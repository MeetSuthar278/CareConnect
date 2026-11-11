"""Consume initial requests, referral rejections and acceptance timeouts."""
import logging

from app.messaging.worker_runtime import run_consumer
from app.services.matching import (
    handle_request_created, handle_referral_rejected, handle_acceptance_timed_out,
)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_consumer("matching_queue", {
        "ServiceRequestCreated": handle_request_created,
        "ReferralRejected": handle_referral_rejected,
        "AcceptanceTimedOut": handle_acceptance_timed_out,
    })
