"""Firebase is mocked; authentication SQL runs only in a disposable memory database."""
from unittest.mock import patch
import pytest
from sqlalchemy import text
from app import create_app, db
from app.auth import InvalidToken, VerificationUnavailable, roles_required


@pytest.fixture
def auth_app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "isolated-auth-tests")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    @app.get("/test/representative")
    @roles_required("representative")
    def representative():
        return {"ok": True}
    with app.app_context():
        with db.engine.begin() as c:
            c.execute(text("CREATE TABLE roles(role_id INTEGER PRIMARY KEY,role_name TEXT UNIQUE)"))
            c.execute(text("CREATE TABLE users(user_id INTEGER PRIMARY KEY,role_id INTEGER,email TEXT UNIQUE,firebase_uid TEXT UNIQUE,password_hash TEXT NULL,is_active BOOLEAN)"))
            c.execute(text("CREATE TABLE organization_representatives(user_id INTEGER UNIQUE,organization_id INTEGER)"))
            c.execute(text("INSERT INTO roles VALUES(1,'member'),(2,'representative'),(3,'coordinator')"))
        yield app
        db.engine.dispose()


@pytest.fixture
def claims():
    return {"uid":"firebase-test-user", "email":"synthetic@example.test", "email_verified":True}


def request(app, claims, path="/api/auth/me"):
    with patch("app.auth.verify_token",return_value=claims):
        return app.test_client().get(path,headers={"Authorization":"Bearer test-token"})


def insert_user(app, role=2, active=True, uid="firebase-test-user", email="synthetic@example.test", linked=True):
    with app.app_context(), db.engine.begin() as c:
        c.execute(text("INSERT INTO users VALUES(10,:role,:email,:uid,'existing-hash',:active)"),
                  {"role":role,"email":email,"uid":uid,"active":active})
        if linked:
            c.execute(text("INSERT INTO organization_representatives VALUES(10,7)"))


@pytest.mark.parametrize("header", [None,"Basic abc","Bearer","Bearer a b"])
def test_auth_requires_bearer_header(auth_app,header):
    with patch("app.auth.verify_token") as verify:
        response=auth_app.test_client().get("/api/auth/me",headers={"Authorization":header} if header else {})
        assert response.status_code==401
        verify.assert_not_called()


@pytest.mark.parametrize("error,status", [(InvalidToken(),401),(VerificationUnavailable(),503)])
def test_invalid_token_and_service_failure(auth_app,error,status):
    with patch("app.auth.verify_token",side_effect=error):
        response=auth_app.test_client().get("/api/auth/me",headers={"Authorization":"Bearer test-token"})
    assert response.status_code==status


@pytest.mark.parametrize("change", [{"uid":""},{"uid":"x"*129},{"email":None}])
def test_invalid_claims_do_not_touch_database(auth_app,claims,change):
    claims.update(change)
    with patch("app.auth.resolve_identity") as resolve:
        assert request(auth_app,claims).status_code==403
        resolve.assert_not_called()


def test_first_identity_creates_only_member_and_duplicate_login_is_safe(auth_app,claims):
    claims["role"]="coordinator"
    for _ in range(2):
        response=request(auth_app,claims)
        assert response.status_code==200
        assert response.json["role"]=="member"
    with auth_app.app_context(),db.engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM users")).scalar()==1
        assert c.execute(text("SELECT password_hash FROM users")).scalar() is None


@pytest.mark.parametrize('role',[1,2,3])
def test_email_verification_uses_sql_role_not_claimed_role(auth_app,claims,role):
    insert_user(auth_app,role=role)
    claims.update(email_verified=False,role='member')
    response=request(auth_app,claims)
    assert response.status_code==(200 if role==1 else 403)


def test_unverified_new_identity_can_only_provision_member(auth_app,claims):
    claims.update(email_verified=False,role='representative',organization_id=7)
    response=request(auth_app,claims)
    assert response.status_code==200 and response.json['role']=='member'
    assert request(auth_app,claims,'/test/representative').status_code==403


def test_existing_email_does_not_link_or_promote(auth_app,claims):
    insert_user(auth_app,role=3,uid=None)
    assert request(auth_app,claims).status_code==409
    with auth_app.app_context(),db.engine.connect() as c:
        assert c.execute(text("SELECT firebase_uid FROM users WHERE user_id=10")).scalar() is None
        assert c.execute(text("SELECT role_id FROM users WHERE user_id=10")).scalar()==3


def test_representative_organization_is_loaded_from_sql(auth_app,claims):
    insert_user(auth_app)
    claims["organization_id"]=999
    response=request(auth_app,claims)
    assert response.status_code==200
    assert response.json["organization_id"]==7
    assert request(auth_app,claims,"/test/representative").status_code==200


def test_inactive_user_denied(auth_app,claims):
    insert_user(auth_app,active=False)
    assert request(auth_app,claims).status_code==403


def test_unlinked_representative_denied(auth_app,claims):
    insert_user(auth_app,linked=False)
    assert request(auth_app,claims).status_code==403


def test_member_cannot_access_representative_action(auth_app,claims):
    assert request(auth_app,claims,"/test/representative").status_code==403


def test_missing_migration_returns_controlled_error(auth_app,claims):
    from sqlalchemy.exc import OperationalError
    with patch("app.auth.resolve_identity",side_effect=OperationalError("test",{},Exception("missing column"))):
        response=request(auth_app,claims)
    assert response.status_code==503
    assert "missing column" not in response.get_data(as_text=True)


def test_existing_home_and_health_preserved(auth_app):
    client=auth_app.test_client()
    assert client.get("/").status_code==200
    assert client.get("/health").status_code==200


@pytest.mark.parametrize("message,expected", [
    ('Firebase ID token has incorrect "aud" claim: private-value', 'project-audience-mismatch'),
    ('Firebase ID token has incorrect "iss" claim: private-value', 'project-issuer-mismatch'),
    ('Token used too early: private-value', 'server-clock-behind-token'),
    ('Token expired: private-value', 'expired-or-server-clock-ahead'),
    ('Could not verify signature: private-value', 'signature-verification-failed'),
    ('private-value', 'invalid-token-or-verifier-configuration'),
])
def test_token_diagnostic_never_returns_raw_details(message, expected):
    from app.auth import token_failure_reason
    result=token_failure_reason(ValueError(message))
    assert result==expected
    assert 'private-value' not in result
