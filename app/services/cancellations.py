"""Cancel only an owned waiting request with no active referral or attendance."""
from sqlalchemy import select,text
from app.models import ServiceRequest,Referral


class CancellationError(Exception):
    def __init__(self,message,status=409):
        super().__init__(message)
        self.status=status


def cancel_request(database,request_id,member_id):
    with database.begin():
        saved=database.execute(select(ServiceRequest).where(ServiceRequest.request_id==request_id).with_for_update()).scalar_one_or_none()
        if saved is None or saved.member_id!=member_id:
            raise CancellationError('Request not found.',404)
        refs=database.execute(select(Referral).where(Referral.request_id==request_id).order_by(Referral.attempt_number).with_for_update()).scalars().all()
        member=database.execute(text('''SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='member' FOR UPDATE'''),{'id':member_id}).scalar_one_or_none()
        if member is None:
            raise CancellationError('Member permission required.',403)
        if saved.status=='cancelled':
            return dict(already_processed=True)
        if saved.status not in {'submitted','unmatched'} or any(row.status not in {'rejected','timed_out'} for row in refs):
            raise CancellationError('Requests with an active referral or completed assistance cannot be cancelled here.')
        attended=database.execute(text('''SELECT a.attendance_id FROM attendance_records a
            JOIN referrals r ON r.referral_id=a.referral_id WHERE r.request_id=:id LIMIT 1'''),{'id':request_id}).first()
        if attended:
            raise CancellationError('An attended request cannot be cancelled.')
        saved.status='cancelled'
        return dict(already_processed=False)
