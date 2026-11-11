"""Store events with business changes; dispatch them with at-least-once delivery."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import EventOutbox
from app.messaging.event_publisher import publish_event

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enqueue(session, event_type, request_id, payload, business_key):
    event = EventOutbox(
        event_id=str(uuid.uuid4()), deduplication_key=business_key,
        event_type=event_type, event_version=1, request_id=request_id,
        payload=payload, created_at=utcnow(), available_at=utcnow(), attempts=0,
    )
    session.add(event)
    return event


def dispatch_one(session):
    """Keep the row locked through confirmed publish; crash recovery may resend it."""
    with session.begin():
        event = session.execute(
            select(EventOutbox)
            .where(EventOutbox.published_at.is_(None), EventOutbox.available_at <= utcnow())
            .order_by(EventOutbox.available_at, EventOutbox.event_id)
            .with_for_update(skip_locked=True).limit(1)
        ).scalar_one_or_none()
        if event is None:
            return False
        event.attempts += 1
        try:
            publish_event(
                event.event_type, event.request_id, event.payload,
                event_id=event.event_id,
                timestamp=event.created_at.replace(tzinfo=timezone.utc).isoformat(),
                event_version=event.event_version,
            )
        except Exception as error:
            event.last_error = str(error)[:2000]
            event.available_at = utcnow() + timedelta(seconds=min(300, 2 ** min(event.attempts, 8)))
            logger.exception("Outbox publish failed: %s", event.event_id)
        else:
            event.published_at = utcnow()
            event.last_error = None
    return True
