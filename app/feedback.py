"""Authenticated member feedback endpoint; no guest identity fallback."""
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import db
from app.auth import roles_required
from app.services.feedback import FeedbackError, submit_feedback

feedback_bp = Blueprint('feedback', __name__)


@feedback_bp.post('/api/requests/<int:request_id>/feedback')
@roles_required('member')
def submit(request_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='JSON object required'), 400
    if 'rating' in data:
        return jsonify(error='Use yes/no is_helpful feedback; ratings are not supported'), 400
    try:
        with Session(db.engine) as session:
            result = submit_feedback(session, request_id, g.current_user.user_id,
                                     data.get('is_helpful'), data.get('comment'))
        return jsonify(result), 200
    except FeedbackError as error:
        return jsonify(error=str(error)), error.status
    except SQLAlchemyError:
        current_app.logger.exception('Feedback transaction failed')
        return jsonify(error='Could not save feedback; retry later'), 503
