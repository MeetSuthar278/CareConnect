"""Member profile updates against disposable SQL and mocked Firebase cookies."""
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import MultiDict
from werkzeug.serving import make_server

from app.member import COOKIE
from app.services.member_profiles import ProfileError, update_profile
from conftest import LocalSession
from test_member_workflow import member_engine,client,signed_in,scalar
from test_login_ui import login_browser

FIELDS=dict(full_name='Updated Demo',phone='4035550111',address='45 Synthetic Street',city='Edmonton')


def payload(client,**changes):
    signed_in(client)
    assert client.get('/member/profile').status_code==200
    with client.session_transaction() as session:
        csrf=session['member_csrf']
    return dict(FIELDS,csrf_token=csrf,form_type='details',**changes)


def test_get_own_profile_email_readonly_and_password_client_form(client,member_engine):
    assert client.get('/member/profile').status_code==302
    signed_in(client)
    response=client.get('/member/profile')
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    html=response.get_data(as_text=True)
    assert 'value="Synthetic Member"' in html and 'value="member@example.test" readonly' in html
    assert 'name="email"' not in html
    assert 'name="old_password"' not in html
    assert '>Change password</button>' in html and 'js/password-change.js' in html
    assert 'name="csrf_token"' in html


def test_update_own_profile_repeat_and_preserve_other_tables(client,member_engine):
    with member_engine.begin() as connection:
        connection.execute(text("INSERT INTO users(user_id,role_id,email,is_active) VALUES(10,1,'other@example.test',1)"))
        connection.execute(text("INSERT INTO member_profiles VALUES(2,10,'Other','Member','4035550122','Other address','Calgary')"))
    tables=('users','service_requests','referrals','referral_status_history',
            'event_outbox','organization_services','notifications')
    def snapshot():
        with member_engine.connect() as connection:
            return {table:connection.execute(text('SELECT * FROM '+table)).all() for table in tables}
    before=snapshot()
    data=payload(client)
    response=client.post('/member/profile',data=data)
    assert response.status_code==303 and response.location=='/member/profile'
    assert scalar(member_engine,'SELECT first_name FROM member_profiles WHERE user_id=9')=='Updated'
    assert scalar(member_engine,'SELECT city FROM member_profiles WHERE user_id=9')=='Edmonton'
    assert scalar(member_engine,'SELECT city FROM member_profiles WHERE user_id=10')=='Calgary'
    assert client.post('/member/profile',data=data).status_code==303
    assert snapshot()==before
    with LocalSession(member_engine) as database:
        assert update_profile(database,9,FIELDS)['already_processed']
    assert b'value="Updated Demo"' in client.get('/member/profile').data
    assert b'Hello, Updated' in client.get('/member').data
    assert b'45 Synthetic Street' in client.get('/get-connected').data


@pytest.mark.parametrize('field,value',[
    ('full_name',''),('full_name','x'*51),('full_name','A '+'x'*51),
    ('phone','abc1234'),('phone','1'*16),('phone','123'),('address',''),
    ('address','x'*256),('city','x'*101),('city','   '),
])
def test_invalid_fields_retain_input_and_preserve_database(client,member_engine,field,value):
    data=payload(client)
    data[field]=value
    response=client.post('/member/profile',data=data)
    assert response.status_code==400
    assert b'Updated Demo' in response.data or field=='full_name'
    assert scalar(member_engine,'SELECT first_name FROM member_profiles WHERE user_id=9')=='Synthetic'


def test_csrf_mass_assignment_password_and_duplicate_fields_rejected(client,member_engine):
    data=payload(client)
    assert client.post('/member/profile',data=dict(data,csrf_token='wrong')).status_code==403
    for key,value in [('user_id','10'),('email','other@example.test'),('role','coordinator'),
                      ('password','synthetic'),('firebase_uid','other-uid')]:
        assert client.post('/member/profile',data=dict(data,**{key:value})).status_code==400
    assert client.post('/member/profile',data=dict(data,form_type='password')).status_code==400
    repeated=MultiDict(data);repeated.add('full_name','Conflicting Name')
    assert client.post('/member/profile',data=repeated).status_code==400
    assert scalar(member_engine,'SELECT first_name FROM member_profiles WHERE user_id=9')=='Synthetic'


