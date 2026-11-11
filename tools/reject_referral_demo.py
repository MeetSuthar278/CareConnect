"""Synthetic rejection helper: python -m tools.reject_referral_demo 9 --request-id 9 --workers.

Prompts for email/password locally; tokens/passwords are never printed or saved.
Uses real Firebase sign-in and the authorized Flask API. Does not link accounts,
grant roles, reset data, bypass deadlines or automatically retry rejection.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

from tools.create_firebase_test_user import PROJECT_ID, SetupError, post


BASE = "http://127.0.0.1:5000"
ROOT = Path(__file__).resolve().parent.parent


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a Firebase bearer token to a redirected destination.
        return None


def local_api(path, token=None, payload=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        BASE + path, headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None,
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read())
        except (ValueError, UnicodeError):
            data = {"error": "Flask returned an unreadable error response"}
        return error.code, data
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise SetupError("Cannot reach Flask or read its response. If rejection was sent, "
                         "check database state before trying again.") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("referral_id", type=int)
    parser.add_argument("--request-id", type=int, help="Expected request, checked against the rejection response")
    parser.add_argument("--workers", action="store_true", help="Run temporary local matching/notification/dispatcher processes")
    args = parser.parse_args(argv)
    if args.referral_id <= 0 or (args.request_id is not None and args.request_id <= 0):
        parser.error("IDs must be positive integers")
    if not sys.stdin.isatty():
        print("Run interactively in CMD; do not pipe credentials.")
        return 1
    processes = []
    try:
        print("Synthetic test only. Firebase project:", PROJECT_ID)
        print("This rejects referral", args.referral_id, "through the real authorized API.")
        email = input("Firebase test email: ").strip()
        password = getpass.getpass("Firebase test password (hidden): ")
        account = post("signInWithPassword", {
            "email": email, "password": password, "returnSecureToken": True,
        })
        password = None
        token = account.get("idToken")
        if not isinstance(token, str) or not token:
            raise SetupError("Firebase did not return an ID token")
        status, identity = local_api("/api/auth/me", token)
        if status != 200:
            print("Identity check:", status, identity.get("error", "Failed"))
            return 1
        if identity.get("role") != "representative":
            raise SetupError("This test account is not an organization representative")
        print("Authenticated representative; organization:", identity.get("organization_id"))
        if args.workers:
            environment = dict(os.environ, RABBITMQ_PORT="5673")
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            for filename in ("worker.py", "notification_worker.py", "outbox_dispatcher.py"):
                processes.append(subprocess.Popen(
                    [sys.executable, "-B", str(ROOT / filename)], cwd=str(ROOT),
                    env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=flags,
                ))
        status, result = local_api(f"/api/referrals/{args.referral_id}/reject", token,
                                  {"reason": "Synthetic live rejection test"})
        print("Rejection response:", status, json.dumps(result))
        if status != 200:
            return 1
        request_id = result.get("request_id")
        if args.request_id is not None and request_id != args.request_id:
            raise SetupError("Rejection committed for a different request than expected; stop and inspect")
        print("Rejection committed. Waiting up to 60 seconds for backup processing...")
        for _ in range(60):
            # Existing demo GET is sufficient for this status-only observation.
            status, request = local_api(f"/api/requests/{request_id}")
            if status == 200 and request.get("status") in {"matched", "unmatched"}:
                print("Request", request_id, "status:", request["status"])
                print("Database verification is still needed for backup referral and notification.")
                time.sleep(2)
                return 0
            time.sleep(1)
        print("Rejection is saved; backup status is not yet confirmed. Check workers/outbox; do not reset data.")
        return 1
    except SetupError as error:
        print("Test stopped:", error)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. If rejection was sent, inspect its saved state before retrying.")
        return 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            process.wait(timeout=10)
        if processes:
            print("Stopped only temporary workers started by this helper.")


if __name__ == "__main__":
    raise SystemExit(main())
