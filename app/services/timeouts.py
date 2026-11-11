"""Acceptance timeout discovery and one atomic transaction per expired referral."""
import logging

from sqlalchemy import select, text

from app.models import Referral, ReferralStatusHistory, ServiceRequest
from app.services.outbox import enqueue, utcnow

logger = logging.getLogger(__name__)


def expired_referral_ids(session, limit=100, referral_ids=None):
    if not 1 <= limit <= 1000:
        raise ValueError("Batch size must be between 1 and 1000")
    query = select(Referral.referral_id).where(
        Referral.status == "sent", Referral.response_deadline <= utcnow())
    if referral_ids is not None:
        query = query.where(Referral.referral_id.in_(referral_ids))
    return session.execute(query.order_by(
        Referral.response_deadline, Referral.referral_id).limit(limit)).scalars().all()


def timeout_referral(session, referral_id):
    """Discovery is only a hint. Recheck locked current state before any mutation."""
    with session.begin():
        request_id = session.execute(select(Referral.request_id).where(
            Referral.referral_id == referral_id)).scalar_one_or_none()
        if request_id is None:
            return False
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == request_id).with_for_update()).scalar_one_or_none()
        referral = session.execute(select(Referral).where(
            Referral.referral_id == referral_id).with_for_update()).scalar_one_or_none()
        if request is None or referral is None:
            return False
        # Do not overwrite acceptance, rejection, cancellation or another scan's work.
        if referral.status != "sent" or request.status != "matched":
            return False
        if referral.response_deadline > utcnow():
            return False
        if referral.responded_at is not None:
            raise RuntimeError("Sent referral already has response data; coordinator review required")
        offering = session.execute(text("""
            SELECT organization_service_id FROM organization_services
            WHERE organization_id=:org AND service_id=:service AND service_area_id=:area
            FOR UPDATE
        """), {"org": referral.organization_id, "service": request.service_id,
                "area": request.service_area_id}).scalar_one_or_none()
        if offering is None:
            raise RuntimeError("Timed-out referral offering is missing; coordinator review required")
        released = session.execute(text("""
            UPDATE organization_services
            SET current_active_referrals=current_active_referrals-1
            WHERE organization_service_id=:id AND current_active_referrals>0
        """), {"id": offering})
        if released.rowcount != 1:
            raise RuntimeError("Capacity is inconsistent; coordinator review required")
        referral.status = "timed_out"
        # No representative responded: do not fabricate responded_at or rejection_reason.
        session.add(ReferralStatusHistory(
            referral_id=referral_id, old_status="sent", new_status="timed_out",
            changed_by_user_id=None, notes="Response deadline passed without an organization response",
        ))
        request.status = "submitted"
        enqueue(session, "AcceptanceTimedOut", request_id,
                {"referral_id": referral_id, "organization_id": referral.organization_id,
                 "attempt_number": referral.attempt_number},
                f"acceptance-timed-out:{referral_id}")
        return True


def scan_once(session_factory, limit=100, referral_ids=None):
    """Independent sessions let one bad record roll back without losing other work."""
    with session_factory() as session:
        candidates = expired_referral_ids(session, limit, referral_ids)
    result = {"examined": len(candidates), "timed_out": 0, "skipped": 0, "failed": 0}
    for referral_id in candidates:
        try:
            with session_factory() as session:
                changed = timeout_referral(session, referral_id)
            result["timed_out" if changed else "skipped"] += 1
        except Exception as error:
            result["failed"] += 1
            logger.error("Timeout processing failed for referral %s (%s); record retained for retry",
                         referral_id, type(error).__name__)
    return result
