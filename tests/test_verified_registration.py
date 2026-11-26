"""Authentication regressions use synthetic identities and an isolated SQLite DB."""
import time
from unittest.mock import Mock

import pytest
from sqlalchemy import event, text

from app import create_app, db
from app.auth import InvalidToken, VerificationUnavailable


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'test-only')
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('FIREBASE_PROJECT_ID', 'careconnect-bfb9e')
    monkeypatch.setenv('HOSTED_MODE', '0')
    app = create_app({'TESTING': True})
    with app.app_context():
        # SQLite has no row locks; MySQL production SQL retains FOR UPDATE.
        @event.listens_for(db.engine, 'before_cursor_execute', retval=True)
        def sqlite_lock_syntax(connection, cursor, statement, parameters, context, executemany):
            return statement.replace(' FOR UPDATE', ''), parameters

        ddl = [
            'CREATE TABLE roles(role_id INTEGER PRIMARY KEY,role_name TEXT UNIQUE)',
            'CREATE TABLE users(user_id INTEGER PRIMARY KEY,role_id INTEGER,email TEXT UNIQUE,firebase_uid TEXT UNIQUE,password_hash TEXT,is_active BOOLEAN)',
            'CREATE TABLE member_profiles(user_id INTEGER PRIMARY KEY,first_name TEXT,last_name TEXT,phone TEXT,address TEXT,city TEXT)',
            'CREATE TABLE organizations(organization_id INTEGER PRIMARY KEY,name TEXT UNIQUE,contact_email TEXT,contact_phone TEXT,address TEXT,city TEXT,status TEXT)',
            'CREATE TABLE organization_representatives(user_id INTEGER PRIMARY KEY,organization_id INTEGER,full_name TEXT,phone TEXT,is_primary_contact BOOLEAN)',
            'CREATE TABLE organization_applications(application_id INTEGER PRIMARY KEY,organization_id INTEGER,submitted_by_user_id INTEGER,status TEXT,submission_notes TEXT)',
        ]
        with db.engine.begin() as connection:
            for sql in ddl:
                connection.execute(text(sql))
            connection.execute(text("INSERT INTO roles VALUES(1,'member'),(2,'representative'),(3,'coordinator')"))
        yield app
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def claims():
    return {'uid': 'synthetic-uid', 'email': 'person@example.test', 'email_verified': True, 'auth_time': time.time()}


PROFILE = {'full_name': 'Test Person', 'phone': '4035550101', 'address': 'Test address', 'city': 'Calgary'}
ORGANIZATION = dict(org_name='Test organization', phone='4035550101', address='Test address',
                    city='Calgary', contact_name='Test Person', service_area='Calgary')
AUTH = {'Authorization': 'Bearer test-only-token'}


@pytest.mark.parametrize('path', ['/api/auth/register/profile', '/api/auth/register/organization',
                                  '/api/auth/me', '/api/auth/session', '/api/auth/organization-session', '/api/auth/coordinator-session'])
def test_unverified_identity_rejected_before_database(app, monkeypatch, claims, path):
    claims['email_verified'] = False
    monkeypatch.setattr('app.auth.verify_token', lambda _: claims)
    monkeypatch.setattr('app.registration.verify_token', lambda _: claims)
    queries = []
    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', lambda *args: queries.append(args[2]))
        client = app.test_client()
        response = client.get(path, headers=AUTH) if path.endswith('/me') else client.post(path, headers=AUTH, json={'email_verified': True})
        assert response.status_code == 403
        assert not queries


@pytest.mark.parametrize('failure,status', [(InvalidToken, 401), (VerificationUnavailable, 503)])
@pytest.mark.parametrize('path', ['/api/auth/register/profile', '/api/auth/register/organization', '/api/auth/me'])
def test_invalid_or_unavailable_tokens_fail_closed(app, monkeypatch, failure, status, path):
    verifier = Mock(side_effect=failure())
    monkeypatch.setattr('app.auth.verify_token', verifier)
    monkeypatch.setattr('app.registration.verify_token', verifier)
    client = app.test_client()
    response = client.get(path, headers=AUTH) if path.endswith('/me') else client.post(path, headers=AUTH, json=PROFILE)
    assert response.status_code == status


@pytest.mark.parametrize('kind,data,expected', [('profile', PROFILE, 'registered'), ('organization', ORGANIZATION, 'submitted')])
def test_verified_completion_is_transactional_and_idempotent(app, monkeypatch, claims, kind, data, expected):
    monkeypatch.setattr('app.registration.verify_token', lambda _: claims)
    client = app.test_client()
    for attempt in range(2):
        response = client.post('/api/auth/register/' + kind, headers=AUTH, json=data)
        assert response.status_code == 200, response.json
        assert response.json['status'] == expected
        assert response.json['already_processed'] == bool(attempt)
    with db.engine.connect() as connection:
        assert connection.execute(text('SELECT COUNT(*) FROM users')).scalar_one() == 1
        if kind == 'organization':
            assert connection.execute(text('SELECT status FROM organizations')).scalar_one() == 'pending'
            assert connection.execute(text('SELECT COUNT(*) FROM organization_applications')).scalar_one() == 1
        else:
            assert connection.execute(text('SELECT COUNT(*) FROM member_profiles')).scalar_one() == 1
    changed = dict(data, phone='4035550199')
    assert client.post('/api/auth/register/' + kind, headers=AUTH, json=changed).status_code == 409


