# ReferralRejected

## Purpose, actors and pages

An authenticated organization representative can decline a sent referral belonging to their
organization. The system releases the reservation and asynchronously tries another eligible
partner. This supports SDG 17 through actual backup coordination across partners.
Relevant team UI: organization/requests.html and organization/request_details.html; member request
views and coordinator attention views reflect resulting stored states when integrated.
Those frontend buttons/pages are NOT connected by this backend-only event phase. No UI changed.

## Producer and triggering API

POST /api/referrals/<referral_id>/reject requires Authorization: Bearer <Firebase ID token>
and JSON {"reason":"Synthetic demo rejection"}. Reason must be a trimmed 1-255 character string.
app/referrals.py uses roles_required('representative') and calls app/services/referrals.py.
A successful committed rejection returns 200 with referral_id, request_id, status='rejected'
and already_processed=false. An authorized repeat returns already_processed=true without new effects.
It does not promise a backup has already been selected.

## Event envelope and payload

The existing outbox creates the stable UUID and retains it on publication retries.

```json
{
  "event_id":"<stable-outbox-uuid>",
  "event_type":"ReferralRejected",
  "event_version":1,
  "timestamp":"<UTC creation timestamp>",
  "request_id":123,
  "payload":{"referral_id":456,"organization_id":1,"attempt_number":1}
}
```

The reason is stored in MySQL/history, not broadcast in the event. The unique business key is
referral-rejected:<referral_id>. No new event types were introduced.

## Broker and consumer

Exchange careconnect.events (durable topic), routing key referral.rejected, queue matching_queue.
Existing bindings and publisher routes already supported this event. worker.py now dispatches
ServiceRequestCreated and ReferralRejected using the shared worker_runtime. The notification worker
remains single-event and backward compatible. AcceptanceTimedOut remains outside this implementation.

## Rejection transaction and database access

1. Read referral parent ID; lock service_requests first, then referrals.
2. Recheck active SQL user/representative role and organization link inside the transaction.
3. Return idempotent success if this owned referral was already rejected.
4. Require sent referral, matched request and an unexpired response_deadline.
5. Find and lock the offering by organization_id + service_id + service_area_id. The existing
   unique offering key identifies the reserved row without introducing a schema field.
6. Decrement current_active_referrals only when positive; inconsistent capacity fails closed.
7. Set rejected, responded_at and rejection_reason; append sent -> rejected status history.
8. Set request submitted (awaiting matching) and enqueue ReferralRejected.
9. Commit all effects together. Any failure rolls back all business writes.

Reads: users, roles, organization_representatives, service_requests, referrals,
organization_services. Writes: referrals, referral_status_history, organization_services,
service_requests and event_outbox. No table/column/index/migration/seed change was made.
models.py maps existing responded_at and rejection_reason columns only.

## Backup transaction and valid transitions

The consumer locks the request and its referral history. It verifies payload IDs against the
saved rejected referral. It acts only if that source is the latest attempt, no active referral
exists, and the request is submitted. Older events and completed work are harmless no-ops.
A delayed ServiceRequestCreated event also ignores a request with referral history.

It enforces contiguous attempt numbers and at most three attempts. All previously attempted
organizations are excluded, regardless of current capacity/status. It preserves the request's
original priority and attendance deadline. The shared matching helper retains approval, active
service/area/offering, exact priority, area/service and capacity checks; ranking remains workload,
acceptance rate, on-time rate, then deterministic IDs.

An eligible backup gets the next attempt number, is_backup=true and sent status, initial history,
atomic capacity reservation and ReferralCreated outbox record; request returns to matched.
The existing ReferralCreated consumer then stores the representative notification.
No eligible backup, exhausted three attempts or expired attendance deadline marks unmatched and
alerts active coordinators in the same consumer transaction. No fourth attempt is created.

The two-hour response window is still capped by the original attendance deadline. Missing coordinator
rolls back the consumer transaction for retry; the earlier rejection remains durably committed.

## Authorization, privacy and idempotency

Firebase verifies identity; SQL supplies the role and organization. No demo identity or client-supplied
organization is trusted by this API. Another organization's referral returns 404. Member/coordinator
roles cannot use the representative action. The service rechecks active role/link after locking.
No member contact details are returned. Test data and rejection reasons must remain synthetic.

