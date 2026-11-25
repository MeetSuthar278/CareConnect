from unittest.mock import patch
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.services.cancellations import cancel_request,CancellationError
from app.services.matching import handle_request_created
from conftest import LocalSession
from test_member_workflow import member_engine,client,signed_in,scalar


def test_cancel_repeat_and_delayed_matching_event(member_engine):
    with LocalSession(member_engine) as database:
        assert not cancel_request(database,1,9)['already_processed']
        assert cancel_request(database,1,9)['already_processed']
        assert handle_request_created(database,{'request_id':1})=='already_processed'
    assert scalar(member_engine,'SELECT status FROM service_requests WHERE request_id=1')=='cancelled'
    assert scalar(member_engine,'SELECT COUNT(*) FROM referrals')==0
    assert scalar(member_engine,'SELECT COUNT(*) FROM event_outbox')==0


@pytest.mark.parametrize('status',['matched','in_progress','completed'])
def test_active_or_completed_state_cannot_cancel(member_engine,status):
    with member_engine.begin() as connection:
        connection.execute(text('UPDATE service_requests SET status=:status WHERE request_id=1'),{'status':status})
    with LocalSession(member_engine) as database,pytest.raises(CancellationError):
        cancel_request(database,1,9)
    assert scalar(member_engine,'SELECT status FROM service_requests WHERE request_id=1')==status


def test_wrong_owner_missing_and_active_referral_rechecked(member_engine):
    with LocalSession(member_engine) as database:
        for request_id in (2,999):
            with pytest.raises(CancellationError) as error:
                cancel_request(database,request_id,9)
            assert error.value.status==404
    with member_engine.begin() as connection:
        connection.execute(text("INSERT INTO referrals(referral_id,request_id,organization_id,attempt_number,is_backup,status,response_deadline) VALUES(1,1,1,1,0,'sent','2099-01-01')"))
    with LocalSession(member_engine) as database,pytest.raises(CancellationError):
        cancel_request(database,1,9)


def test_csrf_native_route_and_no_owner_override(client,member_engine):
    signed_in(client)
    assert b'Cancel request' in client.get('/member/requests/1').data
    with client.session_transaction() as session:
        data=dict(csrf_token=session['member_csrf'])
    assert client.post('/member/requests/1/cancel',data={}).status_code==403
    assert client.post('/member/requests/1/cancel',data=dict(data,user_id=1)).status_code==400
    assert client.post('/member/requests/2/cancel',data=data).status_code==404
    assert client.post('/member/requests/1/cancel',data=data).status_code==303
    assert client.post('/member/requests/1/cancel',data=data).status_code==303
    assert b'Cancelled' in client.get('/member/requests/1').data


def test_failed_flush_rolls_back(member_engine):
    with LocalSession(member_engine) as database:
        with patch.object(database,'flush',side_effect=OperationalError('synthetic',{},Exception())):
            with pytest.raises(OperationalError):
                cancel_request(database,1,9)
    assert scalar(member_engine,'SELECT status FROM service_requests WHERE request_id=1')=='submitted'
