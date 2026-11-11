"""Initial and backup matching with shared eligibility and ranking rules."""
from datetime import timedelta

from sqlalchemy import select, text

from app.models import Referral, ReferralStatusHistory, ServiceRequest
from app.services.notifications import alert_coordinators
from app.services.outbox import enqueue, utcnow


def _lock_request(session, request_id):
    request = session.execute(select(ServiceRequest).where(
        ServiceRequest.request_id == request_id).with_for_update()).scalar_one_or_none()
    if request is None:
        raise RuntimeError("Matching event references a missing request")
    return request


def handle_request_created(session, event):
    with session.begin():
        request = _lock_request(session, event["request_id"])
        if request.status != "submitted":
            return "already_processed"
        existing = session.execute(select(Referral.referral_id).where(
            Referral.request_id == request.request_id).limit(1)).first()
        if existing:
            # An old initial event must never race a pending rejection backup.
            return "already_processed"
        return _match_locked(session, request, attempt_number=1)


def handle_referral_rejected(session, event):
    return _handle_failed_referral(session, event, "rejected")


def handle_acceptance_timed_out(session, event):
    return _handle_failed_referral(session, event, "timed_out")


def _handle_failed_referral(session, event, expected_status):
    referral_id = event["payload"].get("referral_id")
    if type(referral_id) is not int or referral_id <= 0:
        raise ValueError("Backup event requires a positive referral_id")
    with session.begin():
        request = _lock_request(session, event["request_id"])
        attempts = session.execute(select(Referral).where(
            Referral.request_id == request.request_id)
            .order_by(Referral.attempt_number).with_for_update()).scalars().all()
        source = next((r for r in attempts if r.referral_id == referral_id), None)
        if source is None or source.status != expected_status:
            raise RuntimeError("Backup event does not identify the expected failed request referral")
        if expected_status == "timed_out" and source.response_deadline > utcnow():
            raise RuntimeError("Timeout event references an unexpired referral")
        if (event["payload"].get("organization_id") != source.organization_id
                or event["payload"].get("attempt_number") != source.attempt_number):
            raise ValueError("Backup payload does not match saved referral")
        # Latest source + pending state is a durable business-action idempotency key.
        # Replaying an older event must not advance a newer rejected attempt.
        if attempts[-1].referral_id != source.referral_id or request.status != "submitted":
            return "already_processed"
        if any(r.status in {"sent", "accepted", "attended"} for r in attempts):
            return "already_processed"
        if [r.attempt_number for r in attempts] != list(range(1, len(attempts) + 1)):
            raise RuntimeError("Referral attempt history is inconsistent; coordinator review required")
        if source.attempt_number >= 3:
            request.status = "unmatched"
            alert_coordinators(session, request.request_id, "Three referral attempts exhausted")
            return "unmatched"
        return _match_locked(session, request, attempt_number=source.attempt_number + 1)


def eligible_offerings(session, request, *, lock=False):
    """Same eligibility for automatic matching and coordinator selection."""
    return session.execute(text("""
        SELECT os.organization_service_id, os.organization_id,
               os.current_active_referrals
        FROM organization_services os
        JOIN organizations o ON o.organization_id = os.organization_id
        JOIN services s ON s.service_id = os.service_id
        JOIN service_areas a ON a.area_id = os.service_area_id
        JOIN service_priority_support p
          ON p.organization_service_id = os.organization_service_id
        WHERE o.status = 'approved' AND os.status = 'active'
          AND s.is_active = TRUE AND a.is_active = TRUE
          AND p.is_supported = TRUE AND p.priority_id = :priority
          AND os.service_id = :service AND os.service_area_id = :area
          AND os.current_active_referrals < os.active_referral_limit
          AND NOT EXISTS (
              SELECT 1 FROM referrals prior
              WHERE prior.request_id = :request_id
                AND prior.organization_id = os.organization_id
          )
        ORDER BY os.organization_service_id
    """ + (" FOR UPDATE" if lock else "")), {"priority": request.priority_id, "service": request.service_id,
            "area": request.service_area_id, "request_id": request.request_id}).all()


def _match_locked(session, request, attempt_number):
    """Caller owns the transaction and request lock; never reset priority/SLA."""
    now = utcnow()
    if request.attendance_deadline <= now:
        request.status = "unmatched"
        alert_coordinators(session, request.request_id, "Attendance deadline has already passed")
        return "unmatched"
    # Wait in a consistent order rather than skipping a busy, better-ranked partner.
    candidates = eligible_offerings(session, request, lock=True)
    if not candidates:
        request.status = "unmatched"
        alert_coordinators(session, request.request_id, "No eligible partner with available capacity")
        return "unmatched"

    def ranking(candidate):
        rates = session.execute(text("""
            SELECT
              COALESCE(AVG(r.status IN ('accepted','attended','completed')), 0) AS acceptance,
              COALESCE(SUM(CASE WHEN ar.first_attended_at <= sr.attendance_deadline
                                THEN 1 ELSE 0 END) /
                NULLIF(SUM(CASE WHEN ar.attendance_id IS NOT NULL
                  OR (r.status IN ('accepted','attended','completed')
                      AND sr.attendance_deadline <= :now) THEN 1 ELSE 0 END), 0), 0) AS on_time
            FROM referrals r JOIN service_requests sr ON sr.request_id = r.request_id
            LEFT JOIN attendance_records ar ON ar.referral_id = r.referral_id
            WHERE r.organization_id = :org
        """), {"org": candidate.organization_id, "now": now}).one()
        return (candidate.current_active_referrals, -rates.acceptance,
                -rates.on_time, candidate.organization_id, candidate.organization_service_id)

    selected = min(candidates, key=ranking)
    now = utcnow()
    if request.attendance_deadline <= now:
        request.status = "unmatched"
        alert_coordinators(session, request.request_id, "Attendance deadline passed while matching")
        return "unmatched"
    return create_referral_locked(session,request,selected,attempt_number,now=now)


def create_referral_locked(session,request,selected,attempt_number,*,actor=None,notes=None,now=None):
    """Caller holds request and eligibility locks; all effects share its transaction."""
    now = now or utcnow()
    if request.attendance_deadline <= now:
        raise RuntimeError('Attendance deadline passed; reload before assigning')
    # Conditional update is a second guard against overbooking.
    reserved = session.execute(text("""
        UPDATE organization_services
        SET current_active_referrals = current_active_referrals + 1
        WHERE organization_service_id = :id AND status = 'active'
          AND current_active_referrals < active_referral_limit
    """), {"id": selected.organization_service_id})
    if reserved.rowcount != 1:
        raise RuntimeError("Capacity changed; retry matching")
    referral = Referral(
        request_id=request.request_id, organization_id=selected.organization_id,
        attempt_number=attempt_number, is_backup=attempt_number > 1, status="sent",
        # A two-hour demo response window never extends attendance SLA.
        response_deadline=min(request.attendance_deadline, now + timedelta(hours=2)),
    )
    session.add(referral)
    session.flush()
    session.add(ReferralStatusHistory(
        referral_id=referral.referral_id, old_status=None, new_status="sent",
        notes=notes or ("Initial automatic matching" if attempt_number == 1 else "Automatic backup after partner failure"),
        changed_by_user_id=actor,
    ))
    request.status = "matched"
    enqueue(session, "ReferralCreated", request.request_id,
            {"referral_id": referral.referral_id,
             "organization_id": selected.organization_id},
            f"referral-created:{referral.referral_id}")
    return "matched"
