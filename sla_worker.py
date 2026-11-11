"""Consume RequestAttended and persist late-attendance coordinator alerts."""
import logging

from app.messaging.worker_runtime import run_consumer
from app.services.attendance import handle_request_attended


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_consumer('sla_queue', 'RequestAttended', handle_request_attended)
