"""Organization profile against disposable SQL; no live identities or contacts."""
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import MultiDict
from werkzeug.serving import make_server

from app.organization import COOKIE
from app.services.organization_profiles import organization_profile,update_organization_profile,OrganizationProfileError
from conftest import LocalSession
from test_organization_workflow import org_engine,client,signed_in,scalar
from test_member_workflow import member_engine
from test_login_ui import login_browser

FIELDS=dict(contact_name='Updated Representative',phone='4035550111',address='45 Synthetic Street',city='Edmonton')


@pytest.fixture
def profile_engine(org_engine):
    with org_engine.begin() as connection:
        for sql in [
            "ALTER TABLE organizations ADD COLUMN address TEXT DEFAULT '123 Demo Street'",
            "ALTER TABLE organizations ADD COLUMN city TEXT DEFAULT 'Calgary'",
            "ALTER TABLE organization_representatives ADD COLUMN full_name TEXT DEFAULT 'Primary Demo'",
            "ALTER TABLE organization_representatives ADD COLUMN phone TEXT DEFAULT '4035550100'",
            "UPDATE organizations SET name='Alpha Organization' WHERE organization_id=1",
            "UPDATE organizations SET name='Beta Organization' WHERE organization_id=2",
            "INSERT INTO users(user_id,role_id,email,is_active) VALUES(10,2,'other-rep@example.test',1),(11,2,'beta-rep@example.test',1)",
            """INSERT INTO organization_representatives(user_id,organization_id,is_primary_contact,full_name,phone)
                VALUES(10,1,0,'Other Alpha Rep','4035550122'),(11,2,1,'Beta Rep','4035550133')""",
            "INSERT INTO service_areas VALUES(2,'Calgary','Second area',1)",
            "INSERT INTO organization_services VALUES(3,1,1,2,'paused',5,0)",
            """INSERT INTO notifications(user_id,type,title,message,deduplication_key)
                VALUES(4,'system','Own','Own representative alert','own-profile'),
                      (10,'system','Private','Other representative secret','other-profile')""",
        ]:
            connection.execute(text(sql))
    return org_engine


def payload(client):
    signed_in(client)
    assert client.get('/organization/profile').status_code==200
    with client.session_transaction() as session:
        csrf=session['organization_csrf']
    return dict(FIELDS,csrf_token=csrf,form_type='details')


def test_own_saved_fields_area_identity_protection_and_private_alerts(client,profile_engine):
    assert client.get('/organization/profile').status_code==302
    signed_in(client)
    response=client.get('/organization/profile')
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    html=response.get_data(as_text=True)
    assert 'value="Alpha Organization" readonly' in html
    assert 'value="Downtown, Calgary; Second area, Calgary" readonly' in html
    assert 'Own representative alert' in html and 'Other representative secret' not in html
    for key in ('org_name','email','service_area'):
        assert 'name="'+key+'"' not in html
    assert '>Change password</button>' in html and 'js/password-change.js' in html
    assert 'name="old_password"' not in html


def test_atomic_save_repeat_and_other_records_preserved(client,profile_engine):
    tables=('users','organization_services','service_priority_support','service_requests',
            'referrals','referral_status_history','event_outbox','notifications')
    def snapshot():
        with profile_engine.connect() as connection:
            return {table:connection.execute(text('SELECT * FROM '+table)).all() for table in tables}
    before=snapshot()
    data=payload(client)
    response=client.post('/organization/profile',data=data)
    assert response.status_code==303 and response.location=='/organization/profile'
    assert scalar(profile_engine,'SELECT contact_phone FROM organizations WHERE organization_id=1')==FIELDS['phone']
    assert scalar(profile_engine,'SELECT phone FROM organization_representatives WHERE user_id=4')==FIELDS['phone']
    assert scalar(profile_engine,'SELECT full_name FROM organization_representatives WHERE user_id=4')==FIELDS['contact_name']
    assert scalar(profile_engine,'SELECT full_name FROM organization_representatives WHERE user_id=10')=='Other Alpha Rep'
    assert scalar(profile_engine,'SELECT phone FROM organization_representatives WHERE user_id=10')=='4035550122'
    assert scalar(profile_engine,'SELECT city FROM organizations WHERE organization_id=2')=='Calgary'
    assert scalar(profile_engine,'SELECT name FROM organizations WHERE organization_id=1')=='Alpha Organization'
    assert scalar(profile_engine,'SELECT status FROM organizations WHERE organization_id=1')=='approved'
    assert client.post('/organization/profile',data=data).status_code==303
    with LocalSession(profile_engine) as database:
        assert update_organization_profile(database,4,1,FIELDS)['already_processed']
    assert snapshot()==before
    assert b'value="Edmonton"' in client.get('/organization/profile').data


@pytest.mark.parametrize('key,value',[
    ('contact_name',''),('contact_name','x'*101),('phone','abc1234'),('phone','1'*16),
    ('phone','123'),('address',''),('address','x'*256),('city','x'*101),('city','   '),
])
def test_validation_preserves_saved_values_and_retains_input(client,profile_engine,key,value):
    data=payload(client);data[key]=value
    response=client.post('/organization/profile',data=data)
    assert response.status_code==400
    assert b'Updated Representative' in response.data or key=='contact_name'
    assert scalar(profile_engine,'SELECT city FROM organizations WHERE organization_id=1')=='Calgary'


