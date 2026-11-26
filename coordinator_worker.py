"""Consume AttendanceOverdue and store coordinator notifications."""
import logging

from app.messaging.worker_runtime import run_consumer
from app.services.overdue import handle_attendance_overdue


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_consumer('coordinator_queue', 'AttendanceOverdue', handle_attendance_overdue)
