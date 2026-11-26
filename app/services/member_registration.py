"""Transactional, idempotent registration for an already verified Firebase UID."""
from sqlalchemy import text

from app.services.organization_registration import RegistrationError


def register_member(database, uid, email, fields):
    with database.begin():
        user = database.execute(text('''SELECT u.user_id,u.email,u.is_active,r.role_name
            FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.firebase_uid=:uid FOR UPDATE'''), {'uid': uid}).mappings().one_or_none()
        if user:
            if not user['is_active'] or user['role_name'] != 'member' or user['email'] != email:
                raise RegistrationError('An account already exists; existing details were preserved.')
            user_id = user['user_id']
        else:
            if database.execute(text('SELECT user_id FROM users WHERE email=:email'), {'email': email}).first():
                raise RegistrationError('An account already exists; administrator linking is required.')
            role_id = database.execute(text("SELECT role_id FROM roles WHERE role_name='member'")).scalar_one_or_none()
            if role_id is None:
                raise RegistrationError('Individual registration is unavailable.', 503)
            user_id = database.execute(text('''INSERT INTO users
                (role_id,email,firebase_uid,password_hash,is_active)
                VALUES(:role,:email,:uid,NULL,TRUE)'''), {'role': role_id, 'email': email, 'uid': uid}).lastrowid
        existing = database.execute(text('''SELECT first_name,last_name,phone,address,city
            FROM member_profiles WHERE user_id=:id'''), {'id': user_id}).mappings().one_or_none()
        if existing:
            if any(existing[key] != value for key, value in fields.items()):
                raise RegistrationError('A profile already exists; existing details were preserved.')
            return {'already_processed': True}
        database.execute(text('''INSERT INTO member_profiles(user_id,first_name,last_name,phone,address,city)
            VALUES(:id,:first_name,:last_name,:phone,:address,:city)'''), dict(fields, id=user_id))
        return {'already_processed': False}
