# CareConnect: work completed and check-in demonstration

November 3, 2026: remaining agreed page integrations and separate hosting configuration
have been prepared. See [remaining features and actual tests](docs/testing/REMAINING_FEATURES_TEST_GUIDE.md)
and [hosting runbook](docs/hosting/HOSTING_RUNBOOK.md). The latest full suite passed
573 tests. Docker/Compose image validation and actual cloud deployment remain pending;
no schema/import, live deployment or git publishing action was executed.

Current update (November 1, 2026): this document's original check-in summary below
is historical. Authentication, referral lifecycle, feedback, organization approval
and service management have since been implemented. See
[Partner C checks and tester handoff](docs/testing/PartnerC_TESTER_HANDOFF.md) for
the latest smoke checks, known issues and remaining-feature review. Partner C's
full end-to-end workflow is handed to the team tester rather than repeated here.

Prepared October 27, 2026 for the ENSF 607 October 28 check-in.

## What we have accomplished

We turned the initial request API and RabbitMQ messaging utilities into a working
event-driven referral workflow. A member's request now causes a separate matching
worker to choose an eligible partner, reserve capacity and create a referral.
A separate notification worker then stores an in-app alert for that partner's representative.

The architecture remains Flask + SQLAlchemy + MySQL + RabbitMQ/Pika.
No extra framework or external notification service was introduced.
This is the initial working referral flow, not the complete final application.

## Starting point and review

We reviewed the application, SQL schema/seed/queries, configuration, tests and Git history.
The main gap was that worker.py and the referral/deadline modules were empty.
The supplied demo consumer only printed events; it did not create referrals or notifications.
The dependency manifest contained environment assignments rather than dependencies.
There were also inconsistent example connection settings and no application test suite.

## Implemented event flow

```text
Member submits POST /api/requests
    -> Flask validates input
    -> MySQL transaction saves request + ServiceRequestCreated outbox record
    -> Outbox dispatcher publishes ServiceRequestCreated to RabbitMQ
    -> matching_queue delivers it to worker.py
    -> Matching transaction creates referral + history, reserves capacity,
       marks request matched, and stores ReferralCreated in the outbox
    -> Dispatcher publishes ReferralCreated to RabbitMQ
    -> notification_queue delivers it to notification_worker.py
    -> MySQL stores an alert for the selected organization's representative
```

The outbox is a database table holding events awaiting publication. It closes the
gap where a database commit could succeed but a broker outage could lose the event.
Flask does not need RabbitMQ publication to complete during the HTTP request.

## Matching rules and transactions

The matching worker loads authoritative request data from MySQL rather than trusting
eligibility fields from the event payload. It requires:

- An approved organization.
- An active organization offering and active catalog service/area.
- Exact support for the selected priority.
- The selected service and area.
- Spare active-referral capacity.

Eligible offerings are ranked by fewest active referrals, highest acceptance rate,
then highest on-time attendance rate. IDs provide a deterministic final tie-breaker.
Acceptance rate currently includes accepted/attended/completed referrals divided by
all referrals. On-time rate includes recorded attendances and overdue accepted referrals
that never received attendance. An undefined rate ranks as zero.

Request-level locking and state checks prevent repeated initial matching. Eligible
offerings are locked, and a conditional increment reserves capacity. The referral,
initial history, reservation, request status and outgoing event commit together or roll back.

The original request priority and attendance deadline are preserved. The referral's
response window is two hours, capped by the attendance deadline. No eligible partner
or an expired deadline produces an unmatched request and coordinator notification.
If no active coordinator exists, processing rolls back and remains retryable.

## Duplicate handling and recovery

- The database allows only one active referral per request (sent, accepted or attended).
- A processed request is not matched again, even if a duplicate event has a different ID.
- Outbox records have stable event IDs and unique business-event keys.
- The dispatcher uses persistent messages, publisher confirmations and mandatory routing.
- Publication failures retain the outbox record and schedule a delayed retry.
- Representative notifications use a unique key per business action and recipient.
- Messages are acknowledged only after successful database processing.
- Business-processing failures are requeued; worker connections retry after failure.

