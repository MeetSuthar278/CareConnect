"""Attendance overdue detection and durable coordinator alerts."""
import logging

from sqlalchemy import select, text

from app.models import EventOutbox, ServiceRequest
from app.services.notifications import notify
from app.services.outbox import enqueue, utcnow

logger = logging.getLogger(__name__)
OPEN_STATUSES = {'submitted', 'matched', 'in_progress', 'unmatched'}


def overdue_request_ids(session, limit=100, request_ids=None):
    if not 1 <= limit <= 1000:
        raise ValueError('Batch size must be between 1 and 1000')
    query = select(ServiceRequest.request_id).where(
        ServiceRequest.status.in_(OPEN_STATUSES), ServiceRequest.attendance_deadline < utcnow(),
        ~text_exists_attendance(),
        ~select(EventOutbox.event_id).where(
            EventOutbox.request_id == ServiceRequest.request_id,
            EventOutbox.event_type == 'AttendanceOverdue').exists(),
    )
    if request_ids is not None:
        query = query.where(ServiceRequest.request_id.in_(request_ids))
    return session.execute(query.order_by(
        ServiceRequest.attendance_deadline, ServiceRequest.request_id).limit(limit)).scalars().all()


def text_exists_attendance():
    # Attendance is deliberately not ORM-mapped; use its existing request_id index.
    return select(1).select_from(text('attendance_records a')).where(
        text('a.request_id = service_requests.request_id')).exists()


def flag_overdue(session, request_id):
    with session.begin():
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == request_id).with_for_update()).scalar_one_or_none()
        if request is None or request.status not in OPEN_STATUSES or request.attendance_deadline >= utcnow():
            return False
        if session.execute(text('SELECT attendance_id FROM attendance_records WHERE request_id=:id'),
                           {'id': request_id}).first():
            return False
        key = f'attendance-overdue:{request_id}'
        if session.execute(select(EventOutbox.event_id).where(
                EventOutbox.deduplication_key == key)).first():
            return False
        enqueue(session, 'AttendanceOverdue', request_id,
                {'attendance_deadline': request.attendance_deadline.isoformat() + 'Z'}, key)
        # The outbox business key is the durable flag; preserve all business outcomes.
        return True


def scan_overdue_once(session_factory, limit=100, request_ids=None):
    with session_factory() as session:
        candidates = overdue_request_ids(session, limit, request_ids)
    result = dict(examined=len(candidates), flagged=0, skipped=0, failed=0)
    for request_id in candidates:
        try:
            with session_factory() as session:
                changed = flag_overdue(session, request_id)
            result['flagged' if changed else 'skipped'] += 1
        except Exception as error:
            result['failed'] += 1
            logger.error('Overdue processing failed for request %s (%s); retained for retry',
                         request_id, type(error).__name__)
    return result


def handle_attendance_overdue(session, event):
    with session.begin():
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == event['request_id']).with_for_update()).scalar_one_or_none()
        if request is None:
            raise RuntimeError('Overdue event references a missing request')
        if event['payload'].get('attendance_deadline') != request.attendance_deadline.isoformat() + 'Z':
            raise ValueError('Overdue event deadline does not match saved request')
        if request.attendance_deadline >= utcnow():
            raise RuntimeError('Request attendance deadline has not passed')
        if request.status not in OPEN_STATUSES:
            return 'stale'
        timely_attendance = session.execute(text('''
            SELECT attendance_id FROM attendance_records
            WHERE request_id=:id AND first_attended_at <= :deadline
        '''), {'id': request.request_id, 'deadline': request.attendance_deadline}).first()
        if timely_attendance:
            return 'stale'
        coordinators = session.execute(text('''
            SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.is_active=TRUE AND r.role_name='coordinator'
        ''')).scalars().all()
        if not coordinators:
            raise RuntimeError('No active coordinator available for overdue alert')
        notify(session, coordinators, request.request_id, f'attendance-overdue:{request.request_id}',
               'Attendance deadline missed',
               f'Request #{request.request_id}: no attendance was recorded before its deadline.',
               kind='deadline_missed')
        return 'alerted'
