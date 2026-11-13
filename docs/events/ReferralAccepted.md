# ReferralAccepted supporting workflow

## Purpose, actor and pages

An active organization representative accepts a sent referral assigned to their
organization before its response deadline. Relevant existing pages are Incoming
Referrals and Referral Details. No frontend controls or design changed in this phase.

## API and authorization

`POST /api/referrals/<referral_id>/accept` requires a verified Firebase bearer token
and the representative role. No body is required; client identity/organization
fields are not used. The SQL user must still be active, have the representative
role and belong to the referral's organization when the transaction runs.
Missing and unowned referrals return 404; invalid state or elapsed deadlines 409;
missing authentication 401; wrong role 403; database failures 503.

Successful response:

```json
{"referral_id":123,"request_id":456,"status":"accepted","already_processed":false}
```

An authorized repeat returns already_processed=true without another write, even
if the response deadline has passed since the original acceptance. A repeat after
the referral advances to attended/completed returns a state conflict.

## Transaction and valid transitions

1. Read parent request ID, lock request first and referral second.
2. Lock/recheck current SQL representative identity and organization membership.
3. Return idempotent success for an already accepted referral.
4. Otherwise require sent referral, matched request, future response and attendance
   deadlines, and no pre-existing responded_at on the sent referral.
5. Lock the exact offering and require a positive reserved capacity count.
6. Recheck both deadlines after the offering lock wait. Change sent -> accepted,
   set responded_at to current UTC time and append history
   with changed_by_user_id set to the representative. Commit together.

The request remains matched until the attendance workflow advances it. Priority,
attendance deadline, response deadline, rejection reason and capacity are unchanged.
Acceptance retains the original reservation; it does not create a new one or release it.
The positive aggregate capacity check cannot independently audit every reservation;
it fails closed for missing offerings or zero capacity.

## Events and notifications

This is a synchronous supporting workflow, not a new RabbitMQ event type.
There is no event envelope, exchange, routing key, queue, consumer or outbox insert
for acceptance. No new notification is sent. The existing matching and timeout
events remain unchanged. RequestAttended is a separately approved future phase.

## Concurrency, duplicate protection and rollback

Acceptance follows the request-first lock order used by rejection and timeout.
If acceptance commits first, subsequent timeout scans skip the accepted referral.
If timeout or rejection commits first, acceptance refuses the changed state.
Acceptance checks the deadline after acquiring locks; a delayed scanner does not
permit a late acceptance. Repeated acceptance never changes responded_at or adds
history. The existing active-referral uniqueness constraint remains applicable.
History/commit failure rolls back acceptance and response time together.

## Files and database access

Changed app/referrals.py and app/services/referrals.py. Added
tests/test_referral_accepted.py, this document and
docs/testing/ReferralAccepted_TEST_GUIDE.md. Existing RejectionError remains
compatible; AcceptanceError provides acceptance-specific API handling.
Reads requests, referrals, users, roles, organization_representatives and offerings.
Writes only referrals and referral_status_history. No schema, migration, seed,
credentials, messaging configuration or frontend change was required.

## Tests and limitations

24 focused tests passed (46 SQLite datetime-adapter deprecation warnings).
Tests cover ownership/role/activity, deadline boundaries, state conflicts, preserved
capacity/SLA/priority, response timestamps, rollback/retry, duplicate acceptance,
timeout-before-acceptance and acceptance-before-timeout, API errors and authentication.
Sequential state tests do not prove simultaneous MySQL lock scheduling.
No live acceptance or Firebase login was executed for this implementation.
See the testing guide for regression results and controlled live-test requirements.
