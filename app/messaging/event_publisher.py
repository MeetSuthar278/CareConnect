
import json
import uuid
from datetime import datetime, timezone

import pika

from app.messaging.rabbitmq_connection import rabbitmq_channel
from app.messaging.rabbitmq_config import EXCHANGE_NAME


EVENT_ROUTES = {
    "ServiceRequestCreated": "request.created",
    "ReferralCreated": "referral.created",
    "ReferralRejected": "referral.rejected",
    "AcceptanceTimedOut": "referral.timeout",
    "RequestAttended": "request.attended",
    "AttendanceOverdue": "attendance.overdue",
    "FeedbackSubmitted": "feedback.submitted",
}


def publish_event(event_type, request_id, payload, *, event_id=None, timestamp=None,
                  event_version=1):
    """Publish a CareConnect event to RabbitMQ."""

    if event_type not in EVENT_ROUTES:
        raise ValueError(f"Unknown event type: {event_type}")

    if not isinstance(request_id, int) or request_id <= 0:
        raise ValueError("request_id must be a positive integer")

    if not isinstance(payload, dict):
        raise ValueError("payload must be a dictionary")

    event = {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": event_version,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "payload": payload,
    }

    message = json.dumps(event)

    with rabbitmq_channel() as channel:
        channel.confirm_delivery()

        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=EVENT_ROUTES[event_type],
            body=message.encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                message_id=event["event_id"],
            ),
            mandatory=True,
        )

    print(f"Published: {event_type} | Request: {request_id}")
    return event
