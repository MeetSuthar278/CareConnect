# AttendanceOverdue

## Purpose, actors and pages

Notify active coordinators when an open request's original attendance deadline
has passed and no attendance has been recorded. This includes requests without a
referral and unmatched requests. Relevant existing pages are coordinator dashboard,
Escalations, All Service Requests and Notifications. No frontend files changed;
this phase stores alerts but does not connect dashboard controls.

## Producer and trigger

deadline_checker.py adds an explicit `--kind attendance` mode. Existing acceptance
timeout behavior remains the default. Both modes preview by default; only `--apply`
enables writes. Attendance mode accepts repeatable `--request-id` targeting, batch
size 1–1000 (default 100), `--once`, and polling interval (default 30 seconds).
Wrong-mode ID arguments are rejected instead of silently broadening a scan.
There is no public mutation endpoint; this event is produced by the local scanner.

## Eligibility, transactions and durable flag

Discovery requires status submitted, matched, in_progress or unmatched; attendance
deadline strictly before current UTC; no attendance record; and no previous
AttendanceOverdue outbox event. Completed/cancelled requests are excluded.
At exact deadline equality attendance is still allowed; overdue requires later time.

Each candidate gets a separate transaction. Lock the request first, recheck current
status/deadline and absence of attendance, then check the unique outbox business key.
Insert one event and commit. The outbox row itself is the durable overdue flag.
No new schema column or invented status is needed. Failed records roll back and
remain eligible for retry; one failure does not roll back other requests' flags.

Request/referral outcomes, history, original priority/deadlines, attendance and
capacity remain unchanged. This event does not reject, time out, rematch or close
a request, and does not release reservations. Existing timeout processing remains
the separate owner of sent referral expiration.

## Event envelope and broker

```json
{
  "event_id":"<stable-outbox-UUID>",
  "event_type":"AttendanceOverdue",
  "event_version":1,
  "timestamp":"<UTC outbox timestamp>",
  "request_id":123,
  "payload":{"attendance_deadline":"2030-01-01T12:00:00Z"}
}
```

Unique business key: attendance-overdue:<request_id>.
Uses existing careconnect.events durable topic exchange, attendance.overdue routing
key and coordinator_queue binding. Existing publisher confirmations, stable event
IDs and recoverable outbox retry behavior are reused. No broker configuration changed.
Payload contains no contact details, descriptions or notes.

## Consumer and notifications

coordinator_worker.py runs handle_attendance_overdue through the existing worker
runtime. The handler locks the request and verifies the event's deadline against
the saved deadline and current UTC. Missing/mismatched data fails for retry/review.
It skips stale deliveries for terminal requests or saved timely attendance.

If attendance arrives late after the flag was committed, the deadline was still
missed: the consumer sends the overdue alert, preserving in_progress status.
RequestAttended may independently send its late-attendance alert. These represent
different facts and use different business keys. If any attendance already exists
before discovery/recheck, no new overdue event is created; the late-attendance
workflow handles late records instead.

Active SQL coordinators receive notification type deadline_missed with title
Attendance deadline missed and key attendance-overdue:<request_id>. All recipient
writes commit together. Missing coordinators or notification errors roll back and
requeue the event. The worker acknowledges only after successful processing.

## Concurrency and duplicates

The same request-first lock order serializes the scanner with attendance recording,
matching and timeout processing. The absence of attendance is rechecked under the
request lock. All approved writers must keep this lock discipline.
Unique event_outbox.deduplication_key prevents repeated flags; notification uniqueness
on (user_id, deduplication_key) prevents repeated alerts even with changed envelope IDs.
Already flagged requests leave subsequent discovery batches. Consumer retries do
not mutate existing history or original outcomes.

## Database access and exact files

Reads: service_requests, attendance_records, event_outbox, users and roles.
Writes: event_outbox (producer) and notifications (consumer).
Changed: deadline_checker.py.
Added: app/services/overdue.py, coordinator_worker.py, tests/test_attendance_overdue.py,
docs/events/AttendanceOverdue.md, docs/testing/AttendanceOverdue_TEST_GUIDE.md.
No model, migration, baseline, seed, credential or frontend change was needed.
Only this module's disposable test fixture gains the existing production request_id
field; no live database DDL was executed.

## Verification, risks and limits

Tests cover missing attendance/referrals, supported and terminal states, exact
deadline boundaries, locked rechecks, attendance arrival before delivery, duplicates,
outbox/notification rollback and retry, active coordinator delivery, per-record batch
failure isolation, target filters, invalid events, safe CLI modes and worker dispatch.
Actual results and commands are recorded in the testing guide.

No live overdue scan, event delivery or data mutation was executed. SQLite tests
cannot prove MySQL contention/foreign-key behavior. Direct SQL writers that bypass
request locks are unsupported. No DLQ/bounded requeue was added. Persistent failures
among the oldest limited batch need investigation or explicit targeted processing.
The overdue flag is historical; there is no resolved-alert dashboard or clearance
workflow yet. No new replay API, completion or feedback workflow was introduced.
