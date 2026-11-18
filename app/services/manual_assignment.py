"""Coordinator rescue of unmatched requests; never replace an active referral."""
from sqlalchemy import select,text

from app.models import ServiceRequest,Referral,ReferralStatusHistory
from app.services.matching import eligible_offerings,create_referral_locked
from app.services.outbox import utcnow


class AssignmentError(Exception):
    def __init__(self,message,status=409):
        super().__init__(message)
        self.status=status


def assignment_choices(database,request_id):
    saved=database.get(ServiceRequest,request_id)
    if saved is None or saved.status!='unmatched' or saved.attendance_deadline<=utcnow():
        return [],0
    attempts=database.execute(select(Referral).where(Referral.request_id==request_id)
                              .order_by(Referral.attempt_number)).scalars().all()
    if (len(attempts)>=3 or any(row.status not in {'rejected','timed_out'} for row in attempts)
            or [row.attempt_number for row in attempts]!=list(range(1,len(attempts)+1))):
        return [],0
    names=dict(database.execute(text('SELECT organization_id,name FROM organizations')).all())
    choices=[dict(org_id=row.organization_id,org_name=names[row.organization_id])
             for row in eligible_offerings(database,saved)]
    return choices,attempts[-1].referral_id if attempts else 0


def assign_request(database,request_id,organization_id,coordinator_id,expected_referral_id):
    if any(type(value) is not int or value<=0 for value in (request_id,organization_id,coordinator_id)) or type(expected_referral_id) is not int or expected_referral_id<0:
        raise AssignmentError('Invalid assignment selection.',400)
    with database.begin():
        saved=database.execute(select(ServiceRequest).where(ServiceRequest.request_id==request_id)
                               .with_for_update()).scalar_one_or_none()
        if saved is None:
            raise AssignmentError('Request not found.',404)
        attempts=database.execute(select(Referral).where(Referral.request_id==request_id)
                                  .order_by(Referral.attempt_number).with_for_update()).scalars().all()
        actor=database.execute(text('''SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='coordinator' FOR UPDATE'''),
            {'id':coordinator_id}).scalar_one_or_none()
        if actor is None:
            raise AssignmentError('Coordinator permission required.',403)
        latest=attempts[-1] if attempts else None
        previous=attempts[-2].referral_id if len(attempts)>1 else 0
        # Stable form source + coordinator history distinguishes an exact retry
        # from an old form that now points at a different attempt or organization.
        if latest and latest.organization_id==organization_id and previous==expected_referral_id:
            manual=database.execute(select(ReferralStatusHistory.history_id).where(
                ReferralStatusHistory.referral_id==latest.referral_id,
                ReferralStatusHistory.changed_by_user_id==actor,
                ReferralStatusHistory.new_status=='sent',
                ReferralStatusHistory.notes=='Coordinator manual assignment')).first()
            if manual:
                return dict(referral_id=latest.referral_id,already_processed=True)
        if saved.status!='unmatched' or any(row.status not in {'rejected','timed_out'} for row in attempts):
            raise AssignmentError('Only unmatched requests without an active referral can be assigned.')
        if (latest.referral_id if latest else 0)!=expected_referral_id:
            raise AssignmentError('Request history changed. Reload and retry.')
        if len(attempts)>=3:
            raise AssignmentError('Three referral attempts have already been used.')
        if [row.attempt_number for row in attempts]!=list(range(1,len(attempts)+1)):
            raise AssignmentError('Referral history needs review before assigning.')
        if saved.attendance_deadline<=utcnow():
            raise AssignmentError('The original attendance deadline has passed.')
        chosen=next((row for row in eligible_offerings(database,saved,lock=True)
                     if row.organization_id==organization_id),None)
        if chosen is None:
            raise AssignmentError('Organization is no longer eligible or has no capacity. Reload and retry.')
        now=utcnow()
        if saved.attendance_deadline<=now:
            raise AssignmentError('The original attendance deadline has passed.')
        create_referral_locked(database,saved,chosen,len(attempts)+1,actor=actor,
                               notes='Coordinator manual assignment',now=now)
        latest=database.execute(select(Referral.referral_id).where(Referral.request_id==request_id)
                                .order_by(Referral.attempt_number.desc()).limit(1)).scalar_one()
        return dict(referral_id=latest,already_processed=False)
