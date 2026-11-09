"""Insert a verified applicant's pending organization without promoting existing users."""
import re

from sqlalchemy import text


class RegistrationError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def application_fields(data):
    limits = dict(org_name=150, address=255, service_area=255, city=100,
                  contact_name=100, phone=25)
    if not isinstance(data, dict) or set(data) != set(limits):
        raise RegistrationError('Check the organization and contact details.', 400)
    fields = {}
    for key, limit in limits.items():
        value = data[key]
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
            raise RegistrationError('Check the organization and contact details.', 400)
        fields[key] = value.strip()
    phone = fields['phone']
    if not re.fullmatch(r'[+0-9() .\-]{7,25}', phone) or not 7 <= sum(c.isdigit() for c in phone) <= 15:
        raise RegistrationError('Enter a valid phone number.', 400)
    return fields


def register_organization(database, uid, email, fields):
    notes = 'Requested service area: ' + fields['service_area']
    with database.begin():
        user = database.execute(text('''SELECT u.user_id,u.email,u.is_active,r.role_name
            FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.firebase_uid=:uid FOR UPDATE'''), {'uid': uid}).mappings().one_or_none()
        if user is not None:
            # Only an exact retry of this applicant's own application is recoverable.
            # Do not turn members into representatives or link accounts by email.
            existing = database.execute(text('''SELECT o.organization_id,o.name AS org_name,
                o.address,o.city,o.contact_phone AS phone,o.contact_email,
                rep.full_name AS contact_name,rep.phone AS representative_phone,
                a.application_id,a.submission_notes
                FROM organization_representatives rep
                JOIN organizations o ON o.organization_id=rep.organization_id
                JOIN organization_applications a ON a.organization_id=o.organization_id
                    AND a.submitted_by_user_id=rep.user_id
                WHERE rep.user_id=:id ORDER BY a.application_id LIMIT 1'''),
                {'id': user['user_id']}).mappings().one_or_none()
            if (user['is_active'] and user['role_name'] == 'representative' and user['email'] == email
                    and existing and existing['contact_email'] == email
                    and existing['representative_phone'] == fields['phone']
                    and existing['submission_notes'] == notes
                    and all(existing[key] == fields[key] for key in fields if key != 'service_area')):
                return dict(organization_id=existing['organization_id'],
                            application_id=existing['application_id'], already_processed=True)
            raise RegistrationError('An account already exists; existing details were preserved.')
        if database.execute(text('SELECT user_id FROM users WHERE email=:email'), {'email': email}).first():
            raise RegistrationError('An account already exists; administrator linking is required.')
        if database.execute(text('SELECT organization_id FROM organizations WHERE name=:name'),
                            {'name': fields['org_name']}).first():
            raise RegistrationError('An organization with this name already exists.')
        role = database.execute(text("SELECT role_id FROM roles WHERE role_name='representative'")).scalar_one_or_none()
        if role is None:
            raise RegistrationError('Organization registration is unavailable.', 503)
        user_id = database.execute(text('''INSERT INTO users
            (role_id,email,firebase_uid,password_hash,is_active) VALUES(:role,:email,:uid,NULL,TRUE)'''),
            dict(role=role, email=email, uid=uid)).lastrowid
        org_id = database.execute(text('''INSERT INTO organizations
            (name,contact_email,contact_phone,address,city,status)
            VALUES(:org_name,:email,:phone,:address,:city,'pending')'''), dict(fields, email=email)).lastrowid
        database.execute(text('''INSERT INTO organization_representatives
            (user_id,organization_id,full_name,phone,is_primary_contact)
            VALUES(:user,:org,:contact_name,:phone,TRUE)'''), dict(fields, user=user_id, org=org_id))
        app_id = database.execute(text('''INSERT INTO organization_applications
            (organization_id,submitted_by_user_id,status,submission_notes)
            VALUES(:org,:user,'submitted',:notes)'''), dict(org=org_id, user=user_id, notes=notes)).lastrowid
        return dict(organization_id=org_id, application_id=app_id, already_processed=False)
