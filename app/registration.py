"""Save an authenticated member's profile without overwriting existing team data."""
import re

from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import db
from app.auth import InvalidToken, VerificationUnavailable, verify_token
from app.services.member_registration import register_member
from app.services.organization_registration import RegistrationError, application_fields, register_organization

registration_bp = Blueprint('registration', __name__)


def verified_registration(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        result = registration_claims()
        if result is not None:
            return result
        return view(*args, **kwargs)
    return wrapped


def registration_claims():
    # Registration alone creates users; never trust client roles or flags.
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
        return jsonify(error='Verify your email before completing registration.'), 403
    g.registration_claims = claims


@registration_bp.post('/api/auth/register/organization')
@verified_registration
def save_organization():
    uid, email = g.registration_claims['uid'], g.registration_claims['email']
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
@verified_registration
def save_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='JSON object required'), 400
    limits = {'full_name': 101, 'phone': 25, 'address': 255, 'city': 100}
    if set(data) != set(limits):
        return jsonify(error='Only name, phone, address and city can be submitted.'), 400
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
        with Session(db.engine) as database:
            result = register_member(database, g.registration_claims['uid'], g.registration_claims['email'], fields)
        return jsonify(status='registered', **result), 200
    except RegistrationError as error:
        return jsonify(error=str(error)), error.status
    except IntegrityError:
        return jsonify(error='Account changed; retry registration with the same details.'), 409
    except SQLAlchemyError:
        current_app.logger.error('Member registration profile unavailable')
        return jsonify(error='Could not save your profile; please retry.'), 503
