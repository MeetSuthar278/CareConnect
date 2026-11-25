"""Approval/rejection uses disposable application records, never live partners."""
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.services.organization_approvals import ApprovalError,decide_application,pending_applications
from app.services.matching import handle_request_created
from conftest import LocalSession
from test_member_workflow import member_engine
from test_organization_workflow import org_engine
from test_coordinator_workflow import coordinator_engine,client,sign_in
from test_login_ui import login_browser


def scalar(engine,sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def change(engine,sql):
    with engine.begin() as connection:
        connection.execute(text(sql))


@pytest.mark.parametrize('action,reason,expected',[('approve',None,'approved'),('reject','Synthetic application rejection','rejected')])
def test_decision_atomic_idempotent_and_notifies_applicant(coordinator_engine,action,reason,expected):
    with LocalSession(coordinator_engine) as database:
        result=decide_application(database,2,1,1,action,reason)
        assert result['status']==expected and not result['already_processed']
        assert decide_application(database,2,1,1,action,reason)['already_processed']
        assert pending_applications(database)==[]
    assert scalar(coordinator_engine,'SELECT status FROM organization_applications WHERE application_id=1')==expected
    assert scalar(coordinator_engine,'SELECT reviewed_by_user_id FROM organization_applications WHERE application_id=1')==1
    assert scalar(coordinator_engine,'SELECT decided_at FROM organization_applications WHERE application_id=1') is not None
    assert scalar(coordinator_engine,'SELECT decision_notes FROM organization_applications WHERE application_id=1')==reason
    assert scalar(coordinator_engine,'SELECT status FROM organizations WHERE organization_id=2')==('approved' if action=='approve' else 'pending')
    assert scalar(coordinator_engine,"SELECT COUNT(*) FROM notifications WHERE deduplication_key='organization-application:1:decision'")==1
    assert scalar(coordinator_engine,"SELECT user_id FROM notifications WHERE deduplication_key='organization-application:1:decision'")==9
    assert scalar(coordinator_engine,"SELECT related_request_id FROM notifications WHERE deduplication_key='organization-application:1:decision'") is None
    assert scalar(coordinator_engine,'SELECT role_id FROM users WHERE user_id=9')==1
    assert scalar(coordinator_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=2')==1


def test_conflicting_decision_preserves_actor_notes_and_time(coordinator_engine):
    with LocalSession(coordinator_engine) as database:
        decide_application(database,2,1,1,'reject','Original reason')
        original=scalar(coordinator_engine,'SELECT decided_at FROM organization_applications WHERE application_id=1')
        for action,reason in [('approve',None),('reject','Changed reason')]:
            with pytest.raises(ApprovalError,match='already decided'):
                decide_application(database,2,1,1,action,reason)
        assert scalar(coordinator_engine,'SELECT decided_at FROM organization_applications WHERE application_id=1')==original
    assert scalar(coordinator_engine,'SELECT decision_notes FROM organization_applications WHERE application_id=1')=='Original reason'


@pytest.mark.parametrize('sql', ['UPDATE users SET is_active=0 WHERE user_id=1',
                               'UPDATE users SET role_id=1 WHERE user_id=1'])
def test_coordinator_permission_rechecked_in_transaction(coordinator_engine,sql):
    change(coordinator_engine,sql)
    with LocalSession(coordinator_engine) as database:
        with pytest.raises(ApprovalError) as error:
            decide_application(database,2,1,1,'approve')
        assert error.value.status==403
    assert scalar(coordinator_engine,'SELECT status FROM organization_applications WHERE application_id=1')=='submitted'


def test_missing_or_mismatched_application_cannot_target_other_org(coordinator_engine):
    with LocalSession(coordinator_engine) as database:
        for org,app in [(1,1),(2,999),(999,1)]:
            with pytest.raises(ApprovalError) as error:
                decide_application(database,org,app,1,'approve')
            assert error.value.status==404


@pytest.mark.parametrize('action,reason',[('suspend',None),('reject',None),('reject',' '),('reject','x'*256)])
def test_decision_validation(coordinator_engine,action,reason):
    with LocalSession(coordinator_engine) as database:
        with pytest.raises(ApprovalError) as error:
            decide_application(database,2,1,1,action,reason)
        assert error.value.status==400


def test_latest_application_only_and_under_review_supported(coordinator_engine):
    change(coordinator_engine,"INSERT INTO organization_applications(application_id,organization_id,submitted_by_user_id,status) VALUES(2,2,9,'under_review')")
    with LocalSession(coordinator_engine) as database:
        applications=pending_applications(database)
        assert [row['application_id'] for row in applications]==[2]
        database.rollback()
        with pytest.raises(ApprovalError,match='newer application'):
            decide_application(database,2,1,1,'approve')
        assert decide_application(database,2,2,1,'approve')['status']=='approved'


def test_notification_failure_rolls_back_approval_then_retry(coordinator_engine):
    with LocalSession(coordinator_engine) as database:
        with patch('app.services.organization_approvals.notify',side_effect=OperationalError('injected',{},Exception())):
            with pytest.raises(OperationalError):
                decide_application(database,2,1,1,'approve')
        assert scalar(coordinator_engine,'SELECT status FROM organizations WHERE organization_id=2')=='pending'
        assert scalar(coordinator_engine,'SELECT reviewed_by_user_id FROM organization_applications WHERE application_id=1') is None
        assert scalar(coordinator_engine,'SELECT decided_at FROM organization_applications WHERE application_id=1') is None
        assert decide_application(database,2,1,1,'approve')['status']=='approved'


def test_rejected_latest_application_not_listed_and_no_application_is_not_fabricated(coordinator_engine):
    change(coordinator_engine,"UPDATE organization_applications SET status='rejected' WHERE application_id=1")
    with LocalSession(coordinator_engine) as database:
        assert pending_applications(database)==[]
    change(coordinator_engine,'DELETE FROM organization_applications')
    with LocalSession(coordinator_engine) as database:
        assert pending_applications(database)==[]
    assert scalar(coordinator_engine,'SELECT status FROM organizations WHERE organization_id=2')=='pending'


@pytest.mark.parametrize('status',['approved','suspended'])
def test_nonpending_organization_cannot_be_decided(coordinator_engine,status):
    change(coordinator_engine,f"UPDATE organizations SET status='{status}' WHERE organization_id=2")
    with LocalSession(coordinator_engine) as database:
        with pytest.raises(ApprovalError,match='not awaiting'):
            decide_application(database,2,1,1,'approve')
    assert scalar(coordinator_engine,'SELECT status FROM organization_applications WHERE application_id=1')=='submitted'


def test_applicant_sees_decision_in_existing_member_bell(client,coordinator_engine):
    with LocalSession(coordinator_engine) as database:
        decide_application(database,2,1,1,'reject','Synthetic application rejection')
    member_client=client.application.test_client()
    member_client.set_cookie('careconnect_member','synthetic-member-cookie')
    with patch('app.member.Session',side_effect=lambda unused:LocalSession(coordinator_engine)), \
         patch('app.member.cookie_claims',return_value={'uid':'synthetic-member','email_verified':False}):
        page=member_client.get('/member')
    assert page.status_code==200
    assert b'Organization application #1: rejected.' in page.data
    assert b'Synthetic application rejection' in page.data
    assert b'Representative private message' not in page.data


def test_approval_enables_future_matching_but_does_not_rematch_old_request(coordinator_engine):
    change(coordinator_engine,"UPDATE organization_services SET status='paused' WHERE organization_id=1")
    with LocalSession(coordinator_engine) as database:
        assert handle_request_created(database,{'request_id':2})=='unmatched'
        decide_application(database,2,1,1,'approve')
        assert scalar(coordinator_engine,'SELECT status FROM service_requests WHERE request_id=2')=='unmatched'
        change(coordinator_engine,"""INSERT INTO service_requests(request_id,member_id,service_id,service_area_id,priority_id,title,description,status,attendance_deadline)
            VALUES(3,9,1,1,1,'Synthetic newly submitted','Synthetic only','submitted','2099-01-01')""")
        assert handle_request_created(database,{'request_id':3})=='matched'
    assert scalar(coordinator_engine,'SELECT organization_id FROM referrals WHERE request_id=3')==2


def test_portal_auth_csrf_parent_validation_and_safe_return(client,coordinator_engine):
    url='/coordinator/organizations/2/decision'
    assert client.get('/coordinator/approvals').status_code==302
    assert client.post(url,data={}).status_code==302
    sign_in(client)
    page=client.get('/coordinator/approvals')
    assert page.status_code==200 and b'Organization Approvals' in page.data
    with client.session_transaction() as session:
        csrf=session['coordinator_csrf']
    data=dict(csrf_token=csrf,application_id=1,action='approve',return_to='https://example.test')
    assert client.post(url,data=dict(data,csrf_token='wrong')).status_code==403
    assert client.post('/coordinator/organizations/1/decision',data=data).status_code==404
    response=client.post(url,data=data)
    assert response.status_code==303 and response.location.endswith('/coordinator/approvals')
    client.post(url,data=data)
    assert scalar(coordinator_engine,"SELECT COUNT(*) FROM notifications WHERE deduplication_key='organization-application:1:decision'")==1
    assert b'No organizations are waiting for approval.' in client.get(response.location).data


def test_browser_rejection_prompt_and_atomic_decision(client,coordinator_engine,login_browser):
    import threading
    from werkzeug.serving import make_server
    from playwright.sync_api import expect
    from app.coordinator import COOKIE
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':1280,'height':1000})
    context.add_cookies([{'name':COOKIE,'value':'synthetic-coordinator-cookie','url':base}])
    page=context.new_page();mode=['confirm_cancel'];errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def dialog_handler(dialog):
        if dialog.type=='confirm':
            dialog.dismiss() if mode[0]=='confirm_cancel' else dialog.accept()
        elif mode[0]=='prompt_cancel': dialog.dismiss()
        else: dialog.accept('Synthetic application decline')
    page.on('dialog',dialog_handler)
    try:
        page.goto(base+'/coordinator')
        page.get_by_role('link',name='Review',exact=True).click()
        page.get_by_role('button',name='Reject',exact=True).click()
        assert scalar(coordinator_engine,'SELECT status FROM organization_applications WHERE application_id=1')=='submitted'
        mode[0]='prompt_cancel'
        page.get_by_role('button',name='Reject',exact=True).click()
        assert scalar(coordinator_engine,'SELECT status FROM organization_applications WHERE application_id=1')=='submitted'
        mode[0]='reject'
        page.get_by_role('button',name='Reject',exact=True).click()
        expect(page.locator('main')).to_contain_text('Application decision saved.')
        assert scalar(coordinator_engine,'SELECT decision_notes FROM organization_applications WHERE application_id=1')=='Synthetic application decline'
        assert scalar(coordinator_engine,'SELECT status FROM organizations WHERE organization_id=2')=='pending'
        page.goto(base+'/coordinator')
        assert page.get_by_role('link',name='Review',exact=True).count()==0
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()
