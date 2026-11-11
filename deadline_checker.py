"""Deadline scanner. Read-only preview unless --apply is explicit."""
import argparse
import logging
import time

from sqlalchemy.orm import Session

from app import create_app, db
from app.services.timeouts import expired_referral_ids, scan_once
from app.services.overdue import overdue_request_ids, scan_overdue_once


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Value must be positive")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("acceptance", "attendance"), default="acceptance")
    parser.add_argument("--apply", action="store_true", help="Commit the selected deadline processing")
    parser.add_argument("--once", action="store_true", help="Scan one batch then exit")
    parser.add_argument("--referral-id", type=positive, action="append",
                        help="Restrict processing to this ID; repeat to select several")
    parser.add_argument("--request-id", type=positive, action="append",
                        help="Restrict attendance-overdue processing to this request")
    parser.add_argument("--batch-size", type=positive, default=100)
    parser.add_argument("--interval", type=positive, default=30, help="Seconds between scans")
    args = parser.parse_args(argv)
    if args.batch_size > 1000:
        parser.error("Batch size must be at most 1000")
    if args.kind == "attendance" and args.referral_id:
        parser.error("Use --request-id with --kind attendance")
    if args.kind == "acceptance" and args.request_id:
        parser.error("Use --referral-id with --kind acceptance")
    scanner = scan_overdue_once if args.kind == "attendance" else scan_once
    discover = overdue_request_ids if args.kind == "attendance" else expired_referral_ids
    selected_ids = args.request_id if args.kind == "attendance" else args.referral_id
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    with app.app_context():
        while True:
            try:
                if args.apply:
                    result = scanner(lambda: Session(db.engine), args.batch_size, selected_ids)
                    logging.info("%s deadline batch: %s", args.kind, result)
                    if args.once:
                        return 1 if result["failed"] else 0
                else:
                    with Session(db.engine) as session:
                        ids = discover(session, args.batch_size, selected_ids)
                    logging.info("Read-only %s preview; candidate IDs: %s", args.kind, ids)
                    if args.once:
                        return 0
            except KeyboardInterrupt:
                return 0
            except Exception as error:
                logging.error("Deadline scan unavailable (%s); no reset attempted", type(error).__name__)
                if args.once:
                    return 1
            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                return 0


if __name__ == "__main__":
    raise SystemExit(main())
