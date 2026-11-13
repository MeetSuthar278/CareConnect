# Member browser feedback integration

## Approved visible changes and scope

Use the existing team feedback form/layout and completed-request summary. The user
approved replacing the 1–5 rating legend/radios with Was this service helpful? and
Yes/No choices, keeping Comment (optional) and Send Feedback, replacing Rate this
service with Leave feedback, and displaying Helpful: Yes or Helpful: No afterward.
No CSS, layout, sections or unrelated controls changed. No numeric/star conversion
or rating persistence was introduced; the legacy rating column remains NULL.

## Routes and authentication

GET/POST /member/requests/<request_id>/feedback uses the existing member Firebase
session cookie and current active SQL member/profile lookup. Members do not require
email verification under the approved current policy; token signature/expiry,
revocation, SQL role, account activity and ownership remain enforced. No guest,
representative or coordinator identity fallback is accepted.

GET requires the request to be owned by the logged-in member and completed. Missing
or other-owner requests return 404; unfinished requests 409; no login redirects to
/login. Existing saved feedback redirects to owned request details instead of
offering another form. Private responses retain no-store headers.

POST requires the hidden member CSRF token, an explicit is_helpful=yes/no form value,
and optional comment at most 2000 characters. Numeric/string-boolean/rating input is
rejected rather than guessed. Client member_id/organization fields are ignored.
The existing bearer-only JSON endpoint /api/requests/<id>/feedback remains unchanged;
cookies do not become an implicit authorization fallback for other APIs.

## Atomic submission and event flow

The native form adapter calls the unchanged submit_feedback transaction service with
the server-owned member ID and explicit boolean. It rechecks active SQL role,
request ownership/completed state and saved completed referral/organization under
request-first locks, then commits feedback and FeedbackSubmitted outbox together.
Same-answer/comment repeats return the existing feedback without another event;
different details return 409 and preserve the first record. SQL failure rolls back
and returns a retryable error with selected choice/comment retained in the form.

Success redirects 303 to the existing request details page with Feedback saved in
the existing message area. That page now reads the owner's stored is_helpful/comment
and displays the approved summary rather than a rating. Comments are Jinja-escaped;
browser tests verify script-like text is inert. No new frontend JS or token export
is needed for native form submissions.

Existing outbox dispatcher, FeedbackSubmitted routing, feedback_worker.py,
representative notifications and negative-feedback coordinator alerts remain unchanged.
No new event, queue, consumer or notification business key is created by this UI phase.
Original completion, attendance, priority, deadline and capacity are preserved.

## Exact files and database effects

Changed app/member.py (owned form route and saved summary), app/frontend.py (existing
feedback endpoint alias), frontend/templates/individual/feedback.html and
frontend/templates/individual/request_details.html.
Added tests/test_member_feedback_ui.py, docs/events/MemberFeedbackUI.md and
docs/testing/MemberFeedbackUI_TEST_GUIDE.md.
The existing API and feedback service files were reused without edits.
No schema, model, migration, baseline, seed, credentials, account role or CSS changes.
Reads use existing ownership/profile/request/history/feedback data; writes occur
only through the existing feedback service on intentional form submission.

## Verification and limits

Tests cover both answers, approved labels, owned completed-state access, CSRF,
strict choices/comment length, bearer-only API contract, injected identity fields,
saved summary, duplicate/conflicting POSTs, outbox rollback, retry form retention,
no capacity/status mutation, browser navigation and escaped comments.
Focused/full-suite results are in the testing guide. Firebase is mocked and SQL
is disposable; live cookie/SQL/broker operation remains a user-run integration test.
MySQL contention and actual broker redelivery remain separately scoped checks.
No live feedback or notifications were submitted during implementation.
Profile editing/cancellation and other pending navigation remain outside this phase.
