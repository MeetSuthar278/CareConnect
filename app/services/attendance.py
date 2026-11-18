"""First attendance and SLA handling using existing tables and outbox."""
from sqlalchemy import select, text

from app.models import Referral, ReferralStatusHistory, ServiceRequest
from app.services.notifications import notify
from app.services.outbox import enqueue, utcnow


class AttendanceError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def record_attendance(session, referral_id, user_id):
    with session.begin():
        request_id = session.execute(select(Referral.request_id).where(
            Referral.referral_id == referral_id)).scalar_one_or_none()
        if request_id is None:
            raise AttendanceError("Referral not found", 404)
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == request_id).with_for_update()).scalar_one_or_none()
        referral = session.execute(select(Referral).where(
            Referral.referral_id == referral_id).with_for_update()).scalar_one_or_none()
        if request is None or referral is None:
            raise AttendanceError("Referral not found", 404)
        representative = session.execute(text("""
            SELECT rep.representative_id, rep.organization_id
            FROM organization_representatives rep
            JOIN users u ON u.user_id=rep.user_id
            JOIN roles r ON r.role_id=u.role_id
            WHERE rep.user_id=:user AND u.is_active=TRUE
              AND r.role_name='representative' FOR UPDATE
        """), {"user": user_id}).mappings().one_or_none()
        if representative is None or representative['organization_id'] != referral.organization_id:
            raise AttendanceError("Referral not found", 404)
        attendance = session.execute(text("""
            SELECT attendance_id, referral_id, first_attended_at, is_on_time
            FROM attendance_records WHERE request_id=:request FOR UPDATE
        """), {"request": request_id}).mappings().one_or_none()
        if attendance is not None:
            if attendance['referral_id'] != referral_id or referral.status not in {'attended', 'completed'}:
                raise AttendanceError("Attendance data is inconsistent; coordinator review required")
            return _result(referral_id, request_id, attendance['attendance_id'],
                           attendance['is_on_time'], True)
        if referral.status != 'accepted' or request.status != 'matched' or referral.responded_at is None:
            raise AttendanceError("Only an accepted referral can record first attendance")
        reservation = session.execute(text("""
            SELECT current_active_referrals FROM organization_services
            WHERE organization_id=:org AND service_id=:service AND service_area_id=:area
            FOR UPDATE
        """), {"org": referral.organization_id, "service": request.service_id,
                "area": request.service_area_id}).scalar_one_or_none()
        if reservation is None or reservation <= 0:
            raise AttendanceError("Capacity is inconsistent; coordinator review required")
        # Existing MySQL DATETIME stores whole seconds. Compare the timestamp that
        # will actually be persisted, so producer and consumer agree at the boundary.
        now = utcnow().replace(microsecond=0)
        on_time = now <= request.attendance_deadline
        # Use the SQL representative primary key, which is not necessarily the user ID.
        session.execute(text("""
            INSERT INTO attendance_records
              (request_id, referral_id, attended_by_representative_id, first_attended_at, is_on_time)
            VALUES (:request, :referral, :rep, :now, :on_time)
        """), {"request": request_id, "referral": referral_id,
                "rep": representative['representative_id'], "now": now, "on_time": on_time})
        attendance_id = session.execute(text(
            'SELECT attendance_id FROM attendance_records WHERE request_id=:request'
        ), {"request": request_id}).scalar_one()
        referral.status = 'attended'
        request.status = 'in_progress'
        session.add(ReferralStatusHistory(
            referral_id=referral_id, old_status='accepted', new_status='attended',
            changed_by_user_id=user_id, notes='Organization confirmed first attendance',
        ))
        enqueue(session, 'RequestAttended', request_id,
                {"referral_id": referral_id, "attendance_id": attendance_id},
                f'request-attended:{request_id}')
        return _result(referral_id, request_id, attendance_id, on_time, False)


def _result(referral_id, request_id, attendance_id, on_time, repeated):
    return dict(referral_id=referral_id, request_id=request_id, attendance_id=attendance_id,
                status='attended', is_on_time=bool(on_time), already_processed=repeated)


def handle_request_attended(session, event):
    payload = event['payload']
    if any(type(payload.get(key)) is not int or payload[key] <= 0
           for key in ('referral_id', 'attendance_id')):
        raise ValueError('Attendance event requires positive referral and attendance IDs')
    with session.begin():
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == event['request_id']).with_for_update()).scalar_one_or_none()
        if request is None:
            raise RuntimeError('Attendance request does not exist')
        attendance = session.execute(text("""
            SELECT a.first_attended_at, a.is_on_time, r.status
            FROM attendance_records a JOIN referrals r ON r.referral_id=a.referral_id
            WHERE a.request_id=:request AND r.request_id=:request
              AND a.attendance_id=:attendance AND a.referral_id=:referral
        """), {"request": request.request_id, "attendance": payload['attendance_id'],
                "referral": payload['referral_id']}).mappings().one_or_none()
        if attendance is None or attendance['status'] not in {'attended', 'completed'}:
            raise RuntimeError('Attendance event does not match saved attendance')
        # Recompute from authoritative timestamps, not an event's claimed SLA result.
        on_time = session.execute(text("""
            SELECT a.first_attended_at <= s.attendance_deadline
            FROM attendance_records a JOIN service_requests s ON s.request_id=a.request_id
            WHERE a.attendance_id=:id
        """), {"id": payload['attendance_id']}).scalar_one()
        if bool(on_time) != bool(attendance['is_on_time']):
            raise RuntimeError('Attendance SLA data is inconsistent')
        if on_time:
            return 'on_time'
        coordinators = session.execute(text("""
            SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.is_active=TRUE AND r.role_name='coordinator'
        """)).scalars().all()
        if not coordinators:
            raise RuntimeError('No active coordinator available for late attendance alert')
        notify(session, coordinators, request.request_id, f'attendance-late:{request.request_id}',
               'Late attendance recorded',
               f'Request #{request.request_id}: first attendance occurred after the attendance deadline.')
        return 'late'
