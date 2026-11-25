"""Organization portal uses disposable SQL and mocked Firebase sessions."""
import re
import time
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.auth import Identity
from app.organization import COOKIE
from app.services.matching import handle_request_created
from conftest import LocalSession
from test_member_workflow import member_engine
from test_login_ui import login_browser


@pytest.fixture
def org_engine(member_engine):
    with member_engine.begin() as connection:
        for sql in [
            "UPDATE users SET firebase_uid='synthetic-representative' WHERE user_id=4",
            'ALTER TABLE organization_representatives ADD COLUMN representative_id INTEGER',
            'UPDATE organization_representatives SET representative_id=40 WHERE user_id=4',
            'ALTER TABLE attendance_records ADD COLUMN request_id INTEGER',
            'ALTER TABLE attendance_records ADD COLUMN attended_by_representative_id INTEGER',
            'ALTER TABLE attendance_records ADD COLUMN is_on_time BOOLEAN',
            '''CREATE TABLE service_completions(completion_id INTEGER PRIMARY KEY,request_id INTEGER NOT NULL UNIQUE,
                referral_id INTEGER NOT NULL,completed_at DATETIME NOT NULL,outcome TEXT NOT NULL,summary_notes TEXT)''',
        ]:
            connection.execute(text(sql))
    with LocalSession(member_engine) as database:
        handle_request_created(database,{'request_id':1})
    return member_engine


@pytest.fixture
def client(org_engine):
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with patch('app.organization.Session',side_effect=lambda unused:LocalSession(org_engine)), \
         patch('app.organization.cookie_claims',return_value={'uid':'synthetic-representative','email_verified':True}), \
         patch('app.organization.mint_cookie',return_value='synthetic-org-cookie'), \
         patch('app.auth.verify_token',return_value={'uid':'synthetic-representative','email':'rep@example.test','email_verified':True,'auth_time':time.time()}), \
         patch('app.auth.resolve_identity',return_value=(Identity(4,'rep@example.test','representative',1),None)):
        yield app.test_client()


