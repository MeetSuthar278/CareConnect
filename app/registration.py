"""Save an authenticated member's profile without overwriting existing team data."""
import re

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import db
from app.auth import roles_required
from app.auth import InvalidToken, VerificationUnavailable, verify_token
from app.services.organization_registration import RegistrationError, application_fields, register_organization

registration_bp = Blueprint('registration', __name__)


@registration_bp.post('/api/auth/register/organization')
def save_organization():
    # Do not use firebase_required: it auto-provisions first-time UIDs as members.
    # This endpoint verifies Firebase directly and creates only a pending applicant.
    parts = request.headers.get('Authorization', '').split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return jsonify(error='Authentication required'), 401
    try:
        claims = verify_token(parts[1])
    except InvalidToken:
        return jsonify(error='Invalid or expired login'), 401
    except VerificationUnavailable:
        return jsonify(error='Authentication service unavailable'), 503
    if not isinstance(claims, dict):
        return jsonify(error='Invalid login claims'), 401
    uid, email = claims.get('uid'), claims.get('email')
    if (not isinstance(uid, str) or not 1 <= len(uid) <= 128 or not uid.isascii()
            or not isinstance(email, str) or not 1 <= len(email) <= 120
            or claims.get('email_verified') is not True):
        return jsonify(error='Verify your email before submitting your organization application.'), 403
    try:
        fields = application_fields(request.get_json(silent=True))
        with Session(db.engine) as database:
            result = register_organization(database, uid, email, fields)
        return jsonify(status='submitted', **result), 200
    except RegistrationError as error:
        return jsonify(error=str(error)), error.status
    except IntegrityError:
        return jsonify(error='Account or organization changed; retry with the same details.'), 409
    except SQLAlchemyError:
        current_app.logger.error('Organization registration transaction unavailable')
        return jsonify(error='Could not save your application; please retry.'), 503


@registration_bp.after_request
def private_registration_response(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@registration_bp.post('/api/auth/register/profile')
@roles_required('member')
def save_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='JSON object required'), 400
    limits = {'full_name': 101, 'phone': 25, 'address': 255, 'city': 100}
    fields = {}
    for key, limit in limits.items():
        value = data.get(key)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
            return jsonify(error='Check your name, phone, address and city.'), 400
        fields[key] = value.strip()
    names = fields.pop('full_name').split(maxsplit=1)
    fields['first_name'], fields['last_name'] = names[0], names[1] if len(names) > 1 else ''
    if any(len(fields[key]) > 50 for key in ('first_name', 'last_name')):
        return jsonify(error='First and last names must each contain at most 50 characters.'), 400
    if (not re.fullmatch(r'[+0-9() .\-]{7,25}', fields['phone'])
            or not 7 <= sum(character.isdigit() for character in fields['phone']) <= 15):
        return jsonify(error='Enter a valid phone number.'), 400
    try:
        with Session(db.engine) as database, database.begin():
            member = database.execute(text('''
                SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
                WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='member' FOR UPDATE
            '''), {'id': g.current_user.user_id}).scalar_one_or_none()
            if member is None:
                return jsonify(error='Member account unavailable'), 403
            existing = database.execute(text('''
                SELECT first_name,last_name,phone,address,city FROM member_profiles WHERE user_id=:id
            '''), {'id': member}).mappings().one_or_none()
            if existing is not None:
                if any(existing[key] != value for key, value in fields.items()):
                    return jsonify(error='A profile already exists; existing details were preserved.'), 409
                return jsonify(status='registered', already_processed=True), 200
            database.execute(text('''
                INSERT INTO member_profiles(user_id,first_name,last_name,phone,address,city)
                VALUES(:id,:first_name,:last_name,:phone,:address,:city)
            '''), dict(fields, id=member))
        return jsonify(status='registered', already_processed=False), 200
    except SQLAlchemyError:
        current_app.logger.error('Member registration profile unavailable')
        return jsonify(error='Could not save your profile; please retry.'), 503
