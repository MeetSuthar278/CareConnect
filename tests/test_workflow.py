"""Business transaction tests against disposable in-memory SQL, no live services."""
from unittest.mock import patch
import pytest
from sqlalchemy import text
from app.services.matching import handle_request_created
from app.services.notifications import handle_referral_created
from app.services.outbox import dispatch_one


def scalar(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def change(engine, sql):
    with engine.begin() as c:
        c.execute(text(sql))


def test_success_is_atomic_and_preserves_request(session, engine, event):
    assert handle_request_created(session, event) == "matched"
    assert scalar(engine, "SELECT organization_id FROM referrals") == 1
    assert scalar(engine, "SELECT COUNT(*) FROM referral_status_history") == 1
    assert scalar(engine, "SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1") == 1
    assert scalar(engine, "SELECT event_type FROM event_outbox") == "ReferralCreated"
    assert scalar(engine, "SELECT priority_id FROM service_requests WHERE request_id=1") == 1
    assert scalar(engine, "SELECT attendance_deadline FROM service_requests WHERE request_id=1") == "2099-01-01 12:00:00"


@pytest.mark.parametrize("sql", [
    "UPDATE organizations SET status='suspended'",
    "UPDATE organization_services SET status='paused'",
    "UPDATE service_priority_support SET is_supported=0",
    "UPDATE service_priority_support SET priority_id=2",
    "UPDATE organization_services SET service_area_id=2",
    "UPDATE organization_services SET service_id=2",
    "UPDATE organization_services SET current_active_referrals=active_referral_limit",
    "UPDATE services SET is_active=0",
    "UPDATE service_areas SET is_active=0",
])
def test_ineligible_partners_leave_request_unmatched(session, engine, event, sql):
    change(engine, sql)
    assert handle_request_created(session, event) == "unmatched"
    assert scalar(engine, "SELECT COUNT(*) FROM referrals") == 0
    assert scalar(engine, "SELECT status FROM service_requests WHERE request_id=1") == "unmatched"
    assert scalar(engine, "SELECT user_id FROM notifications") == 1


def test_duplicate_request_event_has_no_duplicate_effects(session, engine, event):
    handle_request_created(session, event)
    event["event_id"] = "different-id-same-business-action"
    assert handle_request_created(session, event) == "already_processed"
    assert scalar(engine, "SELECT COUNT(*) FROM referrals") == 1
    assert scalar(engine, "SELECT COUNT(*) FROM event_outbox") == 1
    assert scalar(engine, "SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1") == 1


def test_duplicate_unmatched_event_has_one_alert(session, engine, event):
    change(engine, "UPDATE organizations SET status='pending'")
    handle_request_created(session, event)
    handle_request_created(session, event)
    assert scalar(engine, "SELECT COUNT(*) FROM notifications") == 1


def test_outbox_failure_rolls_back_matching(session, engine, event):
    with patch("app.services.matching.enqueue", side_effect=RuntimeError("injected failure")):
        with pytest.raises(RuntimeError):
            handle_request_created(session, event)
    assert scalar(engine, "SELECT COUNT(*) FROM referrals") == 0
    assert scalar(engine, "SELECT COUNT(*) FROM referral_status_history") == 0
    assert scalar(engine, "SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1") == 0
    assert scalar(engine, "SELECT status FROM service_requests WHERE request_id=1") == "submitted"


def test_expired_request_alerts_without_reserving(session, engine, event):
    change(engine, "UPDATE service_requests SET attendance_deadline='2000-01-01 00:00:00'")
    assert handle_request_created(session, event) == "unmatched"
    assert scalar(engine, "SELECT COUNT(*) FROM referrals") == 0
    assert scalar(engine, "SELECT COUNT(*) FROM notifications") == 1


def test_missing_coordinator_rolls_back_unmatched(session, engine, event):
    change(engine, "UPDATE organizations SET status='pending'")
    change(engine, "UPDATE users SET is_active=0 WHERE user_id=1")
    with pytest.raises(RuntimeError, match="coordinator"):
        handle_request_created(session, event)
    assert scalar(engine, "SELECT status FROM service_requests WHERE request_id=1") == "submitted"


def history(engine, org, status, attendance=None):
    with engine.begin() as c:
        rid = 100 + org
        c.execute(text("INSERT INTO service_requests(request_id,status,attendance_deadline) VALUES(:id,'completed','2020-01-01 12:00:00')"), {"id":rid})
        c.execute(text("INSERT INTO referrals(referral_id,request_id,organization_id,attempt_number,status) VALUES(:id,:id,:org,1,:status)"), {"id":rid,"org":org,"status":status})
        if attendance:
            c.execute(text("INSERT INTO attendance_records VALUES(:id,:id,:at)"), {"id":rid,"at":attendance})


def test_acceptance_breaks_equal_workload_tie(session, engine, event):
    change(engine, "UPDATE organization_services SET current_active_referrals=0")
    history(engine, 1, "rejected")
    history(engine, 2, "completed", "2020-01-01 10:00:00")
    handle_request_created(session, event)
    assert scalar(engine, "SELECT organization_id FROM referrals WHERE request_id=1") == 2


def test_on_time_breaks_equal_acceptance_tie(session, engine, event):
    change(engine, "UPDATE organization_services SET current_active_referrals=0")
    history(engine, 1, "completed", "2020-01-01 14:00:00")
    history(engine, 2, "completed", "2020-01-01 10:00:00")
    handle_request_created(session, event)
    assert scalar(engine, "SELECT organization_id FROM referrals WHERE request_id=1") == 2


def test_workload_outranks_acceptance(session, engine, event):
    history(engine, 1, "rejected")
    history(engine, 2, "completed", "2020-01-01 10:00:00")
    handle_request_created(session, event)
    assert scalar(engine, "SELECT organization_id FROM referrals WHERE request_id=1") == 1


def referral_event(engine, event):
    return dict(event, event_type="ReferralCreated", payload={"referral_id":scalar(engine, "SELECT referral_id FROM referrals WHERE request_id=1")})


def test_notification_created_once_for_representative(session, engine, event):
    handle_request_created(session, event)
    notification = referral_event(engine, event)
    handle_referral_created(session, notification)
    handle_referral_created(session, dict(notification, event_id="redelivery-new-id"))
    assert scalar(engine, "SELECT COUNT(*) FROM notifications") == 1
    assert scalar(engine, "SELECT user_id FROM notifications") == 4
    assert scalar(engine, "SELECT type FROM notifications") == "referral_sent"


def test_notification_missing_recipient_is_retryable(session, engine, event):
    handle_request_created(session, event)
    notification = referral_event(engine, event)
    change(engine, "UPDATE users SET is_active=0 WHERE user_id=4")
    with pytest.raises(RuntimeError, match="representative"):
        handle_referral_created(session, notification)
    assert scalar(engine, "SELECT COUNT(*) FROM notifications") == 0


def test_outbox_retries_same_event_id(session, engine, event):
    handle_request_created(session, event)
    original = scalar(engine, "SELECT event_id FROM event_outbox")
    with patch("app.services.outbox.publish_event", side_effect=RuntimeError("broker unavailable")):
        assert dispatch_one(session)
    assert scalar(engine, "SELECT attempts FROM event_outbox") == 1
    assert scalar(engine, "SELECT published_at FROM event_outbox") is None
    change(engine, "UPDATE event_outbox SET available_at='2000-01-01 00:00:00'")
    with patch("app.services.outbox.publish_event") as publish:
        assert dispatch_one(session)
        assert publish.call_args.kwargs["event_id"] == original
    assert scalar(engine, "SELECT published_at FROM event_outbox") is not None
    assert not dispatch_one(session)


def test_api_creates_request_and_outbox_together(session, engine):
    from flask import Flask
    from types import SimpleNamespace
    from app.requests import requests_bp
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(requests_bp)
    with patch("app.requests.db", SimpleNamespace(session=session)):
        response = app.test_client().post("/api/requests", json={
            "service_id":1,"service_area_id":1,"priority_id":1,
            "title":"API demo","description":"Synthetic test request"})
    assert response.status_code == 201
    assert scalar(engine, "SELECT COUNT(*) FROM event_outbox WHERE event_type='ServiceRequestCreated'") == 1
    assert scalar(engine, "SELECT COUNT(*) FROM service_requests") == 2


def test_api_outbox_failure_does_not_leave_request(session, engine):
    from flask import Flask
    from types import SimpleNamespace
    from app.requests import requests_bp
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(requests_bp)
    with patch("app.requests.db", SimpleNamespace(session=session)), patch(
            "app.requests.enqueue", side_effect=RuntimeError("outbox failed")):
        response = app.test_client().post("/api/requests", json={
            "service_id":1,"service_area_id":1,"priority_id":1,
            "title":"API demo","description":"Synthetic test request"})
    assert response.status_code == 500
    assert scalar(engine, "SELECT COUNT(*) FROM service_requests") == 1