Delivery is at least once: a crash after publishing but before recording success can
publish the same event again. Idempotent handling prevents duplicate business effects.
There is no claim of exactly-once delivery.

## Database setup actually completed

The configured Docker MySQL database was initially empty. With separate approval,
we created the baseline using database/schema_safe.sql and applied migration 001.
We did not execute the destructive schema.sql or seed.sql scripts.

Verified on MySQL 8.0.46:

- 21 tables: the existing 20-table domain schema plus event_outbox.
- Unique active-referral index.
- Capacity bounds and outbox attempt-count checks are enforced.
- Notification and outbox deduplication indexes exist.
- The temporary migration procedure was removed.

Both baseline SQL files remain unchanged; migration 001 is required after either baseline.
Migration evidence and resulting table definitions were saved under migration_backups/.

We then added a small synthetic dataset in one transaction:

| Record | Demo IDs/details |
|---|---|
| Member | User 9 |
| Coordinator | User 1 |
| Partner representatives | Users 4 and 5 |
| Approved organizations | Partners 1 and 2 |
| Service and area | Service 1, area 1 |
| Priorities | High 1 = 6h; Medium 2 = 12h; Low 3 = 24h |
| Capacity at initialization | 0/5 for each offering |

Demo data uses synthetic names and example.test email addresses. Random passwords
were hashed; no working login flow was added. The setup script refuses to run on a
nonempty database. Do not rerun it to reset the demonstration.

## Local infrastructure problems resolved

Docker was installed but its Linux engine was stopped. Docker Desktop was started,
and the MySQL/RabbitMQ services were brought up. Host-side connections use MySQL
port 3307 and RabbitMQ port 5673. The original RabbitMQ connection attempted port 5672.
Local credentials were preserved; example configuration was corrected.

## Automated verification

The recorded final test command was:

```cmd
.\.venv\python.exe -B -m pytest -p no:cacheprovider -q
```

Observed result: **26 passed, 18 warnings in 0.63s**.
The warnings concern Python 3.12 SQLite datetime-adapter deprecation.
Source parsing, application/worker imports, MySQL SQL compilation and diff checks also passed.

Tests cover eligibility, ranking, successful matching, duplicate request events,
unmatched alerts, expired deadlines, transaction rollback, notification creation and
deduplication, missing recipients, outbox retries, API/outbox atomicity, acknowledgements
and publisher confirmations.

The suite uses a disposable in-memory SQLite database with explicit MySQL SQL adapters
and mocked RabbitMQ. It does not prove MySQL concurrency, migration execution or broker
persistence. Actual migration verification and the live demo are separate evidence.
See docs/testing/checkin_test_results.md for the recorded automated results.

## Live demonstration evidence so far

### Request 1: complete flow verified directly in MySQL

We observed:

- Request 1 became matched with High priority and its attendance deadline retained.
- Referral 1 was created for organization 1, attempt 1, status sent.
- One initial referral status-history row was stored.
- ServiceRequestCreated and ReferralCreated were both published on their first attempt.
- Both outbox records had publication timestamps and no last error.
- Representative user 4 received a referral_sent notification with key referral-created:1.
- Organization 1's offering used 1/5 capacity; organization 2 remained at 0/5.

This verifies the complete API -> MySQL -> RabbitMQ -> matching -> referral -> notification path.

### Request 2: latest rehearsal

The user submitted a fresh request titled "Check-in demonstration" and observed:

| Field | Result |
|---|---|
| Request ID | 2 |
| POST response status | submitted |
| Later GET response status | matched |
| Priority | 1 (High) |
| Service / area | 1 / 1 |
| Attendance deadline returned by GET | 2026-10-28T04:44:31Z |