@pytest.mark.parametrize('claims',[
    {'uid':'synthetic-representative','email_verified':True},
    {'uid':'synthetic-coordinator','email_verified':True},
])
def test_nonmember_cookie_cannot_open_or_submit(client,claims):
    data=payload(client)
    with patch('app.member.cookie_claims',return_value=claims):
        assert client.get('/member/profile').status_code==302
        assert client.post('/member/profile',data=data).status_code==302


@pytest.mark.parametrize('sql',[
    'UPDATE users SET is_active=FALSE WHERE user_id=9',
    'UPDATE users SET role_id=2 WHERE user_id=9',
])
def test_role_and_activity_rechecked_inside_transaction(member_engine,sql):
    with member_engine.begin() as connection:
        connection.execute(text(sql))
    with LocalSession(member_engine) as database,pytest.raises(ProfileError) as error:
        update_profile(database,9,FIELDS)
    assert error.value.status==403
    assert scalar(member_engine,'SELECT first_name FROM member_profiles WHERE user_id=9')=='Synthetic'


def test_missing_profile_not_created_and_bad_types_rejected(member_engine):
    with member_engine.begin() as connection:
        connection.execute(text('DELETE FROM member_profiles WHERE user_id=9'))
    with LocalSession(member_engine) as database:
        with pytest.raises(ProfileError) as error:
            update_profile(database,9,FIELDS)
        assert error.value.status==404
        for data in [[],dict(FIELDS,phone=True),dict(FIELDS,email='ignored@example.test')]:
            with pytest.raises(ProfileError) as error:
                update_profile(database,9,data)
            assert error.value.status==400
    assert scalar(member_engine,'SELECT COUNT(*) FROM member_profiles')==0


def test_rollback_after_update_and_safe_error_response(client,member_engine):
    with LocalSession(member_engine) as database:
        execute=database.execute
        def fail(statement,*args,**kwargs):
            result=execute(statement,*args,**kwargs)
            if str(statement).startswith('UPDATE member_profiles'):
                raise OperationalError('Synthetic failure',{},Exception())
            return result
        with patch.object(database,'execute',side_effect=fail),pytest.raises(OperationalError):
            update_profile(database,9,FIELDS)
    assert scalar(member_engine,'SELECT first_name FROM member_profiles WHERE user_id=9')=='Synthetic'
    data=payload(client)
    with patch('app.member.update_profile',side_effect=OperationalError('Private SQL failure',{},Exception())):
        response=client.post('/member/profile',data=data)
    assert response.status_code==503 and b'Could not save your profile.' in response.data
    assert b'Private SQL failure' not in response.data and b'Updated Demo' in response.data


def test_single_name_whitespace_normalization_and_escaping(client,member_engine):
    with LocalSession(member_engine) as database:
        update_profile(database,9,dict(FIELDS,full_name='   Demo    ',address='<script>alert(1)</script>'))
    signed_in(client)
    response=client.get('/member/profile')
    assert scalar(member_engine,'SELECT last_name FROM member_profiles WHERE user_id=9')==''
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;' in response.data
    assert b'<script>alert(1)</script>' not in response.data


def test_browser_profile_navigation_save_and_disabled_identity_controls(client,member_engine,login_browser):
    from playwright.sync_api import expect
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':1280,'height':900})
    context.add_cookies([{'name':COOKIE,'value':'synthetic-cookie','url':base}])
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(base+'/member')
        page.get_by_role('link',name='Profile',exact=True).click()
        expect(page.locator('h1')).to_have_text('My Profile')
        assert page.locator('#email').get_attribute('readonly') is not None
        expect(page.locator('#old_password')).to_be_enabled()
        expect(page.get_by_role('button',name='Change password',exact=True)).to_be_enabled()
        for key,value in FIELDS.items():
            page.locator('#'+key).fill(value)
        page.get_by_role('button',name='Save Changes',exact=True).click()
        expect(page.locator('#page-messages')).to_contain_text('Profile saved.')
        expect(page.locator('#full_name')).to_have_value('Updated Demo')
        expect(page.locator('#email')).to_have_value('member@example.test')
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_load_state('load')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()
