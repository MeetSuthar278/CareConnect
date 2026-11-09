"""Atomic coordinator decisions using existing application and organization tables."""
from sqlalchemy import text

from app.services.notifications import notify
from app.services.outbox import utcnow


class ApprovalError(Exception):
    def __init__(self,message,status=409):
        super().__init__(message)
        self.status=status


def pending_applications(database):
    rows=database.execute(text('''
        SELECT a.application_id,o.organization_id AS org_id,o.name AS org_name,
               o.contact_email AS email,o.contact_phone AS phone,o.city AS service_area,
               a.created_at,rep.full_name AS representative_name,mp.first_name,mp.last_name
        FROM organization_applications a JOIN organizations o ON o.organization_id=a.organization_id
        LEFT JOIN organization_representatives rep ON rep.user_id=a.submitted_by_user_id
          AND rep.organization_id=o.organization_id
        LEFT JOIN member_profiles mp ON mp.user_id=a.submitted_by_user_id
        WHERE o.status='pending' AND a.status IN ('submitted','under_review')
          AND a.application_id=(SELECT latest.application_id FROM organization_applications latest
              WHERE latest.organization_id=o.organization_id ORDER BY latest.application_id DESC LIMIT 1)
        ORDER BY a.application_id
    ''')).mappings().all()
    return [dict(row,contact_name=row['representative_name'] or
                 ((row['first_name'] or '')+' '+(row['last_name'] or '')).strip() or '-') for row in rows]


def decide_application(database,organization_id,application_id,coordinator_id,action,reason=None):
    if action not in {'approve','reject'}:
        raise ApprovalError('Invalid application decision',400)
    if action=='reject':
        if not isinstance(reason,str) or not 1<=len(reason.strip())<=255:
            raise ApprovalError('Enter a rejection reason containing 1 to 255 characters.',400)
        reason=reason.strip()
    else:
        reason=None
    decision='approved' if action=='approve' else 'rejected'
    with database.begin():
        organization=database.execute(text('SELECT status FROM organizations WHERE organization_id=:id FOR UPDATE'),
                                      {'id':organization_id}).scalar_one_or_none()
        application=database.execute(text('''SELECT application_id,status,submitted_by_user_id,decision_notes
            FROM organization_applications WHERE application_id=:app AND organization_id=:org FOR UPDATE'''),
            {'app':application_id,'org':organization_id}).mappings().one_or_none()
        if organization is None or application is None:
            raise ApprovalError('Application not found',404)
        coordinator=database.execute(text('''SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='coordinator' FOR UPDATE'''),
            {'id':coordinator_id}).scalar_one_or_none()
        if coordinator is None:
            raise ApprovalError('Coordinator permission required',403)
        latest=database.execute(text('''SELECT application_id FROM organization_applications
            WHERE organization_id=:org ORDER BY application_id DESC LIMIT 1 FOR UPDATE'''),
            {'org':organization_id}).scalar_one()
        if latest!=application_id:
            raise ApprovalError('A newer application exists. Reload approvals before deciding.')
        if application['status'] in {'approved','rejected'}:
            expected_org='approved' if decision=='approved' else 'pending'
            if (application['status']==decision and application['decision_notes']==reason
                    and organization==expected_org):
                return dict(application_id=application_id,status=decision,already_processed=True)
            raise ApprovalError('Application already decided; existing decision was preserved.')
        if organization!='pending' or application['status'] not in {'submitted','under_review'}:
            raise ApprovalError('Application is not awaiting a decision.')
        if not database.execute(text('SELECT user_id FROM users WHERE user_id=:id'),
                                {'id':application['submitted_by_user_id']}).first():
            raise ApprovalError('Application submitter is missing; review required.')
        database.execute(text('''UPDATE organization_applications
            SET status=:status,reviewed_by_user_id=:reviewer,decision_notes=:notes,decided_at=:now
            WHERE application_id=:app'''),{'status':decision,'reviewer':coordinator_id,'notes':reason,
                                           'now':utcnow().replace(microsecond=0),'app':application_id})
        if action=='approve':
            database.execute(text("UPDATE organizations SET status='approved' WHERE organization_id=:org"),
                             {'org':organization_id})
        # Rejected is an application outcome. Organizations has no rejected enum;
        # leave it pending/unapproved, never misuse suspended or delete the record.
        notify(database,[application['submitted_by_user_id']],None,
               f'organization-application:{application_id}:decision','Organization application decision',
               f'Organization application #{application_id}: {decision}.'+(f' Reason: {reason}' if reason else ''))
        return dict(application_id=application_id,status=decision,already_processed=False)
