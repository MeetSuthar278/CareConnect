"""Rejection/backup tests use only disposable in-memory SQL and mocked Firebase."""
from unittest.mock import patch
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app import create_app
from app.auth import Identity
from app.services.matching import handle_request_created, handle_referral_rejected
from app.services.referrals import reject_referral, RejectionError
from conftest import LocalSession


def scalar(engine,sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def change(engine,sql):
    with engine.begin() as c:
        c.execute(text(sql))


def matched(session,engine,event):
    handle_request_created(session,event)
    return scalar(engine,"SELECT referral_id FROM referrals WHERE request_id=1 ORDER BY attempt_number DESC LIMIT 1")


def rejection(engine,referral):
    with engine.connect() as c:
        r=c.execute(text("SELECT request_id,organization_id,attempt_number FROM referrals WHERE referral_id=:id"),{"id":referral}).mappings().one()
    return {"event_id":"rejection-event", "event_type":"ReferralRejected", "event_version":1,
            "request_id":r["request_id"],"payload":{"referral_id":referral,
            "organization_id":r["organization_id"],"attempt_number":r["attempt_number"]}}


def test_rejection_commits_all_effects_once(session,engine,event):
    rid=matched(session,engine,event)
    result=reject_referral(session,rid,4,"Synthetic rejection")
    assert not result["already_processed"]
    assert scalar(engine,"SELECT status FROM referrals")=="rejected"
    assert scalar(engine,"SELECT rejection_reason FROM referrals")=="Synthetic rejection"
    assert scalar(engine,"SELECT responded_at FROM referrals") is not None
    assert scalar(engine,"SELECT current_active_referrals FROM organization_services WHERE organization_id=1")==0
    assert scalar(engine,"SELECT COUNT(*) FROM referral_status_history WHERE new_status='rejected'")==1
    assert scalar(engine,"SELECT changed_by_user_id FROM referral_status_history WHERE new_status='rejected'")==4
    assert scalar(engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='ReferralRejected'")==1
    assert scalar(engine,"SELECT status FROM service_requests WHERE request_id=1")=="submitted"
    assert reject_referral(session,rid,4,"Repeated click")["already_processed"]
    assert scalar(engine,"SELECT current_active_referrals FROM organization_services WHERE organization_id=1")==0
    assert scalar(engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='ReferralRejected'")==1


def test_backup_preserves_sla_priority_history_and_capacity(session,engine,event):
    rid=matched(session,engine,event)
    deadline=scalar(engine,"SELECT attendance_deadline FROM service_requests WHERE request_id=1")
    reject_referral(session,rid,4,"Synthetic rejection")
    followup=rejection(engine,rid)
    assert handle_referral_rejected(session,followup)=="matched"
    assert scalar(engine,"SELECT organization_id FROM referrals WHERE attempt_number=2")==2
    assert scalar(engine,"SELECT is_backup FROM referrals WHERE attempt_number=2")==1
    assert scalar(engine,"SELECT current_active_referrals FROM organization_services WHERE organization_id=2")==2
    assert scalar(engine,"SELECT status FROM referrals WHERE attempt_number=1")=="rejected"
    assert scalar(engine,"SELECT COUNT(*) FROM referral_status_history WHERE new_status='sent'")==2
    assert scalar(engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='ReferralCreated'")==2
    assert scalar(engine,"SELECT attendance_deadline FROM service_requests WHERE request_id=1")==deadline
    assert scalar(engine,"SELECT priority_id FROM service_requests WHERE request_id=1")==1
    followup["event_id"]="duplicate-with-new-id"
    assert handle_referral_rejected(session,followup)=="already_processed"
    assert scalar(engine,"SELECT COUNT(*) FROM referrals")==2


@pytest.mark.parametrize("sql",[
    "UPDATE organizations SET status='pending' WHERE organization_id=2",
    "UPDATE organization_services SET status='paused' WHERE organization_id=2",
    "UPDATE organization_services SET current_active_referrals=active_referral_limit WHERE organization_id=2",
    "UPDATE service_priority_support SET is_supported=0 WHERE organization_service_id=2",
    "UPDATE organization_services SET service_area_id=2 WHERE organization_id=2",
])
def test_no_eligible_backup_escalates_without_reselecting_old_partner(session,engine,event,sql):
    rid=matched(session,engine,event); reject_referral(session,rid,4,"Synthetic rejection")
    change(engine,sql)
    followup=rejection(engine,rid)
    assert handle_referral_rejected(session,followup)=="unmatched"
    assert scalar(engine,"SELECT COUNT(*) FROM referrals")==1
    assert scalar(engine,"SELECT user_id FROM notifications")==1
    assert handle_referral_rejected(session,followup)=="already_processed"
    assert scalar(engine,"SELECT COUNT(*) FROM notifications")==1


def test_three_attempts_and_stale_event_do_not_create_fourth(session,engine,event):
    for sql in [
        "INSERT INTO users VALUES(5,2,'rep2@example.test','demo',1),(6,2,'rep3@example.test','demo',1)",
        "INSERT INTO organization_representatives VALUES(5,2,1),(6,3,1)",
        "INSERT INTO organizations VALUES(3,'approved')",
        "INSERT INTO organization_services VALUES(3,3,1,1,'active',10,2)",
        "INSERT INTO service_priority_support VALUES(3,1,1)",
    ]: change(engine,sql)
    first=matched(session,engine,event)
    reject_referral(session,first,4,"First decline"); old=rejection(engine,first)
    handle_referral_rejected(session,old)
    second=scalar(engine,"SELECT referral_id FROM referrals WHERE attempt_number=2")
    reject_referral(session,second,5,"Second decline")
    assert handle_referral_rejected(session,old)=="already_processed"
    assert scalar(engine,"SELECT COUNT(*) FROM referrals")==2
    handle_referral_rejected(session,rejection(engine,second))
    third=scalar(engine,"SELECT referral_id FROM referrals WHERE attempt_number=3")
    reject_referral(session,third,6,"Third decline")
    assert handle_referral_rejected(session,rejection(engine,third))=="unmatched"
    assert scalar(engine,"SELECT COUNT(*) FROM referrals")==3
    assert scalar(engine,"SELECT status FROM service_requests WHERE request_id=1")=="unmatched"
    assert scalar(engine,"SELECT COUNT(*) FROM notifications")==1


def test_rejection_outbox_failure_rolls_back_everything(session,engine,event):
    rid=matched(session,engine,event)
    with patch("app.services.referrals.enqueue",side_effect=RuntimeError("injected failure")):
        with pytest.raises(RuntimeError): reject_referral(session,rid,4,"Synthetic rejection")
    assert scalar(engine,"SELECT status FROM referrals")=="sent"
    assert scalar(engine,"SELECT current_active_referrals FROM organization_services WHERE organization_id=1")==1
    assert scalar(engine,"SELECT COUNT(*) FROM referral_status_history WHERE new_status='rejected'")==0
    assert scalar(engine,"SELECT responded_at FROM referrals") is None
    assert scalar(engine,"SELECT status FROM service_requests WHERE request_id=1")=="matched"


def test_backup_outbox_failure_can_retry_without_leaking_capacity(session,engine,event):
    rid=matched(session,engine,event); reject_referral(session,rid,4,"Synthetic rejection")
    followup=rejection(engine,rid)
    with patch("app.services.matching.enqueue",side_effect=RuntimeError("injected failure")):
        with pytest.raises(RuntimeError): handle_referral_rejected(session,followup)
    assert scalar(engine,"SELECT COUNT(*) FROM referrals")==1
    assert scalar(engine,"SELECT current_active_referrals FROM organization_services WHERE organization_id=2")==1
    assert handle_referral_rejected(session,followup)=="matched"


@pytest.mark.parametrize("sql",[
    "UPDATE referrals SET response_deadline='2000-01-01 00:00:00'",
    "UPDATE referrals SET status='accepted'",
    "UPDATE organization_services SET current_active_referrals=0 WHERE organization_id=1",
    "UPDATE service_requests SET status='cancelled' WHERE request_id=1",
])
def test_invalid_rejection_state_preserves_capacity(session,engine,event,sql):
    rid=matched(session,engine,event); change(engine,sql)
    before=scalar(engine,"SELECT current_active_referrals FROM organization_services WHERE organization_id=1")
    with pytest.raises(RejectionError): reject_referral(session,rid,4,"Synthetic rejection")
    assert scalar(engine,"SELECT current_active_referrals FROM organization_services WHERE organization_id=1")==before
    assert scalar(engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='ReferralRejected'")==0


def test_expired_original_sla_prevents_backup(session,engine,event):
    rid=matched(session,engine,event); reject_referral(session,rid,4,"Synthetic rejection")
    change(engine,"UPDATE service_requests SET attendance_deadline='2000-01-01 00:00:00'")
    assert handle_referral_rejected(session,rejection(engine,rid))=="unmatched"
    assert scalar(engine,"SELECT COUNT(*) FROM referrals")==1


def test_late_initial_event_cannot_race_backup(session,engine,event):
    rid=matched(session,engine,event); reject_referral(session,rid,4,"Synthetic rejection")
    assert handle_request_created(session,event)=="already_processed"
    assert scalar(engine,"SELECT COUNT(*) FROM referrals")==1
    assert handle_referral_rejected(session,rejection(engine,rid))=="matched"


def test_missing_coordinator_keeps_backup_recoverable(session,engine,event):
    rid=matched(session,engine,event); reject_referral(session,rid,4,"Synthetic rejection")
    change(engine,"UPDATE organizations SET status='pending'")
    change(engine,"UPDATE users SET is_active=0 WHERE user_id=1")
    with pytest.raises(RuntimeError,match="coordinator"):
        handle_referral_rejected(session,rejection(engine,rid))
    assert scalar(engine,"SELECT status FROM service_requests WHERE request_id=1")=="submitted"


def test_wrong_org_and_inactive_representative_cannot_reject(session,engine,event):
    rid=matched(session,engine,event)
    for sql in ["UPDATE organization_representatives SET organization_id=2 WHERE user_id=4",
                "UPDATE users SET is_active=0 WHERE user_id=4"]:
        change(engine,sql)
        with pytest.raises(RejectionError) as error: reject_referral(session,rid,4,"Synthetic rejection")
        assert error.value.status==404
    assert scalar(engine,"SELECT status FROM referrals")=="sent"


def test_missing_referral_and_mismatched_event(session,engine,event):
    with pytest.raises(RejectionError) as error: reject_referral(session,999,4,"Synthetic rejection")
    assert error.value.status==404
    rid=matched(session,engine,event); reject_referral(session,rid,4,"Synthetic rejection")
    followup=rejection(engine,rid); followup["payload"]["organization_id"]=999
    with pytest.raises(ValueError): handle_referral_rejected(session,followup)
    assert scalar(engine,"SELECT COUNT(*) FROM referrals")==1


@pytest.fixture
def reject_client(engine):
    app=create_app({"TESTING":True,"SQLALCHEMY_DATABASE_URI":"sqlite:///:memory:"})
    with patch("app.auth.verify_token",return_value={"uid":"synthetic","email":"rep@example.test","email_verified":True}), \
         patch("app.auth.resolve_identity",return_value=(Identity(4,"rep@example.test","representative",1),None)), \
         patch("app.referrals.Session",side_effect=lambda unused:LocalSession(engine)):
        yield app.test_client()


def test_api_success_and_unauthorized(reject_client,session,engine,event):
    rid=matched(session,engine,event); url=f"/api/referrals/{rid}/reject"
    assert reject_client.post(url,json={"reason":"Synthetic rejection"}).status_code==401
    response=reject_client.post(url,json={"reason":" Synthetic rejection "},headers={"Authorization":"Bearer synthetic"})
    assert response.status_code==200
    assert response.json["status"]=="rejected"
    assert scalar(engine,"SELECT rejection_reason FROM referrals")=="Synthetic rejection"


@pytest.mark.parametrize("reason",[None,"", "   ",True,"x"*256])
def test_api_reason_validation(reject_client,reason):
    assert reject_client.post('/api/referrals/1/reject',json={"reason":reason},headers={"Authorization":"Bearer synthetic"}).status_code==400


def test_api_wrong_role_and_database_failure(reject_client):
    with patch("app.auth.resolve_identity",return_value=(Identity(9,"member@example.test","member"),None)):
        assert reject_client.post('/api/referrals/1/reject',json={"reason":"Demo"},headers={"Authorization":"Bearer synthetic"}).status_code==403
    with patch("app.referrals.reject_referral",side_effect=OperationalError("test",{},Exception("injected failure"))):
        assert reject_client.post('/api/referrals/1/reject',json={"reason":"Demo"},headers={"Authorization":"Bearer synthetic"}).status_code==503


def test_backup_notification_reuses_existing_consumer(session,engine,event):
    from app.services.notifications import handle_referral_created
    change(engine,"INSERT INTO users VALUES(5,2,'rep2@example.test','demo',1)")
    change(engine,"INSERT INTO organization_representatives VALUES(5,2,1)")
    rid=matched(session,engine,event); reject_referral(session,rid,4,"Synthetic rejection")
    handle_referral_rejected(session,rejection(engine,rid))
    backup=scalar(engine,"SELECT referral_id FROM referrals WHERE attempt_number=2")
    notification=dict(event,event_type="ReferralCreated",payload={"referral_id":backup})
    handle_referral_created(session,notification); handle_referral_created(session,notification)
    assert scalar(engine,"SELECT COUNT(*) FROM notifications WHERE user_id=5")==1
    assert scalar(engine,"SELECT type FROM notifications WHERE user_id=5")=="referral_sent"


def test_api_returns_404_for_unowned_referral(reject_client,session,engine,event):
    rid=matched(session,engine,event)
    change(engine,"UPDATE organization_representatives SET organization_id=2 WHERE user_id=4")
    response=reject_client.post(f'/api/referrals/{rid}/reject',json={"reason":"Demo","organization_id":1},headers={"Authorization":"Bearer synthetic"})
    assert response.status_code==404
    assert scalar(engine,"SELECT status FROM referrals")=="sent"


def test_expired_rejection_repeat_is_idempotent_after_first_commit(session,engine,event):
    rid=matched(session,engine,event); reject_referral(session,rid,4,"Demo")
    change(engine,"UPDATE referrals SET response_deadline='2000-01-01 00:00:00'")
    assert reject_referral(session,rid,4,"Repeat")["already_processed"]
    assert scalar(engine,"SELECT current_active_referrals FROM organization_services WHERE organization_id=1")==0


def test_matching_runtime_dispatches_both_events():
    from unittest.mock import Mock
    from app.messaging.worker_runtime import run_consumer
    app=create_app({"TESTING":True,"SQLALCHEMY_DATABASE_URI":"sqlite:///:memory:"})
    initial=Mock(); rejected=Mock()
    def deliver(queue,process):
        process({"event_type":"ServiceRequestCreated"})
        process({"event_type":"ReferralRejected"})
    with patch("app.messaging.worker_runtime.create_app",return_value=app), \
         patch("app.messaging.worker_runtime.consume_events",side_effect=deliver):
        run_consumer("matching_queue",{"ServiceRequestCreated":initial,"ReferralRejected":rejected})
    initial.assert_called_once();rejected.assert_called_once()
