"""Firebase identity, SQL-owned roles. No frontend activation or schema creation.

Adapted from Dhairya's reviewed implementation. Authentication uses its own SQL
transaction so later business handlers can own their transaction boundaries.
"""
from dataclasses import dataclass
from functools import wraps
import hmac

from flask import Blueprint, current_app, g, jsonify, request, session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import db

auth_bp = Blueprint("auth", __name__)


@auth_bp.post('/api/auth/logout-browser')
def logout_browser():
    """Clear only this browser, even after Firebase invalidates its old cookie."""
    supplied=request.headers.get('X-CSRF-Token','')
    valid=any(isinstance(session.get(key),str) and hmac.compare_digest(
        session[key].encode(),supplied.encode()) for key in ('member_csrf','organization_csrf','coordinator_csrf'))
    if not valid:
        return jsonify(error='Reload the page and retry.'),403
    if request.content_length not in (None,0):
        return jsonify(error='No account or password payload is accepted here.'),400
    session.clear()
    response=jsonify(redirect_url='/login')
    for cookie in ('careconnect_member','careconnect_organization','careconnect_coordinator'):
        response.delete_cookie(cookie,path='/')
    response.headers['Cache-Control']='no-store'
    return response


class InvalidToken(Exception):
    """Invalid, revoked, expired or disabled Firebase credential."""


class VerificationUnavailable(Exception):
    """Missing SDK, credentials, certificates or unavailable identity service."""


def token_failure_reason(error):
    """Return fixed diagnostic labels, never raw SDK messages or token claims."""
    kind = type(error).__name__
    if kind in {"ExpiredIdTokenError", "RevokedIdTokenError", "UserDisabledError"}:
        return kind
    message = str(error).lower()
    for marker, reason in (
        ('incorrect "aud"', "project-audience-mismatch"),
        ('incorrect "iss"', "project-issuer-mismatch"),
        ("token used too early", "server-clock-behind-token"),
        ("token expired", "expired-or-server-clock-ahead"),
        ("signature", "signature-verification-failed"),
        ("custom token", "custom-token-instead-of-id-token"),
        ("project id", "project-configuration-error"),
    ):
        if marker in message:
            return reason
    return "invalid-token-or-verifier-configuration"


@dataclass(frozen=True)
class Identity:
    user_id: int
    email: str
    role: str
    organization_id: int | None = None


def verify_token(token):
    # Lazy import keeps existing demo APIs usable before optional Firebase setup.
    try:
        import firebase_admin
        from firebase_admin import auth
        project = current_app.config["FIREBASE_PROJECT_ID"]
        try:
            firebase_app = firebase_admin.get_app(project)
        except ValueError:
            # Concurrent first requests can initialize the named app together.
            try:
                firebase_app = firebase_admin.initialize_app(
                    options={"projectId": project}, name=project)
            except ValueError:
                firebase_app = firebase_admin.get_app(project)
        try:
            return auth.verify_id_token(token, app=firebase_app, check_revoked=True)
        except (auth.InvalidIdTokenError, auth.RevokedIdTokenError,
                auth.UserDisabledError, ValueError) as error:
            current_app.logger.warning("Firebase token rejected (%s)", token_failure_reason(error))
            raise InvalidToken() from error
    except InvalidToken:
        raise
    except Exception as error:
        # Never log bearer tokens or credential contents.
        current_app.logger.error("Firebase verification unavailable (%s)", type(error).__name__)
        raise VerificationUnavailable() from error


def resolve_identity(claims):
    """Requires team migration; raw SQL avoids changing existing ORM queries.

    Never link existing accounts by email or take roles from request/token claims.
    A first-time Firebase identity may create only a member account. Members do
    not require verified email; privileged SQL roles still do.
    """
    uid, email = claims["uid"], claims["email"]
    with Session(db.engine) as session, session.begin():
        user = session.execute(text("""
            SELECT u.user_id, u.email, u.is_active, r.role_name
            FROM users u JOIN roles r ON r.role_id = u.role_id
            WHERE u.firebase_uid = :uid
        """), {"uid": uid}).mappings().first()
        if user is None:
            if session.execute(text("SELECT user_id FROM users WHERE email = :email"),
                               {"email": email}).first():
                return None, ("Account already exists; administrator linking is required", 409)
            role_id = session.execute(text(
                "SELECT role_id FROM roles WHERE role_name = 'member'"
            )).scalar_one_or_none()
            if role_id is None:
                return None, ("Member role is missing", 503)
            result = session.execute(text("""
                INSERT INTO users (role_id, email, firebase_uid, password_hash, is_active)
                VALUES (:role, :email, :uid, NULL, TRUE)
            """), {"role": role_id, "email": email, "uid": uid})
            return Identity(result.lastrowid, email, "member"), None
        if not user["is_active"]:
            return None, ("Account is inactive", 403)
        if user["role_name"] not in {"member", "representative", "coordinator"}:
            return None, ("Account role is not supported", 403)
        if user["role_name"] != "member" and claims.get("email_verified") is not True:
            return None, ("Verify your email before accessing CareConnect", 403)
        organization_id = None
        if user["role_name"] == "representative":
            organization_id = session.execute(text("""
                SELECT organization_id FROM organization_representatives
                WHERE user_id = :id
            """), {"id": user["user_id"]}).scalar_one_or_none()
            if organization_id is None:
                return None, ("Representative is not linked to an organization", 403)
        return Identity(user["user_id"], user["email"], user["role_name"], organization_id), None


def firebase_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        parts = request.headers.get("Authorization", "").split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify(error="Authentication required"), 401
        try:
            claims = verify_token(parts[1])
        except InvalidToken:
            return jsonify(error="Invalid or expired login"), 401
        except VerificationUnavailable:
            return jsonify(error="Authentication service unavailable"), 503
        if not isinstance(claims, dict):
            return jsonify(error="Invalid login claims"), 401
        uid, email = claims.get("uid"), claims.get("email")
        if (not isinstance(uid, str) or not 1 <= len(uid) <= 128 or not uid.isascii()
                or not isinstance(email, str) or not 1 <= len(email) <= 120):
            return jsonify(error="A valid email account is required"), 403
        g.firebase_claims = claims
        try:
            identity, error = resolve_identity(claims)
        except IntegrityError:
            return jsonify(error="Account changed during sign-in; retry"), 409
        except SQLAlchemyError:
            current_app.logger.error("Authentication database unavailable; check schema and connection")
            return jsonify(error="Account service unavailable"), 503
        if error:
            return jsonify(error=error[0]), error[1]
        if identity.role != "member" and claims.get("email_verified") is not True:
            return jsonify(error="Verify your email before accessing CareConnect"), 403
        g.current_user = identity
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    """Authenticate before consulting a SQL-owned role."""
    def decorate(view):
        @firebase_required
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.current_user.role not in roles:
                return jsonify(error="Permission denied"), 403
            return view(*args, **kwargs)
        return wrapped
    return decorate


@auth_bp.get("/api/auth/me")
@firebase_required
def current_user():
    user = g.current_user
    return jsonify(user_id=user.user_id, email=user.email, role=user.role,
                   organization_id=user.organization_id)
