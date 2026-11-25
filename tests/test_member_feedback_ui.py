"""Cookie-authenticated feedback form; isolated SQL and no live Firebase/email."""
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.serving import make_server

from app import create_app
from app.member import COOKIE
from app.services.referrals import accept_referral
from app.services.attendance import record_attendance
from app.services.completions import complete_referral
from conftest import LocalSession
from test_member_workflow import member_engine
from test_organization_workflow import org_engine
from test_login_ui import login_browser


@pytest.fixture
def feedback_engine(org_engine):
    with org_engine.begin() as connection:
        connection.execute(text('''CREATE TABLE feedback(feedback_id INTEGER PRIMARY KEY,
            request_id INTEGER NOT NULL UNIQUE,member_id INTEGER NOT NULL,organization_id INTEGER NOT NULL,
            is_helpful BOOLEAN NOT NULL,rating INTEGER,comment TEXT,submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
    with LocalSession(org_engine) as database:
        accept_referral(database,1,4)
        record_attendance(database,1,4)
        complete_referral(database,1,4)
    return org_engine


@pytest.fixture
def client(feedback_engine):
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with patch('app.member.Session',side_effect=lambda unused:LocalSession(feedback_engine)), \
         patch('app.member.cookie_claims',return_value={'uid':'synthetic-member','email_verified':False}):
        yield app.test_client()


def sign_in(client):
    client.set_cookie(COOKIE,'synthetic-member-cookie')
    client.get('/member/requests/1/feedback')
    with client.session_transaction() as session:
        return session['member_csrf']


def scalar(engine,sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


@pytest.mark.parametrize('choice,text_value',[('yes','Yes'),('no','No')])
def test_form_saves_owned_boolean_event_and_summary(client,feedback_engine,choice,text_value):
    csrf=sign_in(client)
    page=client.get('/member/requests/1/feedback')
    assert page.status_code==200 and page.headers['Cache-Control']=='no-store'
    assert b'Was this service helpful?' in page.data and b'name="rating"' not in page.data
    data=dict(csrf_token=csrf,is_helpful=choice,comment=' Synthetic UI feedback ',member_id=4,organization_id=2)
    response=client.post('/member/requests/1/feedback',data=data)
    assert response.status_code==303 and response.location.endswith('/member/requests/1')
    assert scalar(feedback_engine,'SELECT is_helpful FROM feedback')==(choice=='yes')
    assert scalar(feedback_engine,'SELECT member_id FROM feedback')==9
    assert scalar(feedback_engine,'SELECT organization_id FROM feedback')==1
    assert scalar(feedback_engine,'SELECT rating FROM feedback') is None
    assert scalar(feedback_engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='FeedbackSubmitted'")==1
    summary=client.get(response.location).get_data(as_text=True)
    assert 'Helpful: '+text_value in summary and 'Synthetic UI feedback' in summary
    assert 'Leave feedback' not in summary and 'Your rating:' not in summary
    assert client.get('/member/requests/1/feedback').status_code==302
    assert scalar(feedback_engine,'SELECT status FROM service_requests WHERE request_id=1')=='completed'
    assert scalar(feedback_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=1')==0


def test_duplicates_preserve_first_response_and_conflicts_do_not_overwrite(client,feedback_engine):
    csrf=sign_in(client)
    data=dict(csrf_token=csrf,is_helpful='no',comment='Original synthetic feedback')
    assert client.post('/member/requests/1/feedback',data=data).status_code==303
    first_id=scalar(feedback_engine,'SELECT feedback_id FROM feedback')
    event=scalar(feedback_engine,"SELECT event_id FROM event_outbox WHERE event_type='FeedbackSubmitted'")
    assert client.post('/member/requests/1/feedback',data=data).status_code==303
    assert client.post('/member/requests/1/feedback',data=dict(data,is_helpful='yes')).status_code==409
    assert scalar(feedback_engine,'SELECT COUNT(*) FROM feedback')==1
    assert scalar(feedback_engine,'SELECT feedback_id FROM feedback')==first_id
    assert scalar(feedback_engine,"SELECT event_id FROM event_outbox WHERE event_type='FeedbackSubmitted'")==event
    assert scalar(feedback_engine,'SELECT is_helpful FROM feedback')==0


def test_auth_ownership_completed_state_and_bearer_api_contract(client,feedback_engine):
    assert client.get('/member/requests/1/feedback').status_code==302
    csrf=sign_in(client)
    assert client.get('/member/requests/2/feedback').status_code==404
    assert client.post('/member/requests/2/feedback',data=dict(csrf_token=csrf,is_helpful='yes')).status_code==404
    # Existing API remains bearer-only; the new cookie is accepted only by native member routes.
    assert client.post('/api/requests/1/feedback',json={'is_helpful':True}).status_code==401
    with feedback_engine.begin() as connection:
        connection.execute(text("UPDATE service_requests SET status='in_progress' WHERE request_id=1"))
    assert client.get('/member/requests/1/feedback').status_code==409
    assert client.post('/member/requests/1/feedback',data=dict(csrf_token=csrf,is_helpful='yes')).status_code==409
    assert scalar(feedback_engine,'SELECT COUNT(*) FROM feedback')==0


@pytest.mark.parametrize('fields',[{}, {'is_helpful':'true'}, {'is_helpful':'1'},
    {'is_helpful':'yes','rating':'5'}, {'is_helpful':'yes','comment':'x'*2001}])
def test_csrf_and_input_validation(client,feedback_engine,fields):
    csrf=sign_in(client)
    assert client.post('/member/requests/1/feedback',data={'is_helpful':'yes'}).status_code==403
    assert client.post('/member/requests/1/feedback',data=dict(fields,csrf_token=csrf)).status_code==400
    assert scalar(feedback_engine,'SELECT COUNT(*) FROM feedback')==0


def test_sql_failure_retains_form_and_no_feedback_is_inserted(client,feedback_engine):
    csrf=sign_in(client)
    data=dict(csrf_token=csrf,is_helpful='no',comment='Keep this synthetic comment')
    with patch('app.member.submit_feedback',side_effect=OperationalError('injected',{},Exception())):
        response=client.post('/member/requests/1/feedback',data=data)
    assert response.status_code==503 and b'Keep this synthetic comment' in response.data
    assert scalar(feedback_engine,'SELECT COUNT(*) FROM feedback')==0


def test_outbox_failure_rolls_back_form_submission(client,feedback_engine):
    csrf=sign_in(client)
    with patch('app.services.feedback.enqueue',side_effect=OperationalError('injected',{},Exception())):
        assert client.post('/member/requests/1/feedback',data=dict(csrf_token=csrf,is_helpful='yes')).status_code==503
    assert scalar(feedback_engine,'SELECT COUNT(*) FROM feedback')==0
    assert scalar(feedback_engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='FeedbackSubmitted'")==0


def test_browser_feedback_navigation_save_and_escaped_summary(client,feedback_engine,login_browser):
    from playwright.sync_api import expect
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':1280,'height':1000})
    context.add_cookies([{'name':COOKIE,'value':'synthetic-member-cookie','url':base}])
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(base+'/member/requests/1')
        page.get_by_role('link',name='Leave feedback',exact=True).click()
        expect(page.locator('legend')).to_have_text('Was this service helpful?')
        assert page.locator('input[type=radio]').count()==2
        page.get_by_label('No',exact=True).check()
        page.get_by_label('Comment (optional)',exact=True).fill('<script>window.injected=true</script> Synthetic comment')
        page.get_by_role('button',name='Send Feedback',exact=True).click()
        expect(page).to_have_url(base+'/member/requests/1')
        expect(page.locator('main')).to_contain_text('Helpful: No')
        assert page.get_by_role('link',name='Leave feedback',exact=True).count()==0
        assert not page.evaluate('window.injected || false')
        page.reload()
        assert scalar(feedback_engine,'SELECT COUNT(*) FROM feedback')==1
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()
