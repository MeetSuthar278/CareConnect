# RequestAttended

## Purpose, actors and frontend

An organization representative confirms that assistance has started for an accepted
referral. Attendance and completion remain distinct. Relevant existing pages are
Referral Details, Request Details, Organization Dashboard and coordinator alerts.
This phase changes no frontend files or visible page content; buttons are not wired.

## Producer and API

`POST /api/referrals/<referral_id>/attend`, with verified Firebase representative
bearer authentication, calls app/services/attendance.py. No body is required.
Client-supplied timestamps, identities and SLA flags are ignored; server UTC is
authoritative. SQL role, active user and organization membership are rechecked
inside the transaction, including on repeated calls. Unowned/missing referrals
return 404, missing authentication 401, wrong role 403, state conflicts 409,
database failures 503.

```json
{"referral_id":123,"request_id":456,"attendance_id":789,
 "status":"attended","is_on_time":true,"already_processed":false}
```

The response's status describes the attendance action. Repeating after completion
returns already_processed=true without moving the completed request backwards.

## Atomic processing and valid transitions

1. Read parent ID, lock request then referral, matching rejection/timeout lock order.
2. Lock and recheck SQL representative membership. Use representative_id for the
   attendance FK and user_id for status history; these IDs need not be equal.
3. Read existing attendance by unique request_id under lock. Owned repeats for the
   same attended/completed referral return the saved result without another write.
   A mismatched attendance record fails closed.
4. New attendance requires accepted referral with responded_at, matched request,
   and an existing offering with positive reserved capacity, locked for checking.
5. Record first_attended_at using server UTC at the existing DATETIME whole-second
   precision; compare that persisted timestamp with the original attendance_deadline.
   Equality is on time. Attendance after the deadline is allowed and marked late.
   The response deadline does not block attendance after a valid acceptance.
6. Insert attendance, change referral accepted -> attended, append history with
   representative user actor, change request matched -> in_progress, and enqueue
   RequestAttended. Commit everything together; any failure rolls back all writes.

No capacity is released or newly reserved. Priority, original attendance deadline
and responded_at are preserved. No completion or feedback is fabricated.

## Event and routing

```json
{
  "event_id":"<stable-outbox-UUID>",
  "event_type":"RequestAttended",
  "event_version":1,
  "timestamp":"<UTC outbox timestamp>",
  "request_id":456,
  "payload":{"referral_id":123,"attendance_id":789}
}
```

The unique business key is request-attended:<request_id>. The existing outbox
dispatcher uses publisher confirmations and recoverable retries with the same event
ID. Existing durable topic exchange careconnect.events, routing key request.attended
and sla_queue binding are reused without broker configuration changes.

## Consumer and SLA effects

New sla_worker.py runs handle_request_attended through the existing worker runtime.
The handler locks the request, verifies the saved attendance/referral relationship
and attended/completed status, and recomputes the SLA result from stored timestamps.
It rejects mismatched event IDs or inconsistent saved flags. On-time attendance
needs no additional write. Late attendance sends active coordinators an in-app
system notification using attendance-late:<request_id> as the deduplication key.
Missing coordinators cause rollback/requeue for retry. The event carries no notes
or contact details. Late attendance does not mark the request unmatched.

## Concurrency, duplicates and failure recovery

Request-first locks serialize competing API calls. Existing UNIQUE(request_id) on
attendance_records and unique outbox keys provide database safeguards. The first
attendance timestamp, actor, history and event ID remain unchanged on retries.
The consumer's existing notification uniqueness prevents duplicate late alerts
even with a different delivery envelope ID. Worker acknowledgement occurs only
after successful database processing; failures requeue. Completed referrals remain
valid for delayed attendance-event delivery. No bounded retry/DLQ was introduced.

## Database and exact files

Reads: service_requests, referrals, users, roles, organization_representatives,
organization_services and attendance_records. Writes: attendance_records,
referrals, service_requests, referral_status_history, event_outbox; the consumer
writes notifications for late attendance. Uses the existing attendance schema,
including UNIQUE(request_id) and attended_by_representative_id foreign key.
No migration, baseline SQL, seed, credentials or live data changed.

Changed: app/referrals.py.
Added: app/services/attendance.py, sla_worker.py, tests/test_request_attended.py,
docs/events/RequestAttended.md, docs/testing/RequestAttended_TEST_GUIDE.md.
The test module expands only its disposable SQLite fixture to the existing production
attendance table shape; production schema and shared fixture remain untouched.

## Verification and limits

Focused tests cover success, exact deadline/late classification, whole-second
precision, distinct representative/user IDs, duplicates (including after completion),
ownership, invalid states, atomic rollback/retry, notification deduplication,
missing-coordinator retry, malformed events, auth/API errors and worker dispatch.
Observed results are in the testing guide. SQLite cannot prove simultaneous MySQL
locking or production foreign-key enforcement. Live API, MySQL concurrency and
RabbitMQ redelivery demonstrations remain separate approved checks. This phase
does not implement AttendanceOverdue, completion, or frontend attendance controls.