Request 2's matched status is confirmed by the supplied API response. Its notification
and outbox query results have not yet been supplied or independently checked in this
latest rehearsal. Use the runbook queries with request_id = 2 to capture that evidence.

## Files implementing the work

| File | Purpose |
|---|---|
| requirements.txt, .env.example | Dependencies and example local settings |
| app/models.py | Relevant schema mappings and protections |
| database/migrations/001_checkin_workflow.sql | Additive database protections and outbox |
| database/create_demo_data.py | Empty-database-only synthetic setup |
| app/requests.py | Atomic request and outgoing-event creation |
| worker.py, app/services/matching.py | Matching consumer and transaction |
| notification_worker.py, app/services/notifications.py | Organization alerts and coordinator handling |
| outbox_dispatcher.py, app/services/outbox.py | Reliable outgoing-event dispatch |
| app/messaging/event_publisher.py | Confirmed publication with stable IDs |
| app/messaging/event_consumer.py | Envelope validation and acknowledgements |
| app/messaging/worker_runtime.py | Consumer sessions and reconnection |
| pytest.ini, tests/conftest.py | Safe discovery and isolated fixtures |
| tests/test_workflow.py, tests/test_messaging.py | Focused automated coverage |
| docs/testing/checkin_runbook.md | Startup and live demonstration instructions |
| docs/testing/checkin_test_results.md | Recorded automated test evidence |

## How to run the demonstration

The baseline, migration and synthetic data have already been created on the configured
local database. Skip those initialization steps. Do not reset the database.

Keep Docker Desktop running. Start infrastructure if needed:

```cmd
docker compose up -d mysql rabbitmq
set RABBITMQ_PORT=5673
.\.venv\python.exe -m app.messaging.rabbitmq_config
```

Run four separate terminals from the project root:

```cmd
REM Terminal 1
.\.venv\python.exe run.py
```

```cmd
REM Terminal 2
set RABBITMQ_PORT=5673
.\.venv\python.exe worker.py
```

```cmd
REM Terminal 3
set RABBITMQ_PORT=5673
.\.venv\python.exe notification_worker.py
```

```cmd
REM Terminal 4
set RABBITMQ_PORT=5673
.\.venv\python.exe outbox_dispatcher.py
```

Keep test_consumer.py stopped; it competes for matching messages and only prints them.
Follow docs/testing/checkin_runbook.md for the POST command and read-only evidence queries.
Use the actual returned request ID. Each submission consumes capacity; the current flow
does not release it. A matched API response alone is not proof of notification delivery.

## Remaining work and honest check-in scope

The initial asynchronous referral flow works. These features remain unfinished:

- Real login, role-based access and complete contact-disclosure privacy.
- Accept/reject operations, timeout scanning, backup referrals and three-attempt escalation.
- Attendance recording, overdue processing and completion.
- Capacity release when a referral finishes or fails.
- Feedback processing and correction of the original schema's star-rating mismatch.
- Notification UI; current in-app alerts are stored in MySQL and demonstrated through SQL.
- Bounded retries/dead-letter queues; malformed envelopes are discarded and permanent
  business failures can retry repeatedly.
- MySQL concurrent-worker and crash/restart integration tests.
- Reconciliation of any old capacity data if another dataset is imported.

Before the check-in, save terminal/database screenshots and test output, review/commit
the implementation, and provide an architecture diagram and individual contribution
evidence. This document does not establish that those remaining course deliverables
are complete or that all changes have been committed.

## What to tell the evaluator

"We implemented an event-driven initial referral workflow. Flask saves the request and
an outbox event together. RabbitMQ delivers the event to a matching worker, which checks
partner eligibility and ranking and atomically creates a referral and reserves capacity.
A second event drives a separate worker that stores the organization notification.
We demonstrated the complete path and have 26 passing focused tests. The remaining
acceptance, backup and attendance workflows are planned for the final delivery."
