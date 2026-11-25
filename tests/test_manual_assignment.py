"""Manual rescue preserves request/SLA and commits referral/capacity/outbox together."""
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.services.manual_assignment import assign_request,assignment_choices,AssignmentError
from app.services.notifications import handle_referral_created
from conftest import LocalSession
from test_coordinator_workflow import coordinator_engine,client,sign_in,scalar
from test_organization_workflow import org_engine
from test_member_workflow import member_engine


@pytest.fixture
def manual_engine(coordinator_engine):
    with coordinator_engine.begin() as connection:
        connection.execute(text("UPDATE service_requests SET attendance_deadline='2099-01-01' WHERE request_id=14"))
    return coordinator_engine


def test_manual_assignment_duplicate_and_notification(manual_engine):
    with LocalSession(manual_engine) as database:
        choices,source=assignment_choices(database,14)
        assert [row['org_id'] for row in choices]==[1] and source==14
        database.rollback()
        result=assign_request(database,14,1,1,14)
        assert not result['already_processed']
        assert assign_request(database,14,1,1,14)['already_processed']
    assert scalar(manual_engine,'SELECT status FROM service_requests WHERE request_id=14')=='matched'
    assert scalar(manual_engine,'SELECT COUNT(*) FROM referrals WHERE request_id=14')==2
    assert scalar(manual_engine,'SELECT attempt_number FROM referrals WHERE referral_id='+str(result['referral_id']))==2
    assert scalar(manual_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1')==2
    assert scalar(manual_engine,'SELECT priority_id FROM service_requests WHERE request_id=14')==1
    assert str(scalar(manual_engine,'SELECT attendance_deadline FROM service_requests WHERE request_id=14')).startswith('2099-01-01')
    assert scalar(manual_engine,"SELECT COUNT(*) FROM referral_status_history WHERE changed_by_user_id=1 AND notes='Coordinator manual assignment'")==1
    with manual_engine.connect() as connection:
        event_id=connection.execute(text("SELECT event_id FROM event_outbox WHERE request_id=14 AND event_type='ReferralCreated'")).scalar_one()
    event={'event_id':event_id,'request_id':14,'payload':{'referral_id':result['referral_id']}}
    with LocalSession(manual_engine) as database:
        handle_referral_created(database,event)
        handle_referral_created(database,event)
    assert scalar(manual_engine,"SELECT COUNT(*) FROM notifications WHERE deduplication_key='referral-created:"+str(result['referral_id'])+"'")==1


@pytest.mark.parametrize('sql,org,source',[
    ("UPDATE organizations SET status='suspended' WHERE organization_id=1",1,14),
    ("UPDATE organization_services SET status='paused' WHERE organization_service_id=1",1,14),
    ('UPDATE organization_services SET current_active_referrals=active_referral_limit WHERE organization_service_id=1',1,14),
    ('UPDATE service_priority_support SET is_supported=FALSE WHERE organization_service_id=1',1,14),
    ("UPDATE service_requests SET attendance_deadline='2000-01-01' WHERE request_id=14",1,14),
    ("UPDATE service_requests SET status='completed' WHERE request_id=14",1,14),
    ("UPDATE service_requests SET status='in_progress' WHERE request_id=14",1,14),
    ('SELECT 1',2,14),('SELECT 1',1,0),
])
def test_ineligible_or_stale_actions_cannot_reserve(manual_engine,sql,org,source):
    with manual_engine.begin() as connection:
        connection.execute(text(sql))
    before=scalar(manual_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1')
    with LocalSession(manual_engine) as database,pytest.raises(AssignmentError):
        assign_request(database,14,org,1,source)
    assert scalar(manual_engine,'SELECT COUNT(*) FROM referrals WHERE request_id=14')==1
    assert scalar(manual_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1')==before


def test_three_attempts_and_active_referral_blocked(manual_engine):
    with LocalSession(manual_engine) as database,pytest.raises(AssignmentError):
        assign_request(database,1,2,1,0)
    with manual_engine.begin() as connection:
        connection.execute(text("""INSERT INTO referrals(referral_id,request_id,organization_id,attempt_number,is_backup,status,response_deadline)
            VALUES(30,14,3,2,1,'rejected','2000-01-01'),(31,14,4,3,1,'timed_out','2000-01-01')"""))
    with LocalSession(manual_engine) as database:
        assert assignment_choices(database,14)[0]==[]
        database.rollback()
        with pytest.raises(AssignmentError,match='Three'):
            assign_request(database,14,1,1,31)


def test_first_assignment_and_role_recheck(manual_engine):
    with manual_engine.begin() as connection:
        connection.execute(text("""INSERT INTO service_requests(request_id,member_id,service_id,service_area_id,priority_id,title,status,attendance_deadline)
            VALUES(20,9,1,1,1,'Unmatched without prior referral','unmatched','2099-01-01')"""))
    with LocalSession(manual_engine) as database:
        with pytest.raises(AssignmentError) as error:
            assign_request(database,20,1,4,0)
        assert error.value.status==403
        assert not assign_request(database,20,1,1,0)['already_processed']
    assert scalar(manual_engine,'SELECT attempt_number FROM referrals WHERE request_id=20')==1


def test_outbox_failure_rolls_back_referral_history_capacity(manual_engine):
    before=scalar(manual_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1')
    with LocalSession(manual_engine) as database:
        with patch('app.services.matching.enqueue',side_effect=OperationalError('synthetic',{},Exception())):
            with pytest.raises(OperationalError):
                assign_request(database,14,1,1,14)
    assert scalar(manual_engine,'SELECT status FROM service_requests WHERE request_id=14')=='unmatched'
    assert scalar(manual_engine,'SELECT COUNT(*) FROM referrals WHERE request_id=14')==1
    assert scalar(manual_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1')==before


def test_native_choices_csrf_and_duplicates(client,manual_engine):
    url='/coordinator/requests/14/assign'
    assert client.post(url).status_code==302
    sign_in(client)
    page=client.get('/coordinator/requests')
    assert b'data-confirm-assignment="CC-14"' in page.data
    with client.session_transaction() as session:
        data=dict(csrf_token=session['coordinator_csrf'],org_id='1',expected_referral_id='14')
    assert client.post(url,data=dict(data,csrf_token='wrong')).status_code==403
    assert client.post(url,data=dict(data,priority_id='3')).status_code==400
    response=client.post(url,data=data)
    assert response.status_code==303 and response.location.endswith('#request-14')
    assert client.post(url,data=data).status_code==303
    assert scalar(manual_engine,'SELECT COUNT(*) FROM referrals WHERE request_id=14')==2
