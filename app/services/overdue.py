"""Missing attendance scanner and existing AttendanceOverdue consumer adapter."""
from sqlalchemy import text

from app.services.notifications import notify
from app.services.outbox import enqueue, utcnow
from app.services.timeouts import candidate_ids, scan_candidates


def overdue_request_ids(database, batch_size=100, selected_ids=None):
    return candidate_ids(database, '''SELECT sr.request_id AS candidate_id FROM service_requests sr
        WHERE sr.attendance_deadline < :now AND sr.status NOT IN ('completed','cancelled')
          AND NOT EXISTS(SELECT 1 FROM attendance_records a WHERE a.request_id=sr.request_id)
          AND NOT EXISTS(SELECT 1 FROM event_outbox e
              WHERE e.request_id=sr.request_id AND e.event_type='AttendanceOverdue') ''',
        batch_size, selected_ids)


def mark_overdue(database, request_id):
    with database.begin():
        saved = database.execute(text('''SELECT status,attendance_deadline FROM service_requests
            WHERE request_id=:id FOR UPDATE'''), {'id': request_id}).mappings().one_or_none()
        if saved is None or saved['status'] in {'completed', 'cancelled'}:
            return False
        if not database.execute(text('SELECT attendance_deadline < :now FROM service_requests WHERE request_id=:id'),
                                {'id': request_id, 'now': utcnow()}).scalar_one():
            return False
        if database.execute(text('SELECT attendance_id FROM attendance_records WHERE request_id=:id'), {'id': request_id}).first():
            return False
        if database.execute(text("SELECT event_id FROM event_outbox WHERE request_id=:id AND event_type='AttendanceOverdue'"),
                            {'id': request_id}).first():
            return False
        # A notification event does not alter request state, capacity or SLA.
        enqueue(database, 'AttendanceOverdue', request_id, {'request_id': request_id}, f'attendance-overdue:{request_id}')
        return True


def scan_overdue_once(session_factory, batch_size=100, selected_ids=None):
    return scan_candidates(session_factory, overdue_request_ids, mark_overdue, batch_size, selected_ids)


def handle_attendance_overdue(database, event):
    request_id = event['request_id']
    with database.begin():
        saved = database.execute(text('''SELECT status FROM service_requests
            WHERE request_id=:id FOR UPDATE'''), {'id': request_id}).scalar_one_or_none()
        if saved is None:
            raise RuntimeError('Overdue event references a missing request')
        if saved in {'completed', 'cancelled'} or database.execute(text(
                'SELECT attendance_id FROM attendance_records WHERE request_id=:id'), {'id': request_id}).first():
            return 'resolved'
        if not database.execute(text('SELECT attendance_deadline < :now FROM service_requests WHERE request_id=:id'),
                                {'id': request_id, 'now': utcnow()}).scalar_one():
            raise RuntimeError('Overdue event references a future service target')
        recipients = database.execute(text('''SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.is_active=TRUE AND r.role_name='coordinator' ''')).scalars().all()
        if not recipients:
            raise RuntimeError('No coordinator available for overdue notification')
        notify(database, recipients, request_id, f'attendance-overdue:{request_id}',
               'Request needs coordinator attention',
               f'Request #{request_id} has passed its service attendance target without recorded attendance.')
        return 'notified'
