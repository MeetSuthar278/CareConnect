"""Persist in-app alerts for ReferralCreated events."""
import logging

from app.messaging.worker_runtime import run_consumer
from app.services.notifications import handle_referral_created


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_consumer("notification_queue", "ReferralCreated", handle_referral_created)
