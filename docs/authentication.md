# Authentication

CareConnect uses Firebase email/password identity and SQL-owned roles. The source
contains bearer-token APIs and browser session adapters. Automated checks use
synthetic identities; real inbox delivery and live sign-in require the team checks
in the [submission report](SUBMISSION_READINESS.md).

## Identity and authorization

`GET /api/auth/me` requires `Authorization: Bearer <Firebase ID token>` and returns
`user_id`, `email`, `role`, and `organization_id`. Firebase verification checks
revocation and disabled accounts. Roles and organization membership come from SQL,
not form fields or Firebase custom role claims.

Every SQL role requires `email_verified=true` from an Admin-SDK-validated token.
`/api/auth/me` never creates a user or links by email. Verified identities without
completed SQL registration receive HTTP 409 with `code=registration-required`.
Roles always come from SQL; public registration can create only a member or a
pending organization representative, never a coordinator.

Missing or invalid tokens return 401; insufficient privileges or inactive accounts
return 403; account-linking conflicts return 409; unavailable verification or database
services return 503. Business handlers separately enforce ownership and state.

## Browser sessions

`frontend/static/js/login.js` uses Firebase in-memory persistence, calls the identity
API, and posts to the appropriate session endpoint:

| SQL role | Session endpoint | Destination |
| --- | --- | --- |
| Member | `/api/auth/session` | `/member` |
| Representative | `/api/auth/organization-session` | `/organization` |
| Coordinator | `/api/auth/coordinator-session` | `/coordinator` |

Session creation checks the login CSRF token and recent Firebase authentication.
Cookies are HttpOnly, use SameSite=Lax, and expire after one hour. Secure cookies
are used for HTTPS requests and are mandatory for all session cookies in hosted mode.
Protected browser requests verify Firebase cookies and recheck SQL identity.
Navigation role/name fields are presentation state, not authorization evidence.

## Verified registration and recovery

Both registration forms validate the existing password policy before calling
Firebase: at least eight characters, one ASCII uppercase letter and one supported
special character, with matching confirmation. Lowercase letters and numbers are
optional. Existing login and recovery passwords have no new complexity rule.

Firebase first creates an authentication account and sends a verification email.
The page switches to `/register/verify` without discarding its in-memory Firebase
session and pending form details. This is an intentional in-document transition;
a full reload would lose those details. The verification screen shows the account
email, inbox/spam guidance, retry and resend buttons, loading state and a 60-second
resend cooldown. Firebase remains authoritative for rate limiting.

After the user opens the link, the application reloads the Firebase user and forces
an ID-token refresh. Flask independently validates that token and its verified
claim before `/api/auth/register/profile` or `/api/auth/register/organization` writes
anything. Member user/profile creation is one transaction. Organization user,
representative, organization and application creation is one transaction with status
`pending` and application status `submitted`. Exact retries return `already_processed`;
conflicting retries preserve existing details. A successful completion returns to
login; it does not establish an authenticated application session.

After closing or reloading the page, use **Finish registration** on the login page.
Sign in with the original password, check verification, and re-enter details if SQL
registration is incomplete. An already registered account returns to login. No
passwords, Firebase tokens or pending profile details are put in local/session
storage, query strings or Flask session cookies. Expired/missing email links can be
replaced by resending; unknown completion outcomes can be retried safely.

Unverified tokens and unverified session cookies cannot open protected pages.
Pending/rejected organizations cannot view referrals or manage services; verified
representatives can still open their approval-status dashboard/profile. Rejection
is an application result, not an invented organization enum. Verification never
approves an organization. Suspended partners retain the existing ability to finish
already accepted work, while acceptance and service management require approval.

Password changes continue to reauthenticate with Firebase. Their unnamed fields
avoid sending passwords to Flask through native form fallback.

## Configuration and schema

Use `FIREBASE_PROJECT_ID` matching the public frontend configuration and configure
Application Default Credentials privately. The browser API key is public client
configuration; Admin service-account keys must remain outside the repository.
Interactive utilities require `FIREBASE_WEB_API_KEY` in their process environment.

The current SQL baselines contain nullable unique `firebase_uid` and nullable
`password_hash`; ORM User metadata now matches those migrated fields. The live
read-only schema check confirms them. Migration 002 is already applied on the
current database; never reapply it. The teammate Firebase SQL implements the same
upgrade and is not an additional required migration. Fresh/legacy initialization
orders are documented in DEPLOYMENT_GUIDE; no startup tool executes migrations.
ORM metadata is partial and must not be used with `create_all()` to provision it.

The legacy demo request APIs use a shared local debug/testing identity rather than
Firebase. Hosted mode disables that access. Preserve this distinction when testing.

## Firebase Console tasks

Confirm Email/Password sign-in, authorized local/hosted domains, and verification
email templates/action links in `careconnect-bfb9e`. The Console password policy
must match eight characters plus uppercase and special characters, with lowercase
and numeric requirements off. Keep forced upgrades on sign-in disabled so existing
passwords remain usable. Live SDK validation confirmed optional lowercase and digits, with both Password@
and PASSWORD@ accepted and forced upgrades off. See testing/SECURITY_AUDIT.md.
See [Firebase password policy](https://firebase.google.com/docs/auth/web/password-auth)
and [email verification](https://firebase.google.com/docs/auth/web/manage-users).

Existing UID mappings need a separate, approved identity review. See the
[account migration plan](testing/ACCOUNT_MIGRATION_PLAN.md); never relink by email
alone or automatically verify an account.

The login page now offers Forgot your password using Firebase reset email, with
email validation, a non-enumerating result and friendly failure/cooldown messages.
No password complexity checks were added to login. Actual email delivery/action
links must be checked with an owned account; developer browser tests use a fake SDK.
