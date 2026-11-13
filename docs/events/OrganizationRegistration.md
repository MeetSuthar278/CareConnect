# Organization registration

The existing team form at `/register/organization` is now connected without changing
its visible fields, layout, labels or submit button. A new module uses Firebase
email/password authentication with memory-only persistence, following member signup's
existing SDK pattern. Only organization signup requires email verification.

First submit creates the Firebase identity (or authenticates an existing identity
using its actual password). If unverified, send a verification email and stop before
any SQL provisioning. The user verifies in their inbox and resubmits the same form
with the same details/password. Password fields are cleared after each attempt;
application fields remain in the current page, not localStorage. Signing out of the
SDK after each attempt avoids leaving a browser Firebase session behind.

Once verified, request a fresh Firebase ID token and POST only organization name,
address, requested service area, city, contact name and phone to
`/api/auth/register/organization`. The server directly reuses the existing token
verifier (including revoked/disabled-account checks). It requires a valid UID,
email and boolean email_verified=true. Email/UID come only from verified claims;
client role, organization IDs, statuses and extra payload fields are rejected.
No SQL password or Firebase credential is received in the application payload.

This endpoint intentionally does not use the member-auto-provisioning decorator.
The service owns one SQL transaction:

1. Lock/check the claimed UID. Existing users cannot be promoted, relinked or edited.
2. Reject an email belonging to another SQL identity and an existing organization name.
3. Insert a new Firebase-linked user with the database representative role.
4. Insert the pending organization and primary representative association.
5. Insert its submitted application, using the representative as submitter.

The existing UID/email/name uniqueness constraints protect concurrent inserts.
Constraint conflicts return 409; SQL failures return 503 and roll back all inserts.
Retry with the same credentials/details. An exact retry for the same active SQL
representative and original application returns the saved IDs without changing
its status, even after approval/rejection/suspension. Different details return 409;
the endpoint is not profile editing or application resubmission. It does not grant
coordinator access or migrate existing member/guest accounts.

Requested service area is stored as `Requested service area: ...` in the existing
application submission_notes column. It is not an approved coverage record. No
catalog, offering, priority support or capacity row is automatically created.
Existing coordinator approval and applicant notifications handle the subsequent
decision. Verified representatives may log in while pending to see their status;
pending organizations cannot receive matches. No new RabbitMQ event is needed.

## Limits

Firebase identity creation/email delivery and SQL are separate systems. A Firebase
identity can exist even when email delivery or SQL fails. Recovery signs in using
the same password and retries; nothing deletes that identity automatically. Do not
use ordinary login before completing organization submission: ordinary first-time
login provisions a member by the existing policy. Existing SQL members need a
separate organization identity; their accounts are never silently converted.

Email delivery may be delayed/rate-limited. Account verification is tested with
mocked Firebase, not actual email in this phase. A functioning deployed project,
email/password provider and Admin credentials are still required. MySQL uniqueness
and lock behavior require live validation; SQLite tests are not concurrency proof.
No schema changes, live account creation or live data edits were executed.
