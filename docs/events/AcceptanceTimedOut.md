# AcceptanceTimedOut

## Purpose and scope

Release a sent referral's reservation when its response deadline passes, then try
another partner. This backend event uses the existing architecture and tables.
No frontend, schema, seed, credentials or live application data changed in this phase.

## Producer and trigger

`deadline_checker.py` discovers sent referrals with response_deadline <= current UTC
time. Default mode only previews IDs. `--apply` explicitly enables processing;
`--once` stops after one batch; repeat `--referral-id` to restrict candidates.
The default batch is 100 (maximum 1000), with 30 seconds between scans.
Each candidate gets an independent transaction; a failed record remains retryable.

## Atomic timeout transaction

`app/services/timeouts.py` reads the parent ID, locks the request first and referral
second, then rechecks matched/sent state and deadline. A stale candidate is skipped.
Unexpected response data or a missing/inconsistent offering fails closed.
It locks the exact organization/service/area offering, conditionally releases one
reservation, changes the referral to timed_out, appends sent -> timed_out history,
changes the request to submitted, and inserts the outbox event together.
The history actor is NULL. responded_at and rejection_reason remain unchanged:
the organization has not responded. Any failure rolls back all these writes.

## Envelope and routing

```json
{
  "event_id": "<stable-outbox-UUID>",
  "event_type": "AcceptanceTimedOut",
  "event_version": 1,
  "timestamp": "<UTC timestamp>",
  "request_id": 123,
  "payload": {"referral_id": 456, "organization_id": 1, "attempt_number": 1}
}
```

Unique outbox business key: `acceptance-timed-out:<referral_id>`.
Existing dispatcher publishes with confirmations and recoverable retries to the
durable topic exchange `careconnect.events`, routing key `referral.timeout`.
The existing `matching_queue` binding delivers to `worker.py`.

## Consumer and backup rules

`handle_acceptance_timed_out` shares backup matching with ReferralRejected.
It locks the request and referral history, validates the saved source status,
deadline, organization and attempt, and processes only the latest source while
the request is submitted and no active referral exists.

Previously attempted organizations are excluded. Eligibility requires approval,
active service/offering/area, supported priority, exact service/area and capacity.
Ranking remains fewest active referrals, highest acceptance rate, then highest
on-time attendance rate, with deterministic ID ties.
Backup referral/history, conditional capacity reservation, request state and
ReferralCreated outbox insertion commit together. The original priority and
attendance deadline are preserved. The existing response window is capped at
the original attendance deadline.

After three total attempts, no eligible partner, or an expired attendance deadline,
the request becomes unmatched with an in-app coordinator alert in that transaction.
The existing notification consumer handles ReferralCreated for the selected
organization's representative; this phase adds no separate timeout notification.

## Concurrency, retries and failures

Request-first locks serialize scans, rejection and backup processing for a request.
Locked state checks prevent repeated capacity releases. The existing active-referral
unique key, outbox business key and notification deduplication remain final guards.
Old events cannot advance newer attempts; duplicate deliveries are no-ops.
Existing worker runtime acknowledges only after database processing succeeds;
failures roll back and requeue. Publication retries preserve the event ID.

## Files and database access

Changed: deadline_checker.py, worker.py, app/services/matching.py.
Added: app/services/timeouts.py, tests/test_acceptance_timeout.py, this document,
and docs/testing/AcceptanceTimedOut_TEST_GUIDE.md.
Reads existing requests/referrals/offerings and matching eligibility/history tables.
Writes existing referrals, referral_status_history, organization_services,
service_requests, event_outbox and coordinator notifications only when run explicitly.

## Verification and limits

Focused isolated tests: 27 passed, 62 SQLite datetime-adapter deprecation warnings.
Coverage includes boundaries, stale states, repeated scans/events, transactional
rollback/retry, capacity inconsistency, backup selection, shared rejection guards,
three attempts, coordinator escalation, notification creation and CLI preview safety.
See the test guide for full-suite results and commands.

No live timeout scan or MySQL/RabbitMQ timeout demonstration was executed.
SQLite tests do not prove MySQL row-lock contention behavior. The future acceptance
endpoint must use the same request-first locking and recheck the deadline; it is
not implemented here. Existing poison messages can requeue indefinitely; no DLQ
was added. Persistent failing oldest candidates can occupy a limited batch and
require coordinator investigation or explicitly targeted scanning.
