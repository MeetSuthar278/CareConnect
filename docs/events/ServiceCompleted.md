# ServiceCompleted supporting workflow

## Purpose, actor and pages

An authorized organization representative closes a service after recorded attendance.
This is distinct from acceptance and attendance, and is a prerequisite for later
feedback. Relevant existing pages are Referral Details, Request Details and organization
dashboard. This backend phase changes no frontend design, labels, controls or scripts.

## API and validation

`POST /api/referrals/<referral_id>/complete` requires a verified Firebase bearer
token with representative role, and a JSON object. An empty object defaults to
successful outcome and no notes. Allowed existing database outcomes:
successful, partially_successful, referred_to_external, unsuccessful.
Optional summary_notes must be a string of at most 2000 characters, or null.
Notes are trimmed; blank notes become null. Client timestamps, identity and
organization fields are not trusted or used. Use synthetic details only.

```json
{"outcome":"successful","summary_notes":"Synthetic service completed."}
```

Response:

```json
{"referral_id":123,"request_id":456,"completion_id":789,
 "status":"completed","outcome":"successful","already_processed":false}
```

Missing auth returns 401, wrong role 403, missing/unowned referral 404,
malformed input 400, invalid state/inconsistent data/conflicting repeat 409,
and database failure 503. Representative activity, SQL role and organization
membership are rechecked inside the transaction, including on repeated calls.

## Transaction, states and database effects

1. Read parent request ID; lock request first and referral second.
2. Lock/recheck current representative membership against the referral organization.
3. Read service_completions by unique request_id under lock. For an existing record,
   require the same referral and completed request/referral states. Matching outcome
   and normalized notes return already_processed=true. Different details return 409
   without editing the original completion or releasing capacity again.
4. New completion requires referral attended and request in_progress.
5. Lock/read attendance and require its request/referral relationship to match.
6. Lock the exact organization/service/area offering. Capture server UTC at the
   existing DATETIME whole-second precision; reject a future attendance timestamp.
7. Conditionally decrement reserved capacity only if positive; otherwise fail closed.
8. Insert completion details, set request and referral completed, append
   attended -> completed history with representative user actor. Commit together.

No attendance timestamp, original SLA, priority or previous history is rewritten.
Completion can occur after the attendance deadline; an earlier late attendance
remains late. Even unsuccessful service outcomes close the service and release
the reservation; they do not trigger automatic backup matching.
No feedback is created automatically.

## Event, broker and notifications

This is a synchronous supporting workflow, like acceptance. No new RabbitMQ event
type is needed for its atomic database effects. There is no completion payload,
exchange, routing key, queue, consumer, outbox insertion or notification in this
phase. Existing events remain unchanged. FeedbackSubmitted is a separate future
phase and must validate completed state and member ownership.

## Concurrency, duplicates and errors

Request-first locks follow existing attendance/rejection/timeout discipline.
They serialize two completions so only one transaction can release capacity.
Existing UNIQUE(request_id) on service_completions is the database backstop.
The conditional positive capacity update prevents underflow. Completion insertion,
both statuses, history and release roll back together on failure and can be retried.
No retry updates completed_at or allows an unauthorized user to discover details.
Direct SQL writers bypassing these locks are outside the supported workflow.

## Files and database access

Changed app/referrals.py. Added app/services/completions.py,
tests/test_service_completed.py, docs/events/ServiceCompleted.md and
docs/testing/ServiceCompleted_TEST_GUIDE.md.
Reads users, roles, organization_representatives, requests, referrals, attendance,
offerings and completions. Writes existing service_completions, service_requests,
referrals, referral_status_history and organization_services.
No schema, model, baseline SQL, migration, seed, credential or frontend change.
Only the module's disposable SQLite fixture creates the existing completion table
and attendance request_id field; no live DDL or service completion was executed.

## Verification and remaining limits

29 focused tests passed, covering all four outcomes, preserved attendance/SLA/priority,
one release, identical/conflicting repeats, authorization even after completion,
invalid states, missing/mismatched attendance, future attendance, inconsistent capacity,
rollback/retry, missing referral, input validation and API errors.
Actual regression results are recorded in the testing guide. SQLite cannot prove
MySQL simultaneous locking or actual foreign-key/ENUM behavior. A live authorized
completion and race test require separately approved synthetic data.
Frontend completion controls and feedback invitation/submission are not implemented
by this phase. No automatic live mutation was executed.