def test_csrf_identity_tampering_and_password_submission_rejected(client,profile_engine):
    data=payload(client)
    assert client.post('/organization/profile',data=dict(data,csrf_token='wrong')).status_code==403
    for key,value in [('organization_id','2'),('user_id','10'),('org_name','Changed'),('email','new@example.test'),
                      ('service_area','Other area'),('status','approved'),('password','synthetic')]:
        assert client.post('/organization/profile',data=dict(data,**{key:value})).status_code==400
    assert client.post('/organization/profile',data=dict(data,form_type='password')).status_code==400
    repeated=MultiDict(data);repeated.add('contact_name','Other Name')
    assert client.post('/organization/profile',data=repeated).status_code==400
    assert scalar(profile_engine,'SELECT full_name FROM organization_representatives WHERE user_id=4')=='Primary Demo'


@pytest.mark.parametrize('sql',[
    'UPDATE users SET is_active=FALSE WHERE user_id=4',
    'UPDATE users SET role_id=1 WHERE user_id=4',
    'UPDATE organization_representatives SET organization_id=2 WHERE user_id=4',
])
def test_current_role_activity_membership_rechecked(profile_engine,sql):
    with profile_engine.begin() as connection:
        connection.execute(text(sql))
    with LocalSession(profile_engine) as database,pytest.raises(OrganizationProfileError) as error:
        update_organization_profile(database,4,1,FIELDS)
    assert error.value.status==403
    assert scalar(profile_engine,'SELECT city FROM organizations WHERE organization_id=1')=='Calgary'


def test_wrong_organization_or_role_never_authorized(profile_engine):
    with LocalSession(profile_engine) as database:
        for user,org in [(4,2),(9,1),(1,1)]:
            assert organization_profile(database,user,org) is None
            database.rollback()
            with pytest.raises(OrganizationProfileError) as error:
                update_organization_profile(database,user,org,FIELDS)
            assert error.value.status==403
    assert scalar(profile_engine,'SELECT city FROM organizations WHERE organization_id=2')=='Calgary'


@pytest.mark.parametrize('status',['pending','suspended'])
def test_contact_edit_never_changes_approval_or_coverage(client,profile_engine,status):
    with profile_engine.begin() as connection:
        connection.execute(text('UPDATE organizations SET status=:status WHERE organization_id=1'),{'status':status})
    data=payload(client)
    assert client.post('/organization/profile',data=data).status_code==303
    assert scalar(profile_engine,'SELECT status FROM organizations WHERE organization_id=1')==status
    assert client.get('/organization/services').status_code==302
    assert scalar(profile_engine,'SELECT service_area_id FROM organization_services WHERE organization_service_id=1')==1


def test_nonprimary_rep_edits_self_and_shared_contact_only(profile_engine):
    with LocalSession(profile_engine) as database:
        update_organization_profile(database,10,1,FIELDS)
    assert scalar(profile_engine,'SELECT full_name FROM organization_representatives WHERE user_id=4')=='Primary Demo'
    assert scalar(profile_engine,'SELECT full_name FROM organization_representatives WHERE user_id=10')==FIELDS['contact_name']
    assert scalar(profile_engine,'SELECT is_primary_contact FROM organization_representatives WHERE user_id=10')==0


def test_rollback_both_tables_safe_error_and_escaped_values(client,profile_engine):
    with LocalSession(profile_engine) as database:
        execute=database.execute
        def fail(statement,*args,**kwargs):
            result=execute(statement,*args,**kwargs)
            if str(statement).startswith('UPDATE organization_representatives'):
                raise OperationalError('Synthetic failure',{},Exception())
            return result
        with patch.object(database,'execute',side_effect=fail),pytest.raises(OperationalError):
            update_organization_profile(database,4,1,FIELDS)
    assert scalar(profile_engine,'SELECT city FROM organizations WHERE organization_id=1')=='Calgary'
    assert scalar(profile_engine,'SELECT full_name FROM organization_representatives WHERE user_id=4')=='Primary Demo'
    data=payload(client)
    with patch('app.organization.update_organization_profile',side_effect=OperationalError('Private SQL',{},Exception())):
        response=client.post('/organization/profile',data=data)
    assert response.status_code==503 and b'Could not save your profile.' in response.data
    assert b'Private SQL' not in response.data
    data['address']='<script>alert(1)</script>'
    assert client.post('/organization/profile',data=data).status_code==303
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;' in client.get('/organization/profile').data


def test_empty_coverage_wrong_cookie_and_unverified_rep(client,profile_engine):
    signed_in(client)
    with profile_engine.begin() as connection:
        connection.execute(text('DELETE FROM organization_services WHERE organization_id=1'))
    assert b'value="-" readonly' in client.get('/organization/profile').data
    for claims in [{'uid':'synthetic-member','email_verified':True},
                   {'uid':'synthetic-representative','email_verified':False}]:
        with patch('app.organization.cookie_claims',return_value=claims):
            assert client.get('/organization/profile').status_code==302


def test_browser_navigation_readonly_controls_save_and_mobile(client,profile_engine,login_browser):
    from playwright.sync_api import expect
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':1280,'height':900})
    context.add_cookies([{'name':COOKIE,'value':'synthetic-org-cookie','url':base}])
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(base+'/organization')
        page.get_by_role('link',name='Profile',exact=True).click()
        expect(page.locator('h1')).to_have_text('Organization Profile')
        for key in ('org_name','email','service_area'):
            assert page.locator('#'+key).get_attribute('readonly') is not None
        expect(page.locator('#old_password')).to_be_enabled()
        expect(page.get_by_role('button',name='Change password',exact=True)).to_be_enabled()
        for key,value in FIELDS.items():
            page.locator('#'+key).fill(value)
        page.get_by_role('button',name='Save Changes',exact=True).click()
        expect(page.locator('#page-messages')).to_contain_text('Profile saved.')
        expect(page.locator('#contact_name')).to_have_value(FIELDS['contact_name'])
        expect(page.locator('#org_name')).to_have_value('Alpha Organization')
        page.set_viewport_size({'width':390,'height':844});page.wait_for_load_state('load')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()
