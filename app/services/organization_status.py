"""Coordinator lifecycle changes; existing reservations are never released here."""
from sqlalchemy import text

from app.services.organization_approvals import ApprovalError


def change_organization_status(database, organization_id, coordinator_id, action):
    transitions = {'suspend': ('approved', 'suspended'),
                   'reactivate': ('suspended', 'approved')}
    if action not in transitions:
        raise ApprovalError('Invalid organization action.', 400)
    source, target = transitions[action]
    with database.begin():
        # Same organization -> coordinator lock order as application decisions.
        status = database.execute(text('''SELECT status FROM organizations
            WHERE organization_id=:id FOR UPDATE'''), {'id': organization_id}).scalar_one_or_none()
        if status is None:
            raise ApprovalError('Organization not found.', 404)
        coordinator = database.execute(text('''SELECT u.user_id FROM users u
            JOIN roles r ON r.role_id=u.role_id WHERE u.user_id=:id
            AND u.is_active=TRUE AND r.role_name='coordinator' FOR UPDATE'''),
            {'id': coordinator_id}).scalar_one_or_none()
        if coordinator is None:
            raise ApprovalError('Coordinator permission required.', 403)
        if status == target:
            return {'status': target, 'already_processed': True}
        if status != source:
            raise ApprovalError('Only approved organizations can be suspended or reactivated.')
        database.execute(text('UPDATE organizations SET status=:status WHERE organization_id=:id'),
                         {'status': target, 'id': organization_id})
        return {'status': target, 'already_processed': False}
