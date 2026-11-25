"""Read-only coordinator UI with disposable SQL and mocked Firebase."""
import time
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app import create_app
from app.auth import Identity
from app.coordinator import COOKIE
from conftest import LocalSession
from test_organization_workflow import org_engine
from test_member_workflow import member_engine
from test_login_ui import login_browser


@pytest.fixture
def coordinator_engine(org_engine):
    with org_engine.begin() as connection:
        for sql in [
            "UPDATE users SET firebase_uid='synthetic-coordinator' WHERE user_id=1",
            "ALTER TABLE organizations ADD COLUMN city TEXT DEFAULT 'Calgary'",
            "UPDATE organizations SET status='pending' WHERE organization_id=2",
            "ALTER TABLE organization_representatives ADD COLUMN full_name TEXT DEFAULT 'Synthetic Representative'",
            '''CREATE TABLE organization_applications(application_id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL,submitted_by_user_id INTEGER NOT NULL,
                reviewed_by_user_id INTEGER,status TEXT NOT NULL,submission_notes TEXT,decision_notes TEXT,
                decided_at DATETIME,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''',
            "INSERT INTO organization_applications(application_id,organization_id,submitted_by_user_id,status) VALUES(1,2,9,'submitted')",
            'CREATE TABLE feedback(feedback_id INTEGER PRIMARY KEY,request_id INTEGER UNIQUE,is_helpful BOOLEAN)',
            """INSERT INTO service_requests(request_id,member_id,service_id,service_area_id,priority_id,title,description,status,attendance_deadline)
               VALUES(14,9,1,1,1,'Synthetic unmatched','Synthetic details to inspect','unmatched','2000-01-01'),
                     (15,9,1,1,1,'Completed with negative feedback','Completed synthetic service','completed','2000-01-01'),
                     (16,9,1,1,1,'Attended synthetic request','Started assistance','in_progress','2000-01-01')""",
            """INSERT INTO referrals(referral_id,request_id,organization_id,attempt_number,is_backup,status,response_deadline)
               VALUES(14,14,2,1,0,'rejected','2000-01-01'),(16,16,1,1,0,'attended','2000-01-01')""",
            "INSERT INTO attendance_records(attendance_id,referral_id,request_id,first_attended_at) VALUES(16,16,16,'2000-01-02')",
            'INSERT INTO feedback VALUES(1,15,0)',
            """INSERT INTO notifications(user_id,type,title,message,related_request_id,deduplication_key)
               VALUES(1,'system','Alert','Request #14: no eligible partner',14,'unmatched:14'),
                     (4,'system','Private','Representative private message',14,'private-org')""",
        ]:
            connection.execute(text(sql))
    return org_engine


@pytest.fixture
def client(coordinator_engine):
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with patch('app.coordinator.Session',side_effect=lambda unused:LocalSession(coordinator_engine)), \
         patch('app.coordinator.cookie_claims',return_value={'uid':'synthetic-coordinator','email_verified':True}), \
         patch('app.coordinator.mint_cookie',return_value='synthetic-coordinator-cookie'), \
         patch('app.auth.verify_token',return_value={'uid':'synthetic-coordinator','email':'coord@example.test','email_verified':True,'auth_time':time.time()}), \
         patch('app.auth.resolve_identity',return_value=(Identity(1,'coord@example.test','coordinator'),None)):
        yield app.test_client()


def sign_in(client):
    client.set_cookie(COOKIE,'synthetic-coordinator-cookie')


