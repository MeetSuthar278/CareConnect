# Coordinator dashboard, request details and alerts

## Scope and design

Read-only integration of the existing coordinator dashboard and All Requests page.
The team template already contains expandable request details and attention filters;
no duplicate page, layout, field, CSS or explanatory section was added.
The existing Reassign column renders its existing dash placeholder in read-only
mode. No manual assignment, approval, organization management or report action was
authorized or implemented by this phase.

## Verified coordinator session

After normal Firebase browser login and /api/auth/me, login.js calls
/api/auth/coordinator-session for SQL coordinators. Require verified email, current
active SQL coordinator role, a matching login CSRF header and auth_time within the
last five minutes. A client role claim or signed Flask role value cannot grant access.
Mint the existing one-hour Firebase server-session credential into the separate
careconnect_coordinator cookie: HttpOnly, SameSite=Lax, path /, Secure on HTTPS.
Local HTTP development retains Secure=false; deployment requires HTTPS/trusted proxy setup.
Rotate browser/CSRF state and clear prior member/organization cookies. Their session
creation now reciprocally clears the coordinator cookie. Client SDK tokens stay in
memory and are signed out after successful session creation; destination is fixed
to /coordinator. No new authentication framework or identity table is introduced.

On every coordinator page/logout request, verify cookie signature/expiry/revocation,
verified email and current SQL activity/coordinator role by UID. Reject member and
representative cookies/UIDs and disabled/demoted coordinators. Invalid cookies are
cleared and protected pages redirect to login. Cookie reads do not provision users,
link identities or change roles. Existing optional email verification for members
remains intact; representative/coordinator verification remains mandatory.

## Routes and data

- GET /coordinator: real pending-organization, unmatched, outstanding overdue and
  total request counts, pending organization rows and needs-attention references.
- GET /coordinator/requests: real requests with existing status/priority/latest-org/
  attention filters, contact fields, original deadlines and expandable history.
- GET /coordinator/logout?csrf=TOKEN: existing logout anchor with unguessable session
  CSRF token, clears coordinator cookie/browser state, redirects to login.
- POST /api/auth/coordinator-session: verified bearer-to-cookie exchange only.

Dashboard links use the existing #request-ID anchor and shared main.js to open
the matching details. The list is globally visible only to authorized coordinators;
member/representative ownership restrictions on their own routes remain unchanged.
Responses are no-store. Read-only pages issue no business writes; no request
mutation or reassignment route is created. Logout affects this browser, not other
devices, and preserves the previously adopted CSRF-protected GET-anchor pattern.

Latest organization/referral is derived from saved attempt order. Guest display
uses users.firebase_uid IS NULL, not email guessing. Missing profile names render
the existing dash placeholder. History includes original submission and all saved
referral transitions. Historical inactive services/organizations remain visible.
The notifications bell reads only unread deliveries to the current coordinator,
newest first, capped at 20; other users' messages are not included or marked read.

## Attention definitions

- Unmatched: saved request status unmatched.
- Rejected referral / Expired referral: latest referral rejected/timed_out while
  request is not completed/cancelled. Earlier rescued attempts remain in history.
- Overdue: original attendance deadline has passed, no attendance record exists,
  and request is not completed/cancelled. This matches outstanding scanner work,
  not every historical deadline-missed alert. Late but recorded attendance removes
  outstanding-overdue status; stored late/overdue notifications remain historical.
- Manual review: saved negative feedback exists. This flags feedback that needs
  coordinator review even when service completion is final.

These flags/filter labels reuse existing template vocabulary. No stored request
status is rewritten to manufacture an escalation. The pending organization's
existing city is displayed in the dashboard Area cell; it is not a matching eligibility rule.
Existing automatic matching, timeout and feedback event workflows are unchanged.

## Database, messaging and exact files

Reads existing users/roles, organizations, requests, services/categories/priorities,
latest referrals, profiles, attendance, feedback, history and current-user notifications.
No database writes, new events/outbox rows, queues, workers, migrations, baselines,
seeds, credential/environment changes or account/role updates occurred in this phase.

Changed app/__init__.py, app/member.py, app/organization.py (registration and cookie
switching), app/frontend.py (existing endpoint aliases), frontend/static/js/login.js,
frontend/templates/coordinator/requests.html (read-only conditional), tests/test_login_ui.py.
Added app/coordinator.py, tests/test_coordinator_workflow.py,
docs/events/CoordinatorWorkflow.md and docs/testing/CoordinatorWorkflow_TEST_GUIDE.md.

## Tests and remaining work

Focused checks cover verified coordinator cookies, fresh login, CSRF/logout, cookie
rotation, forged roles, unverified/member/representative/revoked cookies, SQL deactivation
and demotion, real counts, timely/late attendance handling, negative-feedback flags,
notification recipient privacy, filters, existing expandable details and absence of
business writes. Browser tests follow the dashboard reference, verify automatic
expansion, apply filters and log out. Firebase is mocked and SQL is disposable.
Actual results/commands are recorded in the guide. MySQL concurrency and actual
Firebase cookie permissions remain live checks.

Read-only local readiness inspection found existing coordinator user 1 active but
not Firebase-linked. No login was created or linked. Live coordinator testing needs
a separately approved verified Firebase identity linked to an authorized coordinator;
do not promote a member/representative or bypass verification as a workaround.

Approvals, Organizations, Reports, reassignment, notification read/dismiss controls,
pagination and CSS/mobile-table repairs remain pending. Existing navigation to those
pages is not proof that their handlers are implemented. Earlier organization/member
documents record their original login phase; this phase now adds coordinator routing.
