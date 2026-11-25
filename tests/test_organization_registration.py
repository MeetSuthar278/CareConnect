"""Verified organization registration, with no live Firebase or database writes."""
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app import create_app
from app.auth import InvalidToken, VerificationUnavailable
from app.services.organization_registration import register_organization, application_fields
from app.services.organization_approvals import decide_application
from conftest import LocalSession

FIELDS = dict(org_name='Synthetic New Partner', address='123 Demo Street',
              city='Calgary', service_area='Calgary NW', contact_name='Demo Representative', phone='4035550100')
CLAIMS = dict(uid='synthetic-new-organization',email='new-partner@example.test',email_verified=True)
HEADERS = {'Authorization':'Bearer synthetic'}
URL = '/api/auth/register/organization'


@pytest.fixture
def registration_engine(engine):
    with engine.begin() as connection:
        for sql in [
            'ALTER TABLE users ADD COLUMN firebase_uid TEXT',
            'CREATE UNIQUE INDEX user_uid ON users(firebase_uid)',
            'CREATE UNIQUE INDEX user_email ON users(email)',
            'ALTER TABLE organizations ADD COLUMN name TEXT',
            'CREATE UNIQUE INDEX organization_name ON organizations(name)',
            'ALTER TABLE organizations ADD COLUMN contact_email TEXT',
            'ALTER TABLE organizations ADD COLUMN contact_phone TEXT',
            'ALTER TABLE organizations ADD COLUMN address TEXT',
            'ALTER TABLE organizations ADD COLUMN city TEXT',
            'ALTER TABLE organization_representatives ADD COLUMN full_name TEXT',
            'ALTER TABLE organization_representatives ADD COLUMN phone TEXT',
            'CREATE UNIQUE INDEX representative_user ON organization_representatives(user_id)',
            '''CREATE TABLE organization_applications(application_id INTEGER PRIMARY KEY,
                organization_id INTEGER,submitted_by_user_id INTEGER,reviewed_by_user_id INTEGER,
                status TEXT,submission_notes TEXT,decision_notes TEXT,decided_at DATETIME)''',
        ]:
            connection.execute(text(sql))
    return engine


@pytest.fixture
def client(registration_engine):
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with patch('app.registration.Session',side_effect=lambda unused:LocalSession(registration_engine)), \
         patch('app.registration.verify_token',return_value=CLAIMS), \
         patch('app.auth.resolve_identity',side_effect=AssertionError('Must not auto-provision a member')):
        yield app.test_client()