def scalar(engine,sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def test_verified_coordinator_session_rotation_csrf_logout(client):
    assert client.post('/api/auth/coordinator-session',headers={'Authorization':'Bearer synthetic'}).status_code==403
    client.get('/login')
    with client.session_transaction() as session:
        csrf=session['login_csrf']
        session['guest_member_id']=9
    response=client.post('/api/auth/coordinator-session',headers={'Authorization':'Bearer synthetic','X-CSRF-Token':csrf})
    assert response.status_code==200 and response.json['redirect_url']=='/coordinator'
    assert any(COOKIE in value and 'HttpOnly' in value and 'SameSite=Lax' in value for value in response.headers.getlist('Set-Cookie'))
    with client.session_transaction() as session:
        assert 'guest_member_id' not in session
        csrf=session['coordinator_csrf']
    assert client.get('/coordinator').status_code==200
    assert client.get('/coordinator/logout').status_code==403
    assert client.get('/coordinator/logout',query_string={'csrf':csrf}).status_code==302
    assert client.get('/coordinator').status_code==302


def test_recent_login_provider_failure_and_unverified_bearer(client):
    client.get('/login')
    with client.session_transaction() as session:
        headers={'Authorization':'Bearer synthetic','X-CSRF-Token':session['login_csrf']}
    with patch('app.auth.verify_token',return_value={'uid':'coord','email':'coord@example.test','email_verified':False,'auth_time':time.time()}):
        assert client.post('/api/auth/coordinator-session',headers=headers).status_code==403
    with patch('app.auth.verify_token',return_value={'uid':'coord','email':'coord@example.test','email_verified':True,'auth_time':time.time()-1000}):
        assert client.post('/api/auth/coordinator-session',headers=headers).status_code==401
    with patch('app.coordinator.mint_cookie',side_effect=RuntimeError('injected')):
        assert client.post('/api/auth/coordinator-session',headers=headers).status_code==503


def test_no_cookie_or_forged_role_cannot_read_private_requests(client):
    with client.session_transaction() as session:
        session['role']='coordinator'
        session['user_id']=1
    assert client.get('/coordinator').status_code==302
    assert client.get('/coordinator/requests').status_code==302


@pytest.mark.parametrize('claims',[{'uid':'synthetic-member','email_verified':True},
    {'uid':'synthetic-representative','email_verified':True},
    {'uid':'synthetic-coordinator','email_verified':False}])
def test_wrong_role_and_unverified_cookies_denied(client,claims):
    sign_in(client)
    with patch('app.coordinator.cookie_claims',return_value=claims):
        response=client.get('/coordinator/requests')
    assert response.status_code==302
    assert any('Max-Age=0' in value for value in response.headers.getlist('Set-Cookie'))


def test_revoked_cookie_denied(client):
    sign_in(client)
    with patch('app.coordinator.cookie_claims',side_effect=ValueError('revoked')):
        assert client.get('/coordinator').status_code==302


@pytest.mark.parametrize('sql',['UPDATE users SET is_active=0 WHERE user_id=1',
                               'UPDATE users SET role_id=1 WHERE user_id=1'])
def test_sql_activity_and_role_rechecked(client,coordinator_engine,sql):
    sign_in(client)
    with coordinator_engine.begin() as connection:
        connection.execute(text(sql))
    assert client.get('/coordinator/requests').status_code==302


def test_dashboard_real_counts_and_recipient_scoped_alerts(client):
    sign_in(client)
    page=client.get('/coordinator')
    assert page.status_code==200 and page.headers['Cache-Control']=='no-store'
    html=page.get_data(as_text=True)
    assert 'CC-14' in html and 'Request #14: no eligible partner' in html
    assert 'Representative private message' not in html
    assert 'Manual review' in html
    assert 'CC-16' not in html  # Already attended: no outstanding attendance-overdue flag.
    assert html.count('class="stat-number">1</p>')==3  # pending, unmatched, overdue
    assert 'class="stat-number">5</p>' in html


@pytest.mark.parametrize('query,expected,excluded',[
    ('attention=Unmatched','CC-14','CC-15'),
    ('attention=Overdue','CC-14','CC-16'),
    ('attention=Manual+review','CC-15','CC-14'),
    ('status=Completed','CC-15','CC-14'),
    ('org_id=2','CC-14','CC-1'),
    ('priority=Low','','CC-14'),
])
def test_existing_filters(client,query,expected,excluded):
    sign_in(client)
    page=client.get('/coordinator/requests?'+query)
    assert page.status_code==200
    html=page.get_data(as_text=True)
    if expected: assert expected in html
    # Match request references, avoiding CC-1 as a prefix of CC-14.
    assert excluded+'<' not in html


def test_request_details_are_real_and_views_do_not_mutate(client,coordinator_engine):
    sign_in(client)
    before={table:scalar(coordinator_engine,'SELECT COUNT(*) FROM '+table)
            for table in ('service_requests','referrals','event_outbox','notifications','users')}
    html=client.get('/coordinator/requests').get_data(as_text=True)
    assert 'details-14' in html and 'Synthetic details to inspect' in html
    assert 'member@example.test' in html
    assert 'data-confirm-assignment' not in html
    # Keep status and distinct attention reasons, without repeating Unmatched.
    row=html.split('<tr id="request-14">',1)[1].split('</tr>',1)[0]
    assert row.count('>Unmatched</span>')==1
    assert '>Rejected referral</span>' in row and '>Overdue</span>' in row
    assert client.post('/coordinator/requests',data={'org_id':1}).status_code==405
    assert before=={table:scalar(coordinator_engine,'SELECT COUNT(*) FROM '+table) for table in before}


def test_browser_attention_filter_expand_details_and_logout(client,login_browser):
    import threading
    from werkzeug.serving import make_server
    from playwright.sync_api import expect
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':1280,'height':1000})
    context.add_cookies([{'name':COOKIE,'value':'synthetic-coordinator-cookie','url':base}])
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(base+'/coordinator')
        expect(page.locator('h1')).to_have_text('Coordinator Dashboard')
        page.get_by_role('link',name='CC-14',exact=True).click()
        # Existing main.js opens the details reached through #request-14.
        expect(page.locator('#details-14')).to_have_attribute('open','')
        expect(page.locator('#details-14')).to_contain_text('Synthetic details to inspect')
        page.locator('#attention_filter').select_option(label='Unmatched')
        page.get_by_role('button',name='Filter',exact=True).click()
        expect(page.locator('#request-14')).to_be_visible()
        assert page.locator('#request-15').count()==0
        page.get_by_role('link',name='Log Out',exact=True).click()
        expect(page).to_have_url(base+'/login')
        page.goto(base+'/coordinator/requests')
        expect(page).to_have_url(base+'/login')
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()
