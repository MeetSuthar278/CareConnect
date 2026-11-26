"""Shared process lifecycle; each delivery gets its own database session."""
import logging
import time

from sqlalchemy.orm import Session

from app import create_app, db
from app.messaging.event_consumer import consume_events

logger = logging.getLogger(__name__)


def run_consumer(queue, event_type, handler=None):
    # Existing single-event workers remain compatible; matching uses a dispatch map.
    handlers = event_type if isinstance(event_type, dict) else {event_type: handler}
    app = create_app()
    with app.app_context():
        def process(event):
            selected_handler = handlers.get(event["event_type"])
            if selected_handler is None:
                # The matching queue also has future backup-event bindings.
                # Keep unsupported work queued rather than silently acknowledge it.
                raise RuntimeError(f"This worker does not handle {event['event_type']}")
            with Session(db.engine) as session:
                selected_handler(session, event)

        while True:
            try:
                consume_events(queue, process)
                return
            except KeyboardInterrupt:
                return
            except Exception:
                logger.exception("Consumer disconnected; retrying in 5 seconds")
                time.sleep(5)
