"""Profile creation requires an authenticated member; all SQL is disposable."""
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.auth import Identity
from conftest import LocalSession

PROFILE = dict(full_name='Synthetic Member', phone='4035550100', address='123 Demo Street', city='Calgary')
HEADERS = {'Authorization': 'Bearer synthetic'}
URL = '/api/auth/register/profile'


@pytest.fixture
def client(engine):
    with engine.begin() as connection:
        connection.execute(text('''CREATE TABLE member_profiles(profile_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE,first_name TEXT,last_name TEXT,phone TEXT,address TEXT,city TEXT)'''))
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with patch('app.auth.verify_token',return_value={'uid':'test-member','email':'member@example.test','email_verified':True}), \
         patch('app.auth.resolve_identity',return_value=(Identity(9,'member@example.test','member'),None)), \
         patch('app.registration.Session',side_effect=lambda unused:LocalSession(engine)):
        yield app.test_client()


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def test_new_profile_and_idempotency_preserve_existing(client, engine):
    response=client.post(URL,json=PROFILE,headers=HEADERS)
    assert response.status_code == 200 and not response.json['already_processed']
    assert scalar(engine,'SELECT first_name FROM member_profiles') == 'Synthetic'
    assert scalar(engine,'SELECT last_name FROM member_profiles') == 'Member'
    assert scalar(engine,'SELECT user_id FROM member_profiles') == 9
    assert client.post(URL,json=PROFILE,headers=HEADERS).json['already_processed']
    assert client.post(URL,json=dict(PROFILE,city='Edmonton'),headers=HEADERS).status_code == 409
    assert scalar(engine,'SELECT city FROM member_profiles') == 'Calgary'
    assert scalar(engine,'SELECT COUNT(*) FROM member_profiles') == 1


def test_unverified_member_allowed_but_role_and_activity_required(client, engine):
    assert client.post(URL,json=PROFILE).status_code == 401
    with patch('app.auth.verify_token',return_value={'uid':'test','email':'member@example.test','email_verified':False}):
        assert client.post(URL,json=PROFILE,headers=HEADERS).status_code == 200
    with patch('app.auth.resolve_identity',return_value=(Identity(4,'rep@example.test','representative',1),None)):
        assert client.post(URL,json=PROFILE,headers=HEADERS).status_code == 403
    with engine.begin() as connection:
        connection.execute(text('UPDATE users SET is_active=0 WHERE user_id=9'))
    assert client.post(URL,json=PROFILE,headers=HEADERS).status_code == 403
    assert scalar(engine,'SELECT COUNT(*) FROM member_profiles') == 1


@pytest.mark.parametrize('field,value', [('full_name',''),('full_name','x'*51),('city','x'*101),
    ('address',True),('phone','000'),('phone','abcdefg'),('phone','1'*16)])
def test_profile_validation(client, field, value):
    assert client.post(URL,json=dict(PROFILE,**{field:value}),headers=HEADERS).status_code == 400


def test_json_and_database_failure(client, engine):
    assert client.post(URL,json=[],headers=HEADERS).status_code == 400
    with patch('app.registration.Session',side_effect=OperationalError('test',{},Exception())):
        assert client.post(URL,json=PROFILE,headers=HEADERS).status_code == 503
    assert scalar(engine,'SELECT COUNT(*) FROM member_profiles') == 0


def test_routes_and_safe_no_javascript_fallback(client):
    assert client.get('/signup').status_code == 200
    response=client.get('/register/individual')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert b'id="registration-form"' in response.data
    assert b'js/register.js' in response.data
    assert client.post('/register/individual',data={'password':'synthetic'}).status_code == 405
