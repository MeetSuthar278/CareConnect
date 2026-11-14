"""Member-owned yes/no feedback and durable partner/coordinator delivery."""
from sqlalchemy import select, text

from app.models import ServiceRequest
from app.services.notifications import notify
from app.services.outbox import enqueue


class FeedbackError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def submit_feedback(session, request_id, user_id, is_helpful, comment=None):
    if type(is_helpful) is not bool:
        raise FeedbackError('is_helpful must be true or false', 400)
    if comment is not None:
        if not isinstance(comment, str) or len(comment) > 2000:
            raise FeedbackError('Comment must contain at most 2000 characters', 400)
        comment = comment.strip() or None
    with session.begin():
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == request_id).with_for_update()).scalar_one_or_none()
        if request is None or request.member_id != user_id:
            raise FeedbackError('Request not found', 404)
        member = session.execute(text('''
            SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='member' FOR UPDATE
        '''), {'id': user_id}).scalar_one_or_none()
        if member is None:
            raise FeedbackError('Request not found', 404)
        if request.status != 'completed':
            raise FeedbackError('Feedback requires a completed service request')
        completion = session.execute(text('''
            SELECT r.organization_id FROM service_completions c
            JOIN referrals r ON r.referral_id=c.referral_id
            WHERE c.request_id=:id AND r.request_id=:id AND r.status='completed'
            FOR UPDATE
        '''), {'id': request_id}).scalar_one_or_none()
        if completion is None:
            raise FeedbackError('Completion data is inconsistent; coordinator review required')
        existing = session.execute(text('''
            SELECT feedback_id,member_id,organization_id,is_helpful,comment
            FROM feedback WHERE request_id=:id FOR UPDATE
        '''), {'id': request_id}).mappings().one_or_none()
        if existing is not None:
            if existing['member_id'] != user_id or existing['organization_id'] != completion:
                raise FeedbackError('Feedback data is inconsistent; coordinator review required')
            if bool(existing['is_helpful']) != is_helpful or existing['comment'] != comment:
                raise FeedbackError('Feedback already submitted with different details')
            return _result(request_id, existing['feedback_id'], is_helpful, True)
        # The legacy optional rating column is deliberately left NULL.
        session.execute(text('''
            INSERT INTO feedback(request_id,member_id,organization_id,is_helpful,comment)
            VALUES(:request,:member,:org,:helpful,:comment)
        '''), {'request': request_id, 'member': user_id, 'org': completion,
                'helpful': is_helpful, 'comment': comment})
        feedback_id = session.execute(text('SELECT feedback_id FROM feedback WHERE request_id=:id'),
                                      {'id': request_id}).scalar_one()
        enqueue(session, 'FeedbackSubmitted', request_id, {'feedback_id': feedback_id},
                f'feedback-submitted:{request_id}')
        return _result(request_id, feedback_id, is_helpful, False)


def _result(request_id, feedback_id, is_helpful, repeated):
    return dict(request_id=request_id, feedback_id=feedback_id, is_helpful=is_helpful,
                already_processed=repeated)


def handle_feedback_submitted(session, event):
    feedback_id = event['payload'].get('feedback_id')
    if type(feedback_id) is not int or feedback_id <= 0:
        raise ValueError('FeedbackSubmitted requires a positive feedback_id')
    with session.begin():
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == event['request_id']).with_for_update()).scalar_one_or_none()
        if request is None or request.status != 'completed':
            raise RuntimeError('Feedback event requires a completed request')
        feedback = session.execute(text('''
            SELECT f.organization_id,f.is_helpful FROM feedback f
            JOIN service_completions c ON c.request_id=f.request_id
            JOIN referrals r ON r.referral_id=c.referral_id AND r.request_id=f.request_id
            WHERE f.feedback_id=:feedback AND f.request_id=:request AND f.member_id=:member
              AND f.organization_id=r.organization_id AND r.status='completed'
        '''), {'feedback': feedback_id, 'request': request.request_id,
                'member': request.member_id}).mappings().one_or_none()
        if feedback is None:
            raise RuntimeError('Feedback event does not match saved completed service')
        representatives = session.execute(text('''
            SELECT u.user_id,rep.is_primary_contact FROM organization_representatives rep
            JOIN users u ON u.user_id=rep.user_id JOIN roles r ON r.role_id=u.role_id
            WHERE rep.organization_id=:org AND u.is_active=TRUE AND r.role_name='representative'
            ORDER BY u.user_id
        '''), {'org': feedback['organization_id']}).all()
        recipients = ([row.user_id for row in representatives if row.is_primary_contact]
                      or [row.user_id for row in representatives])
        if not recipients:
            raise RuntimeError('No active representative available for feedback notification')
        notify(session, recipients, request.request_id, f'feedback-submitted:{feedback_id}',
               'Service feedback received',
               f'Request #{request.request_id}: member reported the service was '
               + ('helpful.' if feedback['is_helpful'] else 'not helpful.'))
        if not feedback['is_helpful']:
            coordinators = session.execute(text('''
                SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
                WHERE u.is_active=TRUE AND r.role_name='coordinator'
            ''')).scalars().all()
            if not coordinators:
                raise RuntimeError('No active coordinator available for negative feedback alert')
            notify(session, coordinators, request.request_id, f'feedback-negative:{feedback_id}',
                   'Negative service feedback',
                   f'Request #{request.request_id}: member reported the service was not helpful.')
