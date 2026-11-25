"""Member cookies/pages/form ownership with disposable SQL and mocked Firebase."""
import re
import time
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app import create_app
from app.auth import Identity
from app.member import COOKIE
from conftest import LocalSession
from test_login_ui import login_browser


@pytest.fixture
def member_engine(engine):
    with engine.begin() as connection:
        for sql in [
            'ALTER TABLE users ADD COLUMN firebase_uid TEXT',
            "UPDATE users SET firebase_uid='synthetic-member' WHERE user_id=9",
            "CREATE TABLE service_categories(category_id INTEGER PRIMARY KEY,name TEXT,is_active BOOLEAN)",
            "INSERT INTO service_categories VALUES(1,'Food Assistance',1)",
            "ALTER TABLE services ADD COLUMN delivery_mode TEXT DEFAULT 'in-person'",
            "ALTER TABLE organizations ADD COLUMN name TEXT DEFAULT 'Demo Partner'",
            "ALTER TABLE organizations ADD COLUMN contact_email TEXT DEFAULT 'org@example.test'",
            "ALTER TABLE organizations ADD COLUMN contact_phone TEXT DEFAULT '4035550100'",
            "ALTER TABLE referral_status_history ADD COLUMN changed_at DATETIME",
            "CREATE TABLE member_profiles(profile_id INTEGER PRIMARY KEY,user_id INTEGER UNIQUE,first_name TEXT,last_name TEXT,phone TEXT,address TEXT,city TEXT)",
            "INSERT INTO member_profiles VALUES(1,9,'Synthetic','Member','4035550100','123 Demo Street','Calgary')",
            "INSERT INTO service_requests(request_id,member_id,service_id,service_area_id,priority_id,title,description,status,attendance_deadline) VALUES(2,1,1,1,1,'Other owner','Private other request','submitted','2099-01-01')",
        ]:
            connection.execute(text(sql))
    return engine


@pytest.fixture
def client(member_engine):
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with patch('app.member.Session',side_effect=lambda unused:LocalSession(member_engine)), \
         patch('app.frontend.Session',side_effect=lambda unused:LocalSession(member_engine)), \
         patch('app.member.cookie_claims',return_value={'uid':'synthetic-member','email_verified':True}), \
         patch('app.member.mint_cookie',return_value='synthetic-cookie'), \
         patch('app.auth.verify_token',return_value={'uid':'synthetic-member','email':'member@example.test','email_verified':True,'auth_time':time.time()}), \
         patch('app.auth.resolve_identity',return_value=(Identity(9,'member@example.test','member'),None)):
        yield app.test_client()


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def signed_in(client):
    client.set_cookie(COOKIE,'synthetic-cookie')


def form(client):
    html=client.get('/get-connected').get_data(as_text=True)
    data=dict(service_id='1',priority='High',delivery_method='In person',details='Synthetic member request')
    for key in ('csrf_token','submission_nonce'):
        data[key]=re.search('name="'+key+'" value="([^"]+)"',html).group(1)
    return data


def test_login_csrf_session_cookie_and_logout(client):
    client.get('/login')
    with client.session_transaction() as session:
        csrf=session['login_csrf']
        session['guest_member_id']=123
    headers={'Authorization':'Bearer synthetic','X-CSRF-Token':csrf}
    response=client.post('/api/auth/session',headers=headers)
    assert response.status_code==200 and response.json['redirect_url']=='/member'
    cookie=response.headers['Set-Cookie']
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie and 'Max-Age=3600' in cookie
    with client.session_transaction() as session:
        assert 'guest_member_id' not in session
    page=client.get('/member')
    assert page.status_code==200 and b'Hello, Synthetic' in page.data
    assert page.headers['Cache-Control']=='no-store'
    assert client.get('/logout').status_code==403
    with client.session_transaction() as session:
        csrf=session['member_csrf']
    assert client.get('/logout',query_string={'csrf':csrf}).status_code==302
    assert client.get('/member').status_code==302


def test_login_session_csrf_recent_auth_and_sdk_failure(client):
    assert client.post('/api/auth/session',headers={'Authorization':'Bearer synthetic'}).status_code==403
    client.get('/login')
    with client.session_transaction() as session:
        csrf=session['login_csrf']
    headers={'Authorization':'Bearer synthetic','X-CSRF-Token':csrf}
    with patch('app.auth.verify_token',return_value={'uid':'test','email':'member@example.test','email_verified':True,'auth_time':time.time()-1000}):
        assert client.post('/api/auth/session',headers=headers).status_code==401
    with patch('app.member.mint_cookie',side_effect=RuntimeError('injected')):
        assert client.post('/api/auth/session',headers=headers).status_code==503


def test_secure_cookie_on_https(client):
    client.get('/login',base_url='https://localhost')
    with client.session_transaction() as session:
        csrf=session['login_csrf']
    response=client.post('/api/auth/session',headers={'Authorization':'Bearer synthetic','X-CSRF-Token':csrf},base_url='https://localhost')
    assert response.status_code==200
    assert 'Secure;' in response.headers['Set-Cookie']


def test_no_cookie_or_forged_template_session_cannot_authenticate(client):
    with client.session_transaction() as session:
        session['role']='individual'
        session['user_id']=9
    assert client.get('/member').status_code==302
    assert client.get('/api/member/requests/1').status_code==401
    assert client.post('/api/member/requests',data={}).status_code==401


