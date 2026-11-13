# Organization dashboard and referral controls

## Approved scope and design

Connect the existing team organization dashboard, request list and request details
to organization-scoped data and existing referral transactions. The user separately
approved adding Record attendance inside Update status, showing Mark as Completed
only after attendance, and collecting rejection reason in a native browser prompt.
No CSS, layout, page sections or existing labels were changed. This later phase
extends representative login beyond the success-only behavior recorded in the
earlier MemberWorkflow phase. Coordinator dashboard login remains unchanged.

## Login/session and routes

Firebase browser sign-in remains memory-only and verified through /api/auth/me.
Representative login now POSTs /api/auth/organization-session with a bearer ID
token and page-generated CSRF header. Require verified email, current SQL
representative role, active user, organization membership and recent auth_time
(within five minutes). Mint the same one-hour Firebase server-session credential
used by member login, but store it in the separate careconnect_organization cookie.
It is HttpOnly, SameSite=Lax, path /, Secure on HTTPS (HTTP only for local testing).
Rotate Flask CSRF/browser state, clear the member cookie, sign out the client SDK
and navigate to the fixed /organization destination. Member login reciprocally
clears an old organization cookie. No identity/organization is taken from form data.

Every organization HTML/action request verifies the cookie with Firebase revocation
checking and rechecks SQL user activity, role and representative organization by UID.
A signed Flask role value alone grants no access. Invalid cookies are cleared;
protected requests redirect to login. No user or membership is provisioned from a
cookie. Existing bearer-only APIs remain unchanged.

- GET /organization: current organization's real status, counts and incoming referrals.
- GET /organization/requests: own referrals, existing status filter and inline controls.
- GET /organization/requests/<request_id>: own referral details/history and controls.
- POST /organization/requests/<request_id>/action: CSRF-protected native form adapter.
- GET /organization/logout?csrf=TOKEN: existing logout anchor with unguessable session
  CSRF token; clear this browser's cookie/state and return to login.

Organization responses are no-store. Logout does not revoke other devices. HTTPS
and correct trusted proxy configuration are required outside local development.
The existing GET logout pattern is preserved, with CSRF protection; do not share
logout URLs. No new session framework or schema is introduced.

## Data scoping and contact privacy

All list/detail queries filter by the representative's saved organization ID.
Posted referral_id is checked against both the URL request and current organization
before calling any service. Each existing service rechecks SQL membership and
business state again inside its transaction. Other organizations' records return 404.
Request history contains only this organization's referral transitions.

Member contact fields are not fetched or serialized until this organization has an
accepted, attended or completed referral. Before acceptance the existing contact
placeholder remains. Saved SQL profiles supply the displayed contact fields.
The notification bell reads only notifications addressed to the current user,
not other representatives or coordinators. Existing primary-contact notification
policy remains unchanged; a nonprimary representative may legitimately see no alerts.

## Form actions and transactions

Each existing action form includes hidden CSRF and exact referral ID. Existing
confirmation dialogs remain. The organization-actions script runs after shared
validation/confirmation; cancellation cannot leave the form stuck in a busy state.
Reject prompts for a trimmed 1–255 character reason. Cancelling confirmation or
prompt sends no mutation. Missing/invalid reason is also rejected server-side.
Without JavaScript, rejection cannot silently save a fabricated reason.

- Accept calls accept_referral: matched/sent, unexpired response, authorized owner;
  acceptance/history commit together while capacity remains reserved. Portal
  acceptance additionally requires the current request's organization status approved.
- Reject calls reject_referral with the actual prompt reason: release/history/state
  and ReferralRejected outbox commit together, then existing backup matching applies.
- Record attendance calls record_attendance for accepted referrals: first attendance,
  history, in_progress request and RequestAttended event commit together. Capacity stays reserved.
- Mark as Completed calls complete_referral only after attendance. The existing UI
  has no outcome/notes selector, so it uses the service's successful/default-null
  details; completion/history/status and one release commit atomically.

No automatic accept+attend or attend+complete shortcut exists. Backend deadlines,
state checks, request-first locks, uniqueness and duplicate guards remain authoritative.
Old forms cannot mutate another referral just because the request number matches.
Direct repeats remain safe through existing services. SQL errors show a retryable
message in the existing message area; business conflicts show existing service messages.

## Status display and reliability

Preserve existing status vocabulary: sent -> Assigned; accepted/attended -> Accepted;
rejected -> Rejected; timed_out -> Expired; completed -> Completed. Raw saved status
controls which action is available, so grouping attended under Accepted never permits
completion before attendance. The existing history shows the actual attended transition.
Expired sent referrals show no Accept/Reject controls; the backend also refuses them.
Pending/suspended organizations can inspect existing data, but cannot accept through
the portal. Existing accepted work can still be attended/completed and reservations released.

No new RabbitMQ event or queue is introduced. Existing rejection, attendance and
completion services and all existing outbox publishing, consumer acknowledgement,
notification deduplication and retry logic are reused unchanged. Organization status
is loaded at HTTP-request time; a simultaneous administrative status change is not
serialized with acceptance by this adapter (SQL membership and referral state are).
Atomic admin-status enforcement belongs in a separately reviewed business-rule update.

## Exact files and database effects

Changed app/__init__.py, app/member.py (clear old organization cookie on member login),
app/frontend.py (existing endpoint aliases), frontend/static/js/login.js,
frontend/templates/organization/requests.html,
frontend/templates/organization/request_details.html and tests/test_login_ui.py.
Added app/organization.py, frontend/static/js/organization-actions.js,
tests/test_organization_workflow.py, docs/events/OrganizationWorkflow.md and
docs/testing/OrganizationWorkflow_TEST_GUIDE.md.

Reads existing users/roles/representatives/organizations, referrals/requests/history,
services/priorities/offerings, accepted member profiles and user notifications.
Writes occur only through the unchanged approved business services when actions
are intentionally submitted. No baseline, model, migration, seed, environment,
credentials or CSS changed. Implementation executed no live login or referral mutation.

## Verification and limits

Tests cover session CSRF/recent auth/cookie rotation/logout, wrong-role cookies,
forged template sessions, deactivated/changed membership, organization ownership,
tampered parent IDs, hidden preacceptance contact fields, duplicate mutations,
expired acceptance, completion before attendance, rejection reason, SQL failure,
pending organization and notification recipient scoping. Browser tests exercise
Accept -> Record attendance -> Complete and both rejection confirmation/prompt cancellation.
Actual counts/commands are in the test guide. Firebase is mocked; SQL is disposable.
Live Firebase cookie minting, MySQL contention and broker delivery remain live checks.

My Services and Organization Profile navigation remain pending. No coordinator UI,
organization signup/approval, service editing, custom completion-outcome form or
feedback form is implemented here. Existing narrow-screen tables retain team CSS.
Existing rejection confirmation mentions coordinator review; actual automatic backup
behavior remains the previously approved backend flow, without changing that team text.
