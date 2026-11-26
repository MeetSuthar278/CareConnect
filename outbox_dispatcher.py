"""Publish pending outbox records; retry failures without changing their IDs."""
import logging
import time

from sqlalchemy.orm import Session

from app import create_app, db
from app.services.outbox import dispatch_one


def main():
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    with app.app_context():
        while True:
            try:
                with Session(db.engine) as session:
                    found = dispatch_one(session)
                if not found:
                    time.sleep(1)
            except KeyboardInterrupt:
                return
            except Exception:
                logging.exception("Outbox database failure; retrying in 5 seconds")
                time.sleep(5)


if __name__ == "__main__":
    main()
