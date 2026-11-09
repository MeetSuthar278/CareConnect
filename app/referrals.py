"""Representative-owned referral response APIs."""
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import db
from app.auth import roles_required
from app.services.attendance import AttendanceError, record_attendance
from app.services.completions import CompletionError, complete_referral
from app.services.referrals import (
    RejectionError, reject_referral, AcceptanceError, accept_referral,
)

referrals_bp = Blueprint("referrals", __name__)


@referrals_bp.post("/api/referrals/<int:referral_id>/complete")
@roles_required("representative")
def complete(referral_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="JSON object required"), 400
    try:
        with Session(db.engine) as session:
            result = complete_referral(session, referral_id, g.current_user.user_id,
                                       data.get("outcome", "successful"), data.get("summary_notes"))
        return jsonify(result), 200
    except CompletionError as error:
        return jsonify(error=str(error)), error.status
    except SQLAlchemyError:
        current_app.logger.exception("Service completion transaction failed")
        return jsonify(error="Could not complete service; retry later"), 503


@referrals_bp.post("/api/referrals/<int:referral_id>/attend")
@roles_required("representative")
def attend(referral_id):
    try:
        with Session(db.engine) as session:
            result = record_attendance(session, referral_id, g.current_user.user_id)
        return jsonify(result), 200
    except AttendanceError as error:
        return jsonify(error=str(error)), error.status
    except SQLAlchemyError:
        current_app.logger.exception("Attendance transaction failed")
        return jsonify(error="Could not record attendance; retry later"), 503


@referrals_bp.post("/api/referrals/<int:referral_id>/accept")
@roles_required("representative")
def accept(referral_id):
    try:
        with Session(db.engine) as session:
            result = accept_referral(session, referral_id, g.current_user.user_id)
        return jsonify(result), 200
    except AcceptanceError as error:
        return jsonify(error=str(error)), error.status
    except SQLAlchemyError:
        current_app.logger.exception("Referral acceptance transaction failed")
        return jsonify(error="Could not accept referral; retry later"), 503


@referrals_bp.post("/api/referrals/<int:referral_id>/reject")
@roles_required("representative")
def reject(referral_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="JSON object required"), 400
    reason = data.get("reason")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 255:
        return jsonify(error="Reason must contain 1 to 255 characters"), 400
    try:
        with Session(db.engine) as session:
            result = reject_referral(session, referral_id, g.current_user.user_id, reason.strip())
        # Rejection committed; backup remains asynchronous.
        return jsonify(result), 200
    except RejectionError as error:
        return jsonify(error=str(error)), error.status
    except SQLAlchemyError:
        current_app.logger.exception("Referral rejection transaction failed")
        return jsonify(error="Could not reject referral; retry later"), 503
