# ServiceRequestCreated - current request producers and latest team form

## 1. Purpose

Save a request reliably and asynchronously select an eligible community partner. This implements
SDG 17 partner coordination through real MySQL transactions and RabbitMQ workers.

## 2. Actors and frontend

The latest frontend/templates/public/home.html is served at /. The team request form is at
/get-connected and its existing confirmation is at /get-connected/done/CC-<request_id>.
The newly integrated flow is session-owned guest submission, not Firebase registration or private
member-dashboard integration. User 10's representative Firebase account remains independent.
The former app/templates demo files are preserved, accessible at /demo/request.
No stylesheet, visible label, page structure or technical demonstration section was added.

## 3-6. Producers, API, event and broker

- Existing POST /api/requests retains its earlier debug/testing demo behavior and contract.
- New POST /api/guest/requests accepts the team's native form with hidden CSRF/nonce fields.
- Both producers save ServiceRequestCreated in event_outbox with the business transaction.
- Exchange careconnect.events, routing key request.created, queue matching_queue.
- Outbox envelope: stable event_id UUID, event_type, event_version=1, UTC timestamp, request_id,
  payload={member_id,service_id,area_id,priority,attendance_deadline}. No contact data is broadcast.
- Guest outbox business key is guest-request:<SHA256(session-CSRF-secret + form nonce)>.
  It is deterministic for a repeated form, without adding a database column.

## 7-10. Processing, tables and state

The guest adapter validates all existing contact fields, description, priority and delivery.
The title is the description's first line, capped at 150 characters; the complete description is
preserved. The area is inferred only if exactly one active approved service area exists. The contact
city must match that area's city. Ambiguous services are omitted from the existing selector and
forged ambiguous submissions are rejected. Delivery options reflect services.delivery_mode and
are checked server-side. Because the existing service has one mode, no independent request delivery
column is invented. Changing service delivery later would require a separate historical-data decision.

First use creates a SQL member with an unguessable random password hash, and member_profiles row.
This is a guest tracking identity, not a usable Firebase login. Existing emails cause a conflict;
there is no account linking, profile overwrite or representative-role change.
The same guest session may reuse its profile only when all contact values match exactly.
All SQL identity/profile/request/outbox changes commit together. Error rolls back every new row.

Writes: users, member_profiles, service_requests, event_outbox. Reads also include roles,
services, service_categories, service_areas, organizations, organization_services and priority_levels.
No schema/migration/seed changes. Contact names map to existing first_name/last_name fields with
length validation; they are not silently truncated.

worker.py consumes the event and retains the existing eligibility, ranking, request locks,
capacity reservation, referral/history insertion and ReferralCreated outbox behavior. Outcomes:
submitted -> matched, or submitted -> unmatched with coordinator alert. Existing rejection backups
remain supported by the same worker. Full processing is asynchronous, not performed by the form.

## 11-13. Ownership, privacy, duplicates and errors

The signed Flask session stores a random CSRF secret and the newly created guest member ID.
Hidden per-form nonce plus session secret produces the unique outbox business key. The session
identity is never inferred from a client-supplied member ID or an existing email address.

Confirmation and GET /api/guest/requests/<id> require that session's active member ownership.
They never fall back to demo member 9. Confirmation shows only the owner's name; polling returns
request status/deadlines without email, address, phone or partner contact data. Private pages are
Cache-Control: no-store; session cookies are HttpOnly with SameSite=Lax. Local HTTP is for synthetic
demo use only; production requires TLS, appropriate cookie security, rate limits and retention policy.

A repeated POST with the same nonce retrieves its committed outbox record and restores ownership,
even if the first response's updated session cookie was lost. Concurrent inserts are protected by
existing unique email/outbox constraints; a losing duplicate can recover the committed record.
A new form GET intentionally creates a new nonce; it is not a global duplicate detector across
independent forms/browsers. Native Post/Redirect/Get and disabled submit guard repeated clicks.

400 invalid values/ambiguous area/delivery/city, 403 invalid CSRF, 409 email/profile conflict,
503 database/catalog failure. Errors use the existing message component. The form retains posted
values/nonce for validation correction. No automatic POST retry. Existing outbox retries, publisher
confirmations and consumer acknowledgements remain unchanged.

The existing confirmation status field displays Pending for submitted, Assigned for matched,
and Unmatched for unmatched. Polling performs only GET every ~2 seconds for up to two minutes.
It updates the existing status/response-deadline field, preserving the last verified state on
failure and using existing alert styling for recovery guidance. Reload performs only GET.
The original attendance SLA remains stored and returned by the guest status API. Existing team
copy says Response due: the displayed value is the actual latest referral response_deadline,
not a renamed attendance deadline. The original response-window hint wording is preserved pending
separate content approval; attendance and response semantics must not be conflated.

## 14-16. Evidence and limitations

See tests/test_guest_requests.py for real isolated SQL transactions, rollback, CSRF, ownership,
email conflicts, area inference, delivery/city validation, nonce replay and browser submission/polling.
Screenshots in docs/testing/team-request were visually checked using only memory-only SQL.
No live guest data was inserted while implementing/testing this phase.

Existing Event 1/2 and rejection tests are retained. No claim is made that SQLite proves MySQL
locking/concurrency. The new guest path still needs user-confirmed local MySQL/RabbitMQ testing.

Guest tracking depends on retaining the signed browser session; reference alone grants no access.
Losing the session requires a future approved recovery/account-linking workflow, not email matching.
Guest emails are not verified and must be synthetic; they cannot be used to claim existing accounts.
Firebase login still does not establish member dashboards or saved-profile sessions.
Services/signup navigation and profile management remain separate integration work.
This phase does not add AcceptanceTimedOut, attendance, completion or new event types.


## Recorded verification for this integration

Observed full command: `.\.venv\python.exe -B -m pytest -p no:cacheprovider -q`
Result: **121 passed, 77 warnings in 37.64s**, including 25 new guest-integration cases.
Warnings are existing Python 3.12 SQLite datetime-adapter deprecations.
Changed Python AST checks, both new JavaScript syntax checks and git diff --check passed.
A read-only live MySQL catalog call returned service 1, Demo Food Support, Demo Downtown/Calgary,
and In person delivery. No live guest records, profiles, requests or outbox rows were inserted.
The new browser submission/polling tests and screenshots use isolated in-memory SQL, not RabbitMQ.
Desktop/mobile form and confirmation screenshots were visually inspected in docs/testing/team-request/.
Live guest submission still requires local confirmation; prior live Event 1/2/rejection results do
not substitute for this newly integrated guest flow. AcceptanceTimedOut has not been started.


## User-confirmed live new-frontend test

The user submitted CC-10 through the latest team form. Read-only MySQL checks confirmed
request 10 matched, referral 11 sent to organization 1, and referral_sent notification
stored for user 4 (referral-created:11). ServiceRequestCreated and ReferralCreated both
published on attempt 1 with no last error. The initial Pending state accurately reflected
an unpublished outbox row while the dispatcher was not running; processing completed after
workers/dispatcher started and the user reloaded. No contact details are recorded here.
The actual attendance deadline is separate from referral 11's response deadline.
This verifies the live new-frontend guest -> outbox -> RabbitMQ -> matching -> notification path.
