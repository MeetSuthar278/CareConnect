"""Authorized referral responses; every business effect commits together."""
from sqlalchemy import select, text

from app.models import Referral, ReferralStatusHistory, ServiceRequest
from app.services.outbox import enqueue, utcnow


class RejectionError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


class AcceptanceError(RejectionError):
    """A safe, client-facing acceptance validation failure."""


def accept_referral(session, referral_id, user_id):
    with session.begin():
        request_id = session.execute(select(Referral.request_id).where(
            Referral.referral_id == referral_id)).scalar_one_or_none()
        if request_id is None:
            raise AcceptanceError("Referral not found", 404)
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == request_id).with_for_update()).scalar_one_or_none()
        referral = session.execute(select(Referral).where(
            Referral.referral_id == referral_id).with_for_update()).scalar_one_or_none()
        if request is None or referral is None:
            raise AcceptanceError("Referral not found", 404)
        representative = session.execute(text("""
            SELECT rep.organization_id FROM organization_representatives rep
            JOIN users u ON u.user_id = rep.user_id
            JOIN roles r ON r.role_id = u.role_id
            WHERE rep.user_id = :user AND u.is_active = TRUE
              AND r.role_name = 'representative' FOR UPDATE
        """), {"user": user_id}).scalar_one_or_none()
        if representative != referral.organization_id:
            raise AcceptanceError("Referral not found", 404)
        # A retry after a committed acceptance does not change the response timestamp.
        if referral.status == "accepted":
            return {"referral_id": referral_id, "request_id": request_id,
                    "status": "accepted", "already_processed": True}
        now = utcnow()
        if referral.status != "sent" or request.status != "matched":
            raise AcceptanceError("Referral cannot be accepted in its current state")
        if referral.response_deadline <= now:
            raise AcceptanceError("Referral response deadline has passed")
        if request.attendance_deadline <= now:
            raise AcceptanceError("Request attendance deadline has passed")
        if referral.responded_at is not None:
            raise AcceptanceError("Referral response data is inconsistent; coordinator review required")
        reserved = session.execute(text("""
            SELECT current_active_referrals FROM organization_services
            WHERE organization_id=:org AND service_id=:service AND service_area_id=:area
            FOR UPDATE
        """), {"org": referral.organization_id, "service": request.service_id,
                "area": request.service_area_id}).scalar_one_or_none()
        if reserved is None or reserved <= 0:
            raise AcceptanceError("Capacity is inconsistent; coordinator review required")
        # Offering lock contention must not extend the response window.
        now = utcnow()
        if referral.response_deadline <= now or request.attendance_deadline <= now:
            raise AcceptanceError("Referral response or attendance deadline has passed")
        referral.status = "accepted"
        referral.responded_at = now
        session.add(ReferralStatusHistory(
            referral_id=referral_id, old_status="sent", new_status="accepted",
            changed_by_user_id=user_id, notes="Organization accepted referral",
        ))
        # Acceptance retains the reservation. Attendance will advance request progress.
        return {"referral_id": referral_id, "request_id": request_id,
                "status": "accepted", "already_processed": False}


def reject_referral(session, referral_id, user_id, reason):
    with session.begin():
        # Read the parent ID, then follow the same request-first lock order as matching.
        request_id = session.execute(select(Referral.request_id).where(
            Referral.referral_id == referral_id)).scalar_one_or_none()
        if request_id is None:
            raise RejectionError("Referral not found", 404)
        request = session.execute(select(ServiceRequest).where(
            ServiceRequest.request_id == request_id).with_for_update()).scalar_one_or_none()
        referral = session.execute(select(Referral).where(
            Referral.referral_id == referral_id).with_for_update()).scalar_one_or_none()
        if request is None or referral is None:
            raise RejectionError("Referral not found", 404)
        # Recheck SQL identity in this transaction rather than trusting client IDs
        # or an organization claim cached before the request lock was acquired.
        representative = session.execute(text("""
            SELECT rep.organization_id FROM organization_representatives rep
            JOIN users u ON u.user_id = rep.user_id
            JOIN roles r ON r.role_id = u.role_id
            WHERE rep.user_id = :user AND u.is_active = TRUE
              AND r.role_name = 'representative' FOR UPDATE
        """), {"user": user_id}).scalar_one_or_none()
        if representative != referral.organization_id:
            # Do not reveal another organization's referral existence or details.
            raise RejectionError("Referral not found", 404)
        if referral.status == "rejected":
            return {"referral_id": referral_id, "request_id": request_id,
                    "status": "rejected", "already_processed": True}
        now = utcnow()
        if referral.status != "sent" or request.status != "matched":
            raise RejectionError("Referral cannot be rejected in its current state")
        if referral.response_deadline <= now:
            raise RejectionError("Referral response deadline has passed")
        # The baseline identifies an offering uniquely by organization/service/area.
        offering = session.execute(text("""
            SELECT organization_service_id FROM organization_services
            WHERE organization_id = :org AND service_id = :service
              AND service_area_id = :area FOR UPDATE
        """), {"org": referral.organization_id, "service": request.service_id,
                "area": request.service_area_id}).scalar_one_or_none()
        if offering is None:
            raise RejectionError("Referral offering is missing; coordinator review required")
        released = session.execute(text("""
            UPDATE organization_services
            SET current_active_referrals = current_active_referrals - 1
            WHERE organization_service_id = :id AND current_active_referrals > 0
        """), {"id": offering})
        if released.rowcount != 1:
            raise RejectionError("Capacity is inconsistent; coordinator review required")
        referral.status = "rejected"
        referral.responded_at = now
        referral.rejection_reason = reason
        session.add(ReferralStatusHistory(
            referral_id=referral_id, old_status="sent", new_status="rejected",
            changed_by_user_id=user_id, notes=reason,
        ))
        # Reuse submitted as 'awaiting matching'; no new schema status is introduced.
        request.status = "submitted"
        enqueue(session, "ReferralRejected", request_id,
                {"referral_id": referral_id, "organization_id": referral.organization_id,
                 "attempt_number": referral.attempt_number},
                f"referral-rejected:{referral_id}")
        return {"referral_id": referral_id, "request_id": request_id,
                "status": "rejected", "already_processed": False}
