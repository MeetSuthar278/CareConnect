
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re

from flask import Blueprint, request, jsonify, current_app, session, redirect, url_for
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app import db
from app.services.outbox import enqueue
from app.models import (
    User,
    Service,
    ServiceArea,
    PriorityLevel,
    ServiceRequest
)
from app.models import EventOutbox
from app.services.guest_requests import GuestRequestError, create_guest_request, owned_request

requests_bp = Blueprint("requests", __name__)


@requests_bp.post("/api/guest/requests")
def submit_guest_request():
    from app.frontend import request_page
    supplied = request.form.get("csrf_token", "")
    expected = session.get("guest_csrf", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        return request_page("Your form session expired. Reload the form and try again.", 403)
    nonce = request.form.get("submission_nonce", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32}", nonce):
        return request_page("Reload the form before submitting.", 400)
    key = "guest-request:" + hashlib.sha256((expected + "|" + nonce).encode()).hexdigest()
    try:
        with Session(db.engine) as database:
            request_id, owner = create_guest_request(database, request.form,
                                                      session.get("guest_member_id"), key)
    except GuestRequestError as error:
        return request_page(str(error), error.status)
    except IntegrityError:
        # Concurrent copies of the same form may race the email/outbox unique keys.
        with Session(db.engine) as database:
            saved = database.execute(select(EventOutbox).where(
                EventOutbox.deduplication_key == key)).scalar_one_or_none()
            if saved is None:
                return request_page("Request could not be saved. Check your contact email and try again.", 409)
            request_id, owner = saved.request_id, saved.payload["member_id"]
    except SQLAlchemyError:
        current_app.logger.error("Guest request database transaction failed")
        return request_page("Request could not be saved. Please try again later.", 503)
    session["guest_member_id"] = owner
    return redirect(url_for("request_confirmation", reference=f"CC-{request_id}"), code=303)


@requests_bp.get("/api/guest/requests/<int:request_id>")
def guest_request_status(request_id):
    with Session(db.engine) as database:
        record = owned_request(database, request_id, session.get("guest_member_id"))
    if record is None:
        return jsonify(error="Request not found"), 404
    # This session-owned status API never falls back to demo member 9.
    return jsonify(request_id=request_id, status=record["status"],
                   display_status=record["display_status"],
                   response_deadline=_iso_utc(record["response_deadline"]),
                   attendance_deadline=_iso_utc(record["attendance_deadline"]))


def _iso_utc(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


@requests_bp.get("/api/requests/status")
def request_status():
    return jsonify({
        "module": "service requests",
        "status": "ready"
    }), 200


def get_demo_member_id():
    if current_app.config.get('HOSTED_MODE'):
        return None
    # Temporary local demo only.
    # Replace with authenticated user ID before production.
    if not current_app.debug and not current_app.testing:
        return None

    return current_app.config.get("DEMO_MEMBER_ID", 9)


@requests_bp.post("/api/requests")
def create_request():
    member_id = get_demo_member_id()

    if member_id is None:
        return jsonify({
            "error": "Authentication required"
        }), 401

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400

    required_ids = [
        "service_id",
        "service_area_id",
        "priority_id"
    ]

    for field in required_ids:
        value = data.get(field)

        if type(value) is not int or value <= 0:
            return jsonify({
                "error": f"{field} must be a positive integer"
            }), 400

    title = data.get("title")
    description = data.get("description")

    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 150:
        return jsonify({"error": "Invalid title"}), 400

    if not isinstance(description, str) or not description.strip():
        return jsonify({"error": "Description is required"}), 400

    member = db.session.get(User, member_id)
    service = db.session.get(Service, data["service_id"])
    area = db.session.get(ServiceArea, data["service_area_id"])
    priority = db.session.get(PriorityLevel, data["priority_id"])

    if member is None or member.role_id != 1 or not member.is_active:
        return jsonify({"error": "Invalid member"}), 403

    if service is None or not service.is_active:
        return jsonify({"error": "Invalid or inactive service"}), 400

    if area is None or not area.is_active:
        return jsonify({"error": "Invalid or inactive area"}), 400

    if priority is None:
        return jsonify({"error": "Invalid priority"}), 400

    # Calculate attendance deadline in UTC.
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=priority.deadline_hours)

    new_request = ServiceRequest(
        member_id=member_id,
        service_id=service.service_id,
        service_area_id=area.area_id,
        priority_id=priority.priority_id,
        title=title.strip(),
        description=description.strip(),
        status="submitted",
        attendance_deadline=deadline.replace(tzinfo=None)
    )

    # Save request and outbound event atomically; dispatcher publishes later.
    try:
        db.session.add(new_request)
        db.session.flush()
        enqueue(
            db.session, "ServiceRequestCreated", new_request.request_id,
            {"member_id": member_id, "service_id": service.service_id,
             "area_id": area.area_id, "priority": priority.level_name,
             "attendance_deadline": deadline.isoformat()},
            f"request-created:{new_request.request_id}",
        )
        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Request creation failed")

        return jsonify({
            "error": "Could not create request"
        }), 500

    # Event is durably queued; matching is asynchronous.
    return jsonify({
        "request_id": new_request.request_id,
        "status": new_request.status,
        "attendance_deadline": deadline.isoformat()
    }), 201


# Get all service requests belonging to the current member.
@requests_bp.get("/api/requests")
def get_requests():
    member_id = get_demo_member_id()

    if member_id is None:
        return jsonify({
            "error": "Authentication required"
        }), 401

    records = (
        db.session.query(ServiceRequest)
        .filter_by(member_id=member_id)
        .order_by(ServiceRequest.request_id.desc())
        .all()
    )

    return jsonify([
        {
            "request_id": r.request_id,
            "title": r.title,
            "status": r.status,
            "priority_id": r.priority_id,
            "attendance_deadline":
                r.attendance_deadline.isoformat() + "Z"
        }
        for r in records
    ]), 200


# Get a particular service request.
@requests_bp.get("/api/requests/<int:request_id>")
def get_request(request_id):
    member_id = get_demo_member_id()

    if member_id is None:
        return jsonify({
            "error": "Authentication required"
        }), 401

    record = db.session.get(ServiceRequest, request_id)

    if record is None or record.member_id != member_id:
        return jsonify({
            "error": "Request not found"
        }), 404

    return jsonify({
        "request_id": record.request_id,
        "title": record.title,
        "description": record.description,
        "status": record.status,
        "service_id": record.service_id,
        "service_area_id": record.service_area_id,
        "priority_id": record.priority_id,
        "attendance_deadline":
            record.attendance_deadline.isoformat() + "Z"
    }), 200