def scalar(engine,sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def test_atomic_registration_retry_and_coordinator_approval(client,registration_engine):
    response=client.post(URL,json=FIELDS,headers=HEADERS)
    assert response.status_code==200 and response.json['already_processed'] is False
    org=response.json['organization_id']; application=response.json['application_id']
    assert scalar(registration_engine,f'SELECT status FROM organizations WHERE organization_id={org}')=='pending'
    assert scalar(registration_engine,f'SELECT COUNT(*) FROM organization_services WHERE organization_id={org}')==0
    assert scalar(registration_engine,"SELECT role_id FROM users WHERE firebase_uid='synthetic-new-organization'")==2
    assert scalar(registration_engine,f'SELECT is_primary_contact FROM organization_representatives WHERE organization_id={org}')==1
    assert scalar(registration_engine,'SELECT submission_notes FROM organization_applications')=='Requested service area: Calgary NW'
    assert client.post(URL,json=FIELDS,headers=HEADERS).json['already_processed']
    assert scalar(registration_engine,'SELECT COUNT(*) FROM organization_applications')==1
    assert client.post(URL,json=dict(FIELDS,city='Edmonton'),headers=HEADERS).status_code==409
    with LocalSession(registration_engine) as database:
        decide_application(database,org,application,1,'approve')
    # A registration retry after approval must never reset the lifecycle or decision.
    assert client.post(URL,json=FIELDS,headers=HEADERS).json['already_processed']
    assert scalar(registration_engine,f'SELECT status FROM organizations WHERE organization_id={org}')=='approved'
    assert scalar(registration_engine,'SELECT COUNT(*) FROM notifications')==1


@pytest.mark.parametrize('claims',[
    dict(CLAIMS,email_verified=False),dict(CLAIMS,email_verified='true'),
    dict(CLAIMS,uid=''),dict(CLAIMS,uid='é'),dict(CLAIMS,email=None),None,
])
def test_invalid_or_unverified_identity_never_inserts(client,registration_engine,claims):
    with patch('app.registration.verify_token',return_value=claims):
        assert client.post(URL,json=FIELDS,headers=HEADERS).status_code in {401,403}
    assert scalar(registration_engine,'SELECT COUNT(*) FROM organization_applications')==0
    assert scalar(registration_engine,'SELECT COUNT(*) FROM users')==3


@pytest.mark.parametrize('field,value',[
    ('org_name',''),('org_name','x'*151),('contact_name','x'*101),('address','x'*256),
    ('city','x'*101),('service_area','x'*256),('phone','abc1234'),('phone','1'*16),
    ('phone',True),
])
def test_invalid_fields(client,registration_engine,field,value):
    assert client.post(URL,json=dict(FIELDS,**{field:value}),headers=HEADERS).status_code==400
    assert scalar(registration_engine,'SELECT COUNT(*) FROM organization_applications')==0


def test_authentication_failure_and_tampering(client,registration_engine):
    assert client.post(URL,json=FIELDS).status_code==401
    for failure,code in [(InvalidToken(),401),(VerificationUnavailable(),503)]:
        with patch('app.registration.verify_token',side_effect=failure):
            assert client.post(URL,json=FIELDS,headers=HEADERS).status_code==code
    for data in [[],{},dict(FIELDS,role='coordinator'),dict(FIELDS,email='spoof@example.test')]:
        assert client.post(URL,json=data,headers=HEADERS).status_code==400
    assert scalar(registration_engine,'SELECT COUNT(*) FROM users')==3


@pytest.mark.parametrize('existing_uid,email',[
    ('existing-member','member@example.test'),('existing-representative','rep@example.test'),
    ('existing-coordinator','coord@example.test'),('new-uid','member@example.test'),
])
def test_existing_accounts_never_promoted_or_linked(client,registration_engine,existing_uid,email):
    with registration_engine.begin() as connection:
        connection.execute(text("UPDATE users SET firebase_uid=:uid WHERE email=:email"),dict(uid=existing_uid,email=email))
    with patch('app.registration.verify_token',return_value=dict(CLAIMS,uid=existing_uid,email=email)):
        assert client.post(URL,json=FIELDS,headers=HEADERS).status_code==409
    assert scalar(registration_engine,'SELECT COUNT(*) FROM users')==3
    assert scalar(registration_engine,'SELECT role_id FROM users WHERE user_id=9')==1


def test_other_uid_cannot_claim_existing_organization(client,registration_engine):
    assert client.post(URL,json=FIELDS,headers=HEADERS).status_code==200
    with patch('app.registration.verify_token',return_value=dict(CLAIMS,uid='other-uid',email='other@example.test')):
        assert client.post(URL,json=FIELDS,headers=HEADERS).status_code==409
    assert scalar(registration_engine,'SELECT COUNT(*) FROM users')==4


@pytest.mark.parametrize('table',['users','organizations','organization_representatives','organization_applications'])
def test_rollback_after_each_insert(registration_engine,table):
    with LocalSession(registration_engine) as database:
        original=database.execute
        def fail(statement,*args,**kwargs):
            result=original(statement,*args,**kwargs)
            if str(statement).startswith('INSERT INTO '+table+'\n') or str(statement).startswith('INSERT INTO '+table+' '):
                raise OperationalError('Synthetic failure',{},Exception())
            return result
        with patch.object(database,'execute',side_effect=fail),pytest.raises(OperationalError):
            register_organization(database,CLAIMS['uid'],CLAIMS['email'],application_fields(FIELDS))
    assert scalar(registration_engine,'SELECT COUNT(*) FROM users')==3
    assert scalar(registration_engine,'SELECT COUNT(*) FROM organizations')==2
    assert scalar(registration_engine,'SELECT COUNT(*) FROM organization_applications')==0


def test_database_failures_and_page(client):
    for failure,code in [(OperationalError('synthetic',{},Exception()),503),
                         (IntegrityError('synthetic',{},Exception()),409)]:
        with patch('app.registration.Session',side_effect=failure):
            assert client.post(URL,json=FIELDS,headers=HEADERS).status_code==code
    response=client.get('/register/organization')
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    assert b'js/register-organization.js' in response.data
    assert b'Validate application details' in response.data
    assert client.post('/register/organization',data={'password':'synthetic'}).status_code==405
