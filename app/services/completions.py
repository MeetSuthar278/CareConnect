"""Authorized service completion with one atomic capacity release."""
from sqlalchemy import select, text

from app.models import Referral, ReferralStatusHistory, ServiceRequest
from app.services.outbox import utcnow

OUTCOMES = {'successful', 'partially_successful', 'referred_to_external', 'unsuccessful'}


class CompletionError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def complete_referral(session, referral_id, user_id, outcome='successful', summary_notes=None):
    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        raise CompletionError('Invalid completion outcome', 400)
    if summary_notes is not None:
        if not isinstance(summary_notes, str) or len(summary_notes) > 2000:
            raise CompletionError('Summary notes must contain at most 2000 characters', 400)
        summary_notes = summary_notes.strip() or None
    with session.begin():
        request_id = session.execute(select(Referral.request_id).where(
            Referral.referral_id == referral_id)).scalar_one_or_none()
        if request_id is None:
            raise CompletionError('Referral not found', 404)
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == request_id).with_for_update()).scalar_one_or_none()
        referral = session.execute(select(Referral).where(
            Referral.referral_id == referral_id).with_for_update()).scalar_one_or_none()
        if request is None or referral is None:
            raise CompletionError('Referral not found', 404)
        organization_id = session.execute(text('''
            SELECT rep.organization_id FROM organization_representatives rep
            JOIN users u ON u.user_id=rep.user_id JOIN roles r ON r.role_id=u.role_id
            WHERE rep.user_id=:user AND u.is_active=TRUE
              AND r.role_name='representative' FOR UPDATE
        '''), {'user': user_id}).scalar_one_or_none()
        if organization_id != referral.organization_id:
            raise CompletionError('Referral not found', 404)
        completion = session.execute(text('''
            SELECT completion_id,referral_id,outcome,summary_notes
            FROM service_completions WHERE request_id=:id FOR UPDATE
        '''), {'id': request_id}).mappings().one_or_none()
        if completion is not None:
            if (completion['referral_id'] != referral_id or referral.status != 'completed'
                    or request.status != 'completed'):
                raise CompletionError('Completion data is inconsistent; coordinator review required')
            if completion['outcome'] != outcome or completion['summary_notes'] != summary_notes:
                raise CompletionError('Service already completed with different details')
            return _result(referral_id, request_id, completion['completion_id'], outcome, True)
        if referral.status != 'attended' or request.status != 'in_progress':
            raise CompletionError('Only an attended referral can be completed')
        attendance = session.execute(text('''
            SELECT attendance_id,referral_id FROM attendance_records WHERE request_id=:id FOR UPDATE
        '''), {'id': request_id}).mappings().one_or_none()
        if attendance is None or attendance['referral_id'] != referral_id:
            raise CompletionError('Attendance data is inconsistent; coordinator review required')
        offering = session.execute(text('''
            SELECT organization_service_id FROM organization_services
            WHERE organization_id=:org AND service_id=:service AND service_area_id=:area
            FOR UPDATE
        '''), {'org': referral.organization_id, 'service': request.service_id,
                'area': request.service_area_id}).scalar_one_or_none()
        if offering is None:
            raise CompletionError('Referral offering is missing; coordinator review required')
        now = utcnow().replace(microsecond=0)
        started = session.execute(text('''
            SELECT first_attended_at <= :now FROM attendance_records WHERE attendance_id=:id
        '''), {'now': now, 'id': attendance['attendance_id']}).scalar_one()
        if not started:
            raise CompletionError('Attendance timestamp is in the future; check the server clock')
        released = session.execute(text('''
            UPDATE organization_services SET current_active_referrals=current_active_referrals-1
            WHERE organization_service_id=:id AND current_active_referrals>0
        '''), {'id': offering})
        if released.rowcount != 1:
            raise CompletionError('Capacity is inconsistent; coordinator review required')
        session.execute(text('''
            INSERT INTO service_completions(request_id,referral_id,completed_at,outcome,summary_notes)
            VALUES(:request,:referral,:now,:outcome,:notes)
        '''), {'request': request_id, 'referral': referral_id, 'now': now,
                'outcome': outcome, 'notes': summary_notes})
        completion_id = session.execute(text(
            'SELECT completion_id FROM service_completions WHERE request_id=:id'
        ), {'id': request_id}).scalar_one()
        referral.status = 'completed'
        request.status = 'completed'
        session.add(ReferralStatusHistory(
            referral_id=referral_id, old_status='attended', new_status='completed',
            changed_by_user_id=user_id, notes='Organization completed service: ' + outcome,
        ))
        return _result(referral_id, request_id, completion_id, outcome, False)


def _result(referral_id, request_id, completion_id, outcome, repeated):
    return dict(referral_id=referral_id, request_id=request_id, completion_id=completion_id,
                status='completed', outcome=outcome, already_processed=repeated)
