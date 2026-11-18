r"""Interactive synthetic Firebase account setup; no MySQL or Admin credentials.

Windows CMD, from project root:
    .\.venv\python.exe tools\create_firebase_test_user.py

If account creation succeeded but email delivery failed:
    .\.venv\python.exe tools\create_firebase_test_user.py --resend-verification

Use a test inbox you control. Passwords/tokens are not written to disk or printed.
This does not verify email automatically, grant roles, link SQL accounts or reset
passwords. Open the received verification email before using /login.
REST reference: https://firebase.google.com/docs/reference/rest/auth
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode


# Public web configuration, matching the team's reviewed frontend. Not an Admin key.
PROJECT_ID = "careconnect-7132c"
WEB_API_KEY = os.environ["FIREBASE_WEB_API_KEY"]
BASE_URL = "https://identitytoolkit.googleapis.com/v1/accounts:"


class SetupError(Exception):
    """A sanitized message safe to show without credential/token contents."""


ERRORS = {
    "EMAIL_EXISTS": "This account already exists. No account or password was changed. "
                    "Use --resend-verification only if you own it and know its password.",
    "INVALID_EMAIL": "Enter a valid test email address.",
    "WEAK_PASSWORD": "Firebase rejected the password. Choose a stronger password.",
    "PASSWORD_DOES_NOT_MEET_REQUIREMENTS": "The password does not meet the project's password policy.",
    "OPERATION_NOT_ALLOWED": "Email/password authentication must be enabled in Firebase.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Firebase rate-limited this action. Wait before trying again.",
    "INVALID_LOGIN_CREDENTIALS": "Email or password is incorrect.",
    "INVALID_PASSWORD": "Email or password is incorrect.",
    "EMAIL_NOT_FOUND": "Email or password is incorrect.",
    "USER_DISABLED": "This Firebase account is disabled.",
    "API_KEY_INVALID": "The reviewed Firebase web API key is not accepted by Firebase.",
    "QUOTA_EXCEEDED": "Firebase email or account quota was exceeded. Try later.",
}


def post(action, payload):
    request = urllib.request.Request(
        BASE_URL + action + "?" + urlencode({"key": WEB_API_KEY}),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            raise SetupError("Firebase returned an unexpected response.")
        return data
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read()).get("error", {}).get("message", "")
            code = detail.split(":", 1)[0].strip()
        except (ValueError, AttributeError, TypeError):
            code = ""
        # Never print server response bodies, request payloads or exception URLs.
        raise SetupError(ERRORS.get(code, "Firebase rejected the request. Check project settings "
                                   "or ask the project administrator.")) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SetupError("Connection failed or timed out. The previous operation may have succeeded. "
                         "Do not repeatedly create accounts; check Firebase Console first.") from None
    except (ValueError, UnicodeError):
        raise SetupError("Firebase returned an unreadable response. Check the account state before retrying.") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resend-verification", action="store_true",
                        help="Sign in to an existing account and request verification; do not create or reset it")
    options = parser.parse_args(argv)
    if not sys.stdin.isatty():
        print("Run this interactively in Command Prompt; do not pipe credentials into the script.")
        return 1
    created = False
    try:
        print("Firebase project:", PROJECT_ID)
        print("Use a synthetic test account and an inbox you control. Credentials are sent only to Firebase.")
        print("No MySQL records, roles or frontend files will be changed by this script.")
        email = input("Test email: ").strip()
        if email.count("@") != 1 or any(c.isspace() for c in email) or len(email) > 120:
            raise SetupError("Enter a valid test email of at most 120 characters.")
        password = getpass.getpass("Password (hidden): ")
        if not password:
            raise SetupError("Password cannot be empty.")
        if not options.resend_verification:
            confirmation = getpass.getpass("Confirm password (hidden): ")
            if password != confirmation:
                raise SetupError("Passwords do not match. Nothing was sent.")
            if len(password) < 6:
                raise SetupError("Use at least six characters, or more if required by Firebase policy.")
        operation = "RESEND" if options.resend_verification else "CREATE"
        print("This will " + ("sign in and request a verification email for "
              if options.resend_verification else "create a Firebase account and request a verification email for ") + email)
        if input("Type " + operation + " to continue: ").strip() != operation:
            print("Cancelled. Nothing was sent.")
            return 0
        action = "signInWithPassword" if options.resend_verification else "signUp"
        account = post(action, {"email": email, "password": password, "returnSecureToken": True})
        created = not options.resend_verification
        password = None
        token = account.get("idToken")
        if not isinstance(token, str) or not token:
            raise SetupError("Firebase did not return a verification token. Check the account before retrying.")
        post("sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": token})
        print("Verification email requested. Check your inbox and spam folder, then open the verification link.")
        print("After verification, sign in at http://127.0.0.1:5000/login using the same email and password.")
        print("The first successful CareConnect login may create a member row; this script does not.")
        return 0
    except SetupError as error:
        print("Setup stopped:", error)
        if created:
            print("Account creation succeeded, but verification email was not confirmed. "
                  "Use --resend-verification with the same credentials; do not create another account.")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. If a network operation was in progress, check Firebase Console before retrying.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
