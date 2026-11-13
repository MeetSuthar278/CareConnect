# Member login, dashboard and owned requests

Policy update approved October 30, 2026: member bearer and cookie authentication
no longer requires verified email. All signature/expiry/revocation, SQL role,
activity, ownership, recent-login and CSRF checks remain. References to verified
member email below describe the original phase; see the current
[policy guide](../testing/EmailVerificationPolicy_TEST_GUIDE.md).

## Scope and existing pages

Connect a verified member login to the team's existing dashboard, My Requests,
Request Details and Get Connected pages. Preserve layout, labels, CSS and existing
guest flow. This phase does not implement representative/coordinator dashboards,
profile editing, cancellation, service browsing or frontend feedback controls.
Those existing navigation destinations remain pending; no extra sections were added.

## Login session

The existing Firebase browser sign-in and /api/auth/me checks remain. For SQL members,
login.js then POSTs /api/auth/session with its bearer ID token and a page-generated
X-CSRF-Token. The backend requires verified email, SQL member role, a profile and
an auth_time within the last five minutes. Firebase Admin mints a one-hour session
cookie. The browser signs out its memory-only Firebase SDK and navigates only to
the fixed /member destination. Errors remain on login; no open redirect is accepted.
Representative/coordinator login keeps its previous success-only behavior.

The careconnect_member cookie is HttpOnly, SameSite=Lax, path / and Secure on HTTPS.
Local HTTP development requires Secure=false; deployed use must be HTTPS with trusted
proxy configuration. Firebase verifies cookie signature, expiry and revocation on
each member page/form request. SQL identity is looked up by Firebase UID and must
still be an active member with an existing profile. No email linking/provisioning is
performed from a cookie. Flask role/name state is for rendering only and cannot grant
access without the verified Firebase cookie. Browser state/CSRF secret rotates at login.

No Firebase token or password is stored in localStorage, sessionStorage or the signed
Flask session. Firebase's own signed session credential lives only in its HttpOnly
cookie. Existing bearer-only business APIs remain bearer-only and do not accept
the new cookie as an implicit authorization fallback.

## Routes, ownership and display

- GET /member: dashboard with real owned request counts and latest five requests.
- GET /member/requests: owned requests with existing status filter.
- GET /member/requests/<id>: request details/history, checked against the member.
- GET /get-connected: existing template's saved contact-summary branch for members;
  guest contact-input branch remains unchanged for guests.
- POST /api/member/requests: member form submission with member CSRF and nonce.
- GET /get-connected/done/CC-ID: checks the current member's ownership when signed in;
  retains existing guest-session ownership checks for guests.
- GET /api/member/requests/<id>: minimal owned status polling, no guest fallback.
- GET /logout?csrf=TOKEN: existing logout anchor with unguessable session CSRF token;
  clears browser state and the Firebase cookie and redirects to login.

Protected HTML routes redirect unauthenticated users to login; protected member APIs
return 401. Other owners' details/status return 404. Invalid/revoked/inactive cookies
fail closed, are cleared, and cannot silently fall back to creating a guest request.
Member/private responses have Cache-Control no-store.

Logout affects this browser cookie, not every device's Firebase credentials. It does
not revoke all refresh tokens. The CSRF token is included in the existing GET anchor
to preserve its design; avoid sharing logout URLs. A later navigation/security phase
can change the control to a POST form with explicit frontend approval.

## Member submission transaction and existing events

Derive the owner and every contact field from the verified SQL member/profile; ignore
all client-supplied identity/contact fields. Reuse create_guest_request's existing
transaction with an explicit existing owner, so it never creates a guest account or
overwrites the member profile. Its SQL active-member/contact recheck remains in force.
Saved contacts must satisfy the existing service city and validation rules.

The business key is member-request:SHA256(owner|member-CSRF|form-nonce). The existing
transaction validates active service/category, one determinable supported area,
delivery mode and priority; inserts the owned request with the original SLA; and
enqueues ServiceRequestCreated atomically. Repeat form POSTs reuse the same request;
unique outbox keys prevent concurrent duplicates. Database failures roll back and
return a retryable error; the same nonce remains usable.

Existing matching, capacity reservation and ReferralCreated delivery stay unchanged.
No new RabbitMQ event, exchange, queue, schema, migration, seed, credentials or live
data changes were needed. Member login never transfers guest request ownership.
Login/logout rotate browser state, so previous guest-session access is not carried
into the authenticated session; stored guest data is preserved.

## Exact files

Changed app/__init__.py, app/auth.py, app/frontend.py,
frontend/static/js/login.js, frontend/static/js/request-confirmation.js,
frontend/templates/auth/login.html, frontend/templates/individual/request_form.html,
frontend/templates/individual/request_confirmation.html, tests/test_login_ui.py.
Added app/member.py, tests/test_member_workflow.py, docs/events/MemberWorkflow.md,
docs/testing/MemberWorkflow_TEST_GUIDE.md.
app/requests.py and existing guest/matching services were reused without edits.

## Verification and remaining limitations

Focused tests cover CSRF, recent auth, cookie flags, session rotation, logout, forged
template sessions, revoked/unverified/unknown cookies, SQL deactivation, ownership,
nonce duplicates, saved-contact authority, atomic rollback, member login failure,
preserved representative login, guest regressions and a browser dashboard -> owned
submission -> My Requests -> logout flow. Actual counts are in the test guide.
Firebase session minting/verification is mocked; real Admin permissions, cookies and
MySQL concurrency require user-run live checks. No real account or request was created.

The unchanged My Requests table showed horizontal document overflow at 390px in the
browser check. CSS/layout fixes require separate approval; it retains the team's
scrollable table region. The test verifies functionality rather than claiming the
mobile layout is fixed. Legacy Request Details feedback/rating/cancel controls are
not connected in this phase; no rating value is fabricated from yes/no feedback.
Profile/Services navigation destinations are not yet implemented. Some accepted/
in-progress display/contact details still follow existing template status conditions.
These are frontend reconciliation work, separate from secured ownership/submission.

Session design follows Firebase's official [server session-cookie guidance](https://firebase.google.com/docs/auth/admin/manage-cookies).
