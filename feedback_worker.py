"""Persist organization feedback notifications and negative coordinator alerts."""
import logging

from app.messaging.worker_runtime import run_consumer
from app.services.feedback import handle_feedback_submitted


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_consumer('feedback_queue', 'FeedbackSubmitted', handle_feedback_submitted)
