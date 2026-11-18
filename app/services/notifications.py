"""In-app delivery using stable business keys, serialized by request."""
from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert

from app.models import Notification


def notify(session, user_ids, request_id, key, title, message, kind="system"):
    for user_id in sorted(set(user_ids)):
        statement = insert(Notification).values(
            user_id=user_id, related_request_id=request_id,
            deduplication_key=key, title=title, message=message, type=kind,
        )
        # Do not suppress other integrity errors with INSERT IGNORE.
        session.execute(statement.on_duplicate_key_update(
            notification_id=Notification.notification_id,
        ))


def alert_coordinators(session, request_id, reason):
    users = session.execute(text("""
        SELECT u.user_id FROM users u JOIN roles r ON r.role_id = u.role_id
        WHERE u.is_active = TRUE AND r.role_name = 'coordinator'
    """)).scalars().all()
    if not users:
        raise RuntimeError("No active coordinator available for unmatched alert")
    notify(session, users, request_id, f"unmatched:{request_id}",
           "Request needs coordinator assistance", f"Request #{request_id}: {reason}")


def handle_referral_created(session, event):
    referral_id = event["payload"].get("referral_id")
    if type(referral_id) is not int or referral_id <= 0:
        raise ValueError("ReferralCreated requires a positive referral_id")
    with session.begin():
        request = session.execute(text(
            "SELECT request_id FROM service_requests WHERE request_id = :id FOR UPDATE"
        ), {"id": event["request_id"]}).first()
        if request is None:
            raise RuntimeError("Notification request does not exist")
        referral = session.execute(text("""
            SELECT organization_id FROM referrals
            WHERE referral_id = :referral AND request_id = :request
        """), {"referral": referral_id, "request": event["request_id"]}).first()
        if referral is None:
            raise RuntimeError("Notification referral does not belong to request")
        representatives = session.execute(text("""
            SELECT u.user_id, rep.is_primary_contact
            FROM organization_representatives rep
            JOIN users u ON u.user_id = rep.user_id
            JOIN roles r ON r.role_id = u.role_id
            WHERE rep.organization_id = :org AND u.is_active = TRUE
              AND r.role_name = 'representative'
            ORDER BY u.user_id
        """), {"org": referral.organization_id}).all()
        primary = [r.user_id for r in representatives if r.is_primary_contact]
        recipients = primary or [r.user_id for r in representatives]
        if not recipients:
            raise RuntimeError("No active representative available for referral notification")
        notify(session, recipients, event["request_id"], f"referral-created:{referral_id}",
               "New referral request",
               f"Referral #{referral_id} for request #{event['request_id']} is awaiting response.",
               "referral_sent")