@pytest.mark.parametrize('change', ['revoked','wrong_user','database'])
def test_cookie_verification_fails_closed(client, change):
    signed_in(client)
    if change=='revoked':
        context=patch('app.member.cookie_claims',side_effect=ValueError('revoked'))
    elif change=='wrong_user':
        context=patch('app.member.cookie_claims',return_value={'uid':'other','email_verified':True})
    else:
        context=patch('app.member.Session',side_effect=RuntimeError('unavailable'))
    with context:
        response=client.get('/get-connected')
    assert response.status_code==302 and response.location.endswith('/login')
    assert 'Max-Age=0' in response.headers['Set-Cookie']


def test_unverified_member_can_start_and_use_session(client):
    client.get('/login')
    with client.session_transaction() as session:
        csrf=session['login_csrf']
    with patch('app.auth.verify_token',return_value={'uid':'synthetic-member','email':'member@example.test','email_verified':False,'auth_time':time.time()}):
        assert client.post('/api/auth/session',headers={'Authorization':'Bearer synthetic','X-CSRF-Token':csrf}).status_code==200
    with patch('app.member.cookie_claims',return_value={'uid':'synthetic-member','email_verified':False}):
        assert client.get('/member').status_code==200


def test_member_views_are_scoped_and_guest_not_inherited(client):
    signed_in(client)
    response=client.get('/member/requests')
    assert response.status_code==200 and b'CC-1' in response.data and b'CC-2' not in response.data
    assert client.get('/member/requests/1').status_code==200
    assert client.get('/member/requests/2').status_code==404
    assert client.get('/api/member/requests/1').status_code==200
    assert client.get('/api/member/requests/2').status_code==404
    assert client.get('/get-connected/done/CC-2').status_code==404


def test_form_uses_saved_identity_atomic_event_and_idempotency(client, member_engine):
    signed_in(client)
    html=client.get('/get-connected').get_data(as_text=True)
    assert '/api/member/requests' in html and 'Synthetic Member' in html
    assert 'id="contact_email"' not in html
    data=form(client)
    data.update(member_id='1',contact_name='Other',contact_email='other@example.test')
    response=client.post('/api/member/requests',data=data)
    assert response.status_code==303
    assert scalar(member_engine,'SELECT member_id FROM service_requests WHERE request_id=3')==9
    assert scalar(member_engine,'SELECT COUNT(*) FROM users')==3
    assert scalar(member_engine,'SELECT COUNT(*) FROM member_profiles')==1
    assert scalar(member_engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='ServiceRequestCreated'")==1
    assert client.post('/api/member/requests',data=data).location==response.location
    assert client.get(response.location).status_code==200
    assert b'/api/member/requests/3' in client.get(response.location).data
    assert scalar(member_engine,'SELECT COUNT(*) FROM service_requests')==3


def test_form_csrf_and_transaction_rollback(client, member_engine):
    signed_in(client)
    data=form(client)
    assert client.post('/api/member/requests',data=dict(data,csrf_token='wrong')).status_code==403
    assert client.post('/api/member/requests',data=dict(data,member_id=1,submission_nonce='bad')).status_code==400
    with patch('app.services.guest_requests.enqueue',side_effect=RuntimeError('injected')):
        with pytest.raises(RuntimeError):
            client.post('/api/member/requests',data=data)
    assert scalar(member_engine,'SELECT COUNT(*) FROM service_requests')==2


def test_sql_member_deactivation_rechecked(client, member_engine):
    signed_in(client)
    with member_engine.begin() as connection:
        connection.execute(text('UPDATE users SET is_active=0 WHERE user_id=9'))
    assert client.get('/member').status_code==302


def test_browser_saved_contact_submission_and_logout(client, member_engine, login_browser):
    import threading
    from werkzeug.serving import make_server
    from playwright.sync_api import expect
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    context=login_browser.new_context(viewport={'width':1280,'height':1000})
    base=f'http://127.0.0.1:{server.server_port}'
    context.add_cookies([{'name':COOKIE,'value':'synthetic-cookie','url':base}])
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(base+'/member')
        expect(page.locator('h1')).to_have_text('Hello, Synthetic')
        page.get_by_role('link',name='Get Connected',exact=True).first.click()
        expect(page.locator('#team-request-form')).to_have_attribute('action','/api/member/requests')
        assert page.locator('#contact_email').count()==0
        page.locator('#service_id').select_option('1')
        page.locator('#priority').select_option('High')
        page.locator('#delivery_method').select_option('In person')
        page.locator('#details').fill('Synthetic browser member request')
        page.get_by_role('button',name='Send Request',exact=True).click()
        expect(page).to_have_url(re.compile('/get-connected/done/CC-3$'))
        page.get_by_role('link',name='Go to My Requests',exact=True).click()
        expect(page.locator('main')).to_contain_text('CC-3')
        assert 'CC-2' not in page.locator('main').inner_text()
        assert scalar(member_engine,'SELECT member_id FROM service_requests WHERE request_id=3')==9
        page.set_viewport_size({'width':390,'height':844})
        # Preserve the team's existing table design; mobile overflow is documented.
        assert page.get_by_role('region',name='Scrollable data table').count()==1
        page.goto(base+'/member')
        # Follow the existing logout anchor, including its unguessable CSRF query.
        page.goto(base+page.locator('a[href^="/logout?"]').get_attribute('href'))
        expect(page).to_have_url(base+'/login')
        page.goto(base+'/member')
        expect(page).to_have_url(base+'/login')
        assert not errors
    finally:
        context.close()
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