Request locking, state checks, existing active-referral uniqueness and request/attempt uniqueness
protect concurrent processing. Capacity release belongs ONLY to the rejection transaction, not the
backup consumer. Repeated requests preserve the first reason/time/history/event even after expiry.
Repeated events cannot advance a newer rejected attempt or reserve twice. Delivery remains at least
once, not exactly once; a persistent event-processing ledger was not added.

## Errors and retries

400 invalid JSON/reason. 401 missing/invalid token. 403 wrong role/unverified/inactive identity.
404 missing/unowned referral. 409 invalid state, expired response or inconsistent capacity/offering.
503 database transaction failure; no partial rejection commit. Firebase/account lookup can independently
return existing authentication-service errors. Missing users/relationships are not silently repaired.

Existing outbox retries retain ID/timestamp and use publisher confirmations. Consumers acknowledge
only after transaction completion; handler exceptions requeue and reconnect with delay. A crash after
confirmed publish/before recording publication can redeliver safely. HTTP retry after rejection commit
is idempotent. No automatic API retry is introduced.

## Automated tests and remaining limits

See tests/test_referral_rejected.py: atomic rejection, repeated API/events, exclusion, backup SLA,
three-attempt escalation, stale source and initial events, expired state, wrong role/organization,
rollback of both transactions, capacity inconsistency, coordinator absence, backup notification and
worker dispatch. Existing initial matching/authentication/notification tests are retained.

Tests use isolated SQLite and mocked Firebase; MySQL row-lock races and live broker/crash recovery
are not established by them. No live rejection was run in this implementation phase.
No live records were modified. Frontend action wiring, acceptance/timeout/attendance remain separate.
The baseline lacks a direct offering FK on referrals; this implementation assumes request service/area
are immutable and offerings remain available as records. Missing/inconsistent data fails for coordinator
review rather than changing schema or guessing which capacity to release.
No bounded retry/DLQ policy was added. Request status is submitted during the asynchronous backup gap;
clients must not assume matched until matching finishes. A missing representative for the backup causes
the existing notification worker to retry separately from matching.


## Recorded implementation verification

Final full-suite command: `.\.venv\python.exe -B -m pytest -p no:cacheprovider -q`
Observed result: **96 passed, 73 warnings in 24.97s** (30 rejection/backup cases included).
Warnings are Python 3.12 SQLite datetime-adapter deprecations. Source AST parsing,
MySQL referral-mapping/locking compilation and git diff --check passed.
The tests did not apply SQL migrations or change live data. MySQL concurrency and
live HTTP -> RabbitMQ -> backup -> notification verification still require local testing.
No frontend/CSS/template changes, schema changes, Git commits or pushes occurred in this event phase.


## Confirmed live test - October 29, 2026 (America/Edmonton)

The user ran the CMD helper with the approved representative test account. API response:
200, referral_id 9, request_id 9, status rejected, already_processed false.
The helper observed request 9 return to matched. Subsequent read-only MySQL verification confirmed:

- Referral 9: organization 1, attempt 1, rejected; reason and responded_at persisted.
- History: sent -> rejected recorded with acting user_id 10.
- Referral 10: organization 2, attempt 2, is_backup=1, sent; initial history persisted.
- Original offering reservation released: Partner A 5/5 -> 4/5.
- Backup reservation added: Partner B 4/5 -> 5/5.
- ReferralRejected and backup ReferralCreated both published on attempt 1, with no last error.
- Backup notification stored for user 5, key referral-created:10.
- Request 9 is matched, priority_id=1, attendance_deadline=2026-10-30 06:37:09 UTC.

This confirms the authenticated HTTP rejection -> outbox -> RabbitMQ -> backup matching ->
notification happy path. Duplicate/race/failure cases remain covered by isolated tests, not this
single live test. No live broker crash/concurrent-worker stress test was performed.
Two synthetic requests were created to respect workload ranking during preparation: request 8
matched the less-loaded Partner B; request 9 then matched Partner A. Both records were retained.
No password, email address, Firebase UID, bearer token or private credential is recorded here.
Partner B is now full; further demonstrations must account for existing capacity without resetting data.