def test_login_does_not_provision_preliminary_firebase_account(app, monkeypatch, claims):
    monkeypatch.setattr('app.auth.verify_token', lambda _: claims)
    response = app.test_client().get('/api/auth/me', headers=AUTH)
    assert response.status_code == 409
    assert response.json['code'] == 'registration-required'
    with db.engine.connect() as connection:
        assert connection.execute(text('SELECT COUNT(*) FROM users')).scalar_one() == 0


def test_registration_rejects_role_injection_and_never_links_by_email(app, monkeypatch, claims):
    monkeypatch.setattr('app.registration.verify_token', lambda _: claims)
    client = app.test_client()
    assert client.post('/api/auth/register/profile', headers=AUTH, json=dict(PROFILE, role='coordinator')).status_code == 400
    with db.engine.begin() as connection:
        connection.execute(text("INSERT INTO users VALUES(1,3,'person@example.test','different-uid',NULL,TRUE)"))
    assert client.post('/api/auth/register/profile', headers=AUTH, json=PROFILE).status_code == 409
    with db.engine.connect() as connection:
        assert connection.execute(text('SELECT firebase_uid FROM users')).scalar_one() == 'different-uid'


def test_unverified_session_cookie_cannot_open_member_pages(app, monkeypatch, claims):
    claims['email_verified'] = False
    monkeypatch.setattr('app.member.cookie_claims', lambda _: claims)
    client = app.test_client()
    client.set_cookie('careconnect_member', 'synthetic-cookie')
    assert client.get('/member').status_code == 302
    assert client.get('/api/member/requests/1/status').status_code == 401


def test_verified_member_requires_csrf_and_fresh_login_for_session(app, monkeypatch, claims):
    monkeypatch.setattr('app.registration.verify_token', lambda _: claims)
    monkeypatch.setattr('app.auth.verify_token', lambda _: claims)
    mint = Mock(return_value='test-only-cookie')
    monkeypatch.setattr('app.member.mint_cookie', mint)
    client = app.test_client()
    assert client.post('/api/auth/register/profile', headers=AUTH, json=PROFILE).status_code == 200
    assert client.post('/api/auth/session', headers=AUTH).status_code == 403
    with client.session_transaction() as session:
        session['login_csrf'] = 'test-csrf'
    headers = dict(AUTH, **{'X-CSRF-Token': 'test-csrf'})
    claims['auth_time'] = time.time() - 600
    assert client.post('/api/auth/session', headers=headers).status_code == 401
    claims['auth_time'] = time.time()
    response = client.post('/api/auth/session', headers=headers)
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers.getlist('Set-Cookie')[0]
    assert mint.call_count == 1


def test_error_responses_are_friendly_and_keep_http_headers(app, caplog):
    @app.get('/synthetic-failure')
    def fail():
        raise RuntimeError('secret-data-sentinel')
    app.config['TESTING'] = False
    client = app.test_client()
    response = client.get('/synthetic-failure')
    assert response.status_code == 500
    assert b'Something went wrong' in response.data
    assert b'secret-data-sentinel' not in response.data
    assert 'secret-data-sentinel' not in caplog.text
    assert response.headers['Cache-Control'] == 'no-store'
    missing = client.get('/api/does-not-exist')
    assert missing.status_code == 404 and missing.is_json
    method = client.post('/health')
    assert method.status_code == 405 and 'GET' in method.headers['Allow']


def test_missing_configuration_identifies_names_without_values(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    with pytest.raises(RuntimeError, match='Missing required configuration: SECRET_KEY'):
        create_app()


def test_missing_firebase_web_configuration_has_friendly_503(app, monkeypatch):
    monkeypatch.delenv('FIREBASE_WEB_API_KEY', raising=False)
    response = app.test_client().get('/login')
    assert response.status_code == 503
    assert b'Account services are temporarily unavailable' in response.data


def test_hosted_firebase_cookie_is_secure_even_without_forwarded_https(app, monkeypatch, claims):
    app.config['HOSTED_MODE'] = True
    monkeypatch.setattr('app.registration.verify_token', lambda _: claims)
    monkeypatch.setattr('app.auth.verify_token', lambda _: claims)
    monkeypatch.setattr('app.member.mint_cookie', lambda _: 'test-cookie')
    client = app.test_client()
    assert client.post('/api/auth/register/profile', headers=AUTH, json=PROFILE).status_code == 200
    with client.session_transaction() as session:
        session['login_csrf'] = 'csrf'
    response = client.post('/api/auth/session', headers=dict(AUTH, **{'X-CSRF-Token': 'csrf'}))
    assert response.status_code == 200
    cookies = response.headers.getlist('Set-Cookie')
    assert any('careconnect_member=' in value and 'Secure' in value and 'HttpOnly' in value for value in cookies)