def scalar(engine,sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def change(engine,sql):
    with engine.begin() as connection:
        connection.execute(text(sql))


def signed_in(client):
    client.set_cookie(COOKIE,'synthetic-org-cookie')


def payload(client,action):
    response=client.get('/organization/requests/1')
    assert response.status_code==200
    html=response.get_data(as_text=True)
    data=dict(action=action)
    for key in ('csrf_token','referral_id'):
        data[key]=re.search('name="'+key+'" value="([^"]+)"',html).group(1)
    return data


def test_representative_session_csrf_cookie_rotation_and_logout(client):
    assert client.post('/api/auth/organization-session',headers={'Authorization':'Bearer synthetic'}).status_code==403
    client.get('/login')
    with client.session_transaction() as session:
        csrf=session['login_csrf']
    response=client.post('/api/auth/organization-session',headers={'Authorization':'Bearer synthetic','X-CSRF-Token':csrf})
    assert response.status_code==200 and response.json['redirect_url']=='/organization'
    assert any(COOKIE in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie for cookie in response.headers.getlist('Set-Cookie'))
    assert client.get('/organization').status_code==200
    assert client.get('/organization/logout').status_code==403
    with client.session_transaction() as session:
        csrf=session['organization_csrf']
    assert client.get('/organization/logout',query_string={'csrf':csrf}).status_code==302
    assert client.get('/organization').status_code==302


def test_session_requires_fresh_auth_and_handles_provider_failure(client):
    client.get('/login')
    with client.session_transaction() as session:
        headers={'Authorization':'Bearer synthetic','X-CSRF-Token':session['login_csrf']}
    with patch('app.auth.verify_token',return_value={'uid':'rep','email':'rep@example.test','email_verified':True,'auth_time':time.time()-1000}):
        assert client.post('/api/auth/organization-session',headers=headers).status_code==401
    with patch('app.organization.mint_cookie',side_effect=RuntimeError('injected')):
        assert client.post('/api/auth/organization-session',headers=headers).status_code==503


def test_unverified_representative_denied_for_bearer_and_cookie(client):
    with patch('app.auth.verify_token',return_value={'uid':'synthetic-representative','email':'rep@example.test','email_verified':False,'auth_time':time.time()}):
        assert client.get('/api/auth/me',headers={'Authorization':'Bearer synthetic'}).status_code==403
        assert client.post('/api/auth/organization-session',headers={'Authorization':'Bearer synthetic'}).status_code==403
    signed_in(client)
    with patch('app.organization.cookie_claims',return_value={'uid':'synthetic-representative','email_verified':False}):
        assert client.get('/organization').status_code==302


def test_unauthenticated_or_wrong_role_cookie_cannot_enter(client):
    assert client.get('/organization').status_code==302
    assert client.post('/organization/requests/1/action',data={}).status_code==302
    signed_in(client)
    with patch('app.organization.cookie_claims',return_value={'uid':'synthetic-member','email_verified':True}):
        assert client.get('/organization').status_code==302
    with client.session_transaction() as session:
        session['role']='organization'
        session['organization_id']=1
    assert client.get('/organization').status_code==302


def test_views_scope_contacts_and_complete_sequence(client,org_engine):
    signed_in(client)
    initial=payload(client,'accept')
    page=client.get('/organization/requests/1')
    assert b'member@example.test' not in page.data
    assert b'123 Demo Street' not in page.data
    assert client.get('/organization').status_code==200
    assert client.get('/organization/requests').status_code==200
    assert client.get('/organization/requests/2').status_code==404
    assert client.post('/organization/requests/1/action',data=initial).status_code==303
    page=client.get('/organization/requests/1')
    assert b'Record attendance' in page.data and b'Mark as Completed' not in page.data
    assert b'member@example.test' in page.data
    assert scalar(org_engine,'SELECT status FROM referrals')=='accepted'
    # Replay does not add a second acceptance or reserve capacity again.
    client.post('/organization/requests/1/action',data=initial)
    assert scalar(org_engine,"SELECT COUNT(*) FROM referral_status_history WHERE new_status='accepted'")==1
    assert client.post('/organization/requests/1/action',data=payload(client,'attend')).status_code==303
    page=client.get('/organization/requests/1')
    assert b'Mark as Completed' in page.data and b'Record attendance' not in page.data
    completion=payload(client,'complete')
    client.post('/organization/requests/1/action',data=completion)
    client.post('/organization/requests/1/action',data=completion)
    assert scalar(org_engine,'SELECT status FROM service_requests WHERE request_id=1')=='completed'
    assert scalar(org_engine,'SELECT COUNT(*) FROM service_completions')==1
    assert scalar(org_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=1')==0
    assert scalar(org_engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='RequestAttended'")==1


def test_rejection_validates_reason_and_uses_transactional_service(client,org_engine):
    signed_in(client)
    data=payload(client,'reject')
    assert client.post('/organization/requests/1/action',data=data).status_code==303
    assert scalar(org_engine,'SELECT status FROM referrals')=='sent'
    data['reason']='Synthetic organization browser rejection'
    client.post('/organization/requests/1/action',data=data)
    client.post('/organization/requests/1/action',data=data)
    assert scalar(org_engine,'SELECT status FROM referrals')=='rejected'
    assert scalar(org_engine,'SELECT rejection_reason FROM referrals')==data['reason']
    assert scalar(org_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=1')==0
    assert scalar(org_engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='ReferralRejected'")==1


def test_csrf_tampered_parent_and_cross_org_rejected(client,org_engine):
    signed_in(client)
    data=payload(client,'accept')
    assert client.post('/organization/requests/1/action',data=dict(data,csrf_token='wrong')).status_code==403
    assert client.post('/organization/requests/2/action',data=data).status_code==404
    assert client.post('/organization/requests/1/action',data=dict(data,referral_id=999)).status_code==404
    change(org_engine,'UPDATE referrals SET organization_id=2')
    assert client.get('/organization/requests/1').status_code==404
    assert client.post('/organization/requests/1/action',data=data).status_code==404
    assert scalar(org_engine,'SELECT status FROM referrals')=='sent'


def test_deadline_and_completion_before_attendance_fail_closed(client,org_engine):
    signed_in(client)
    data=payload(client,'complete')
    client.post('/organization/requests/1/action',data=data)
    assert scalar(org_engine,'SELECT COUNT(*) FROM service_completions')==0
    change(org_engine,"UPDATE referrals SET response_deadline='2000-01-01'")
    page=client.get('/organization/requests/1')
    assert b'value="accept"' not in page.data
    client.post('/organization/requests/1/action',data=dict(data,action='accept'))
    assert scalar(org_engine,'SELECT status FROM referrals')=='sent'


@pytest.mark.parametrize('sql', ['UPDATE users SET is_active=0 WHERE user_id=4',
    'UPDATE users SET role_id=1 WHERE user_id=4','DELETE FROM organization_representatives WHERE user_id=4'])
def test_representative_permission_rechecked_on_every_request(client,org_engine,sql):
    signed_in(client)
    data=payload(client,'accept')
    change(org_engine,sql)
    assert client.post('/organization/requests/1/action',data=data).status_code==302
    assert scalar(org_engine,'SELECT status FROM referrals')=='sent'


def test_pending_organization_cannot_accept_and_database_errors_retry(client,org_engine):
    signed_in(client)
    data=payload(client,'accept')
    change(org_engine,"UPDATE organizations SET status='pending' WHERE organization_id=1")
    assert client.post('/organization/requests/1/action',data=data).status_code==403
    change(org_engine,"UPDATE organizations SET status='approved' WHERE organization_id=1")
    with patch('app.organization.accept_referral',side_effect=OperationalError('test',{},Exception())):
        assert client.post('/organization/requests/1/action',data=data).status_code==303
    assert scalar(org_engine,'SELECT status FROM referrals')=='sent'


def test_notification_panel_shows_only_current_representative(client,org_engine):
    signed_in(client)
    change(org_engine,"""INSERT INTO notifications(user_id,type,title,message,deduplication_key)
        VALUES(4,'system','Notice','Representative notice','org-test'),
              (1,'system','Private','Coordinator-only notice','private-test')""")
    page=client.get('/organization')
    assert b'Representative notice' in page.data
    assert b'Coordinator-only notice' not in page.data


def browser_context(client,login_browser):
    import threading
    from werkzeug.serving import make_server
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':1280,'height':1000})
    context.add_cookies([{'name':COOKIE,'value':'synthetic-org-cookie','url':base}])
    return server,thread,context,base


def test_browser_accept_attend_complete(client,org_engine,login_browser):
    from playwright.sync_api import expect
    server,thread,context,base=browser_context(client,login_browser)
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('dialog',lambda dialog:dialog.accept())
    try:
        page.goto(base+'/organization')
        page.get_by_role('link',name='View',exact=True).first.click()
        assert page.get_by_text('member@example.test',exact=True).count()==0
        page.get_by_role('button',name='Accept',exact=True).click()
        expect(page.get_by_role('button',name='Record attendance',exact=True)).to_be_visible()
        expect(page.get_by_text('member@example.test',exact=True)).to_be_visible()
        page.get_by_role('button',name='Record attendance',exact=True).click()
        expect(page.get_by_role('button',name='Mark as Completed',exact=True)).to_be_visible()
        page.get_by_role('button',name='Mark as Completed',exact=True).click()
        expect(page.locator('.page-title-row .status')).to_have_text('Completed')
        assert scalar(org_engine,'SELECT COUNT(*) FROM service_completions')==1
        assert scalar(org_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=1')==0
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()


def test_browser_reject_prompt_cancel_and_reason(client,org_engine,login_browser):
    from playwright.sync_api import expect
    server,thread,context,base=browser_context(client,login_browser)
    page=context.new_page()
    mode=['confirmation']
    def dialog_handler(dialog):
        if dialog.type=='confirm':
            if mode[0]=='confirmation': dialog.dismiss()
            else: dialog.accept()
        elif mode[0]=='prompt': dialog.dismiss()
        else: dialog.accept('Synthetic browser rejection reason')
    page.on('dialog',dialog_handler)
    try:
        page.goto(base+'/organization/requests/1')
        page.get_by_role('button',name='Reject',exact=True).click()
        assert scalar(org_engine,'SELECT status FROM referrals')=='sent'
        mode[0]='prompt'
        page.get_by_role('button',name='Reject',exact=True).click()
        assert scalar(org_engine,'SELECT status FROM referrals')=='sent'
        mode[0]='accept'
        page.get_by_role('button',name='Reject',exact=True).click()
        expect(page.locator('.page-title-row .status')).to_have_text('Rejected')
        assert scalar(org_engine,'SELECT rejection_reason FROM referrals')=='Synthetic browser rejection reason'
        assert scalar(org_engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='ReferralRejected'")==1
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()
