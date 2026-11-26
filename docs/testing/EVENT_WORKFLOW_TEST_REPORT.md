# Event workflow verification

PASS: real MySQL and RabbitMQ workers passed the disposable integration suite.
No existing live queue was consumed or purged. Before testing, the existing
`careconnect.events` exchange and all five queues existed with zero ready messages
and zero consumers. The current database outbox had zero unpublished rows.

The application does not launch workers from Flask or `run.py`. Five consumers,
an outbox dispatcher and two deadline scanners are separate processes. The new
local supervisor starts these eight background processes plus Flask. Hosted Compose
already defines the corresponding services.

| Event / producer | Version-1 payload | Topic route / queue | Consumer and verified effect |
| --- | --- | --- | --- |
| `ServiceRequestCreated` / `guest_requests.create_guest_request` | member_id, service_id, area_id, priority, attendance_deadline | `request.created` / `matching_queue` | `worker.py` → `handle_request_created`: eligible approved partner, reservation, attempt, history and ReferralCreated outbox in one transaction. |
| `ReferralCreated` / `matching.create_referral_locked` | referral_id, organization_id | `referral.created` / `notification_queue` | `notification_worker.py` → primary representative alerts, or active representatives if no primary; stable per-recipient business key. |
| `ReferralRejected` / `referrals.reject_referral` | referral_id, organization_id, attempt_number | `referral.rejected` / `matching_queue` | Release once, next untried eligible partner; original priority and attendance target retained. |
| `AcceptanceTimedOut` / `timeouts.expire_referral` | referral_id, organization_id, attempt_number | `referral.timeout` / `matching_queue` | Expire only an overdue sent attempt, release once and match backup or escalate. Replayed expiry has no second effect. |
| `RequestAttended` / `attendance.record_attendance` | referral_id, attendance_id, is_on_time | `request.attended` / `sla_queue` | `sla_worker.py` recomputes timing from SQL, no alert if on time; one alert per coordinator if late. |
| `AttendanceOverdue` / `overdue.mark_overdue` | request_id | `attendance.overdue` / `coordinator_queue` | `coordinator_worker.py`: deduplicated attention notifications; rechecks resolved cases and does not alter SLA/capacity. |
| `FeedbackSubmitted` / `feedback.submit_feedback` | feedback_id | `feedback.submitted` / `feedback_queue` | `feedback_worker.py`: partner notification; negative feedback additionally alerts all active coordinators. |

All routes use the durable topic exchange `careconnect.events`. Envelopes carry
event_id, event_type, event_version=1, timestamp, request_id and payload. Outbox IDs
and timestamps remain stable through retries; persistent AMQP messages use publisher
confirms and mandatory routing. SQL writes and enqueue share a transaction. The
dispatcher locks one due row with `FOR UPDATE SKIP LOCKED`, marks published only
after confirmation and backs off failed publication without changing its ID.

Acceptance, completion, cancellation, organization decisions/status changes and
profile/offering updates are synchronous SQL actions. There are no implemented
`ReferralAccepted` or `ServiceCompleted` events. Acceptance retains capacity;
completion releases it once. Approval and escalation notifications are written
transactionally, without an additional RabbitMQ event. An `is_read` column exists;
do not describe it as an implemented notification mark-read UI.

## Test evidence

`tests/integration/test_live_workflows.py` uses a fresh schema, synthetic records,
five actual consumer subprocesses and the actual dispatcher. It verifies primary
selection/notification, decline and timeout backups, distinct partners, maximum
three attempts, coordinator alerts, no-capacity handling, manual rescue, on-time
and late attendance, overdue alerts, completion/capacity release, both feedback
outcomes, duplicate delivery without duplicate effects and outbox retry after an
injected publication failure. Concurrent matching proves a one-slot offering is
reserved only once under MySQL locks; the generated active-slot unique constraint
rejects a second active referral for one request.

The source consumer acknowledges only after the handler returns successfully.
Malformed envelopes are rejected without requeue; handler failures are nacked with
requeue and cause reconnect/backoff. Regression tests verify those branches using
a fake channel; business delivery and replay use real AMQP. There is no dead-letter
queue or finite business-failure retry limit, so persistent invalid business data
can keep retrying. Inspect logs and repair data deliberately; never purge important
messages as a recovery shortcut.

The supervisor test verifies controlled local startup, no duplicate starts, health,
and owned shutdown. Fixture teardown stops only its own Popen children and removes
only its own Docker containers. Forced broker restart while deliveries are in
flight and reboot recovery are NOT TESTED. No dedicated scheduled outreach worker
exists; follow-up is the implemented attention/notification/feedback workflow.

## Live demonstration follow-up

The owner reported starting all nine processes and observing automatic capacity
release. The November 26 read-only audit independently counted six published
AttendanceOverdue events, one published AcceptanceTimedOut event and 28
coordinator notifications with overdue or unmatched keys. After migration 003,
the owner verified processing of three additional pending AttendanceOverdue
events. The final outbox has nine AttendanceOverdue and one AcceptanceTimedOut
published, with zero pending events, publication errors and deadline candidates.
Post-migration capacity reconciliation returned zero mismatches. The isolated suite independently verified managed
startup, acceptance timeout and capacity release.
