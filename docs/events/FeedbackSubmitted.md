# FeedbackSubmitted

## Purpose, actor and pages

The member who owns a completed request can submit one yes/no helpfulness response
with an optional comment. Notify the delivering organization and alert coordinators
for negative feedback. Relevant team pages are Submit Feedback, Request Details,
Notifications and Partnership Reports. This phase changes no frontend design or
scripts; it provides an authenticated backend API and consumer only.

## Producer, API and authorization

`POST /api/requests/<request_id>/feedback` requires verified Firebase bearer auth
with member role and a JSON object:

```json
{"is_helpful":false,"comment":"Synthetic feedback test only."}
```

is_helpful must be a JSON boolean, not a number or string. Optional comment is
null or at most 2000 characters; trim whitespace and normalize blank to null.
The legacy nullable rating column remains NULL; rating input is rejected. No star
rating is introduced. Identity and organization fields from the client are ignored.

Missing auth returns 401, wrong role 403, missing/unowned request 404, malformed
input 400, unfinished/inconsistent service or conflicting feedback 409, database
failure 503. Inside the transaction, recheck the active SQL member role and ownership.

```json
{"request_id":123,"feedback_id":456,"is_helpful":false,"already_processed":false}
```

## Atomic submission and valid states

1. Lock the request first; verify member_id matches the authenticated SQL user.
2. Lock/recheck active SQL member identity and require completed request state.
3. Lock/read the completion joined to its completed referral. Derive the organization
   from that saved referral, not the client or an earlier rejected partner.
4. Read feedback by unique request_id. Matching helpfulness and normalized comment
   return already_processed=true without writes. Different details return 409.
   Mismatched saved owner/organization fails closed.
5. Insert the feedback and FeedbackSubmitted outbox row in one transaction.
   Any failure rolls back both; retry never overwrites the first response.

No request/referral status, attendance, completion, capacity or original deadline
is changed. This phase does not create a feedback invitation automatically.

## Event envelope and routing

```json
{
  "event_id":"<stable-outbox-UUID>",
  "event_type":"FeedbackSubmitted",
  "event_version":1,
  "timestamp":"<UTC outbox timestamp>",
  "request_id":123,
  "payload":{"feedback_id":456}
}
```

Outbox business key: feedback-submitted:<request_id>. Payload carries no comments,
contact data, rating or user details. Existing confirmed dispatcher publishing
preserves the event ID across retries. Uses the existing careconnect.events durable
topic exchange, feedback.submitted routing key and feedback_queue binding.
No broker topology or schema change was required.

## Consumer and delivery effects

feedback_worker.py invokes handle_feedback_submitted through worker_runtime.
Lock the request and verify completed state; load authoritative feedback joined
to its request, owner, completion and completed referral/organization.
Malformed or inconsistent events fail for retry/review.

Notify active SQL representatives of the delivering organization: primary contacts
if available, otherwise all active representatives, matching the existing referral
notification policy. Use type system and key feedback-submitted:<feedback_id>.
Messages contain only request number and helpful/not helpful summary, not the comment.
Negative feedback additionally notifies active coordinators with key
feedback-negative:<feedback_id>. These notifications commit together. Missing
representatives or required coordinators cause rollback/requeue, avoiding partial
delivery. Positive feedback does not require a coordinator.

## Concurrency, duplicates and reliability

Request-first locks serialize competing submissions; existing UNIQUE(request_id)
on feedback and the outbox business-key constraint are final protections.
The first submitted_at, response and event ID stay unchanged on identical retries.
Consumer notification uniqueness on (user_id,deduplication_key) prevents duplicate
delivery even with changed envelope IDs. Worker acknowledges only after successful
processing; failures roll back and requeue. No bounded retry/DLQ was added.

## Database reads/writes and exact files

Reads requests, users, roles, completions, referrals, feedback and organization
representatives. Producer writes feedback and event_outbox; consumer writes
notifications. No other business data is modified.
Changed app/__init__.py to register the new feedback blueprint.
Added app/feedback.py, app/services/feedback.py, feedback_worker.py,
tests/test_feedback_submitted.py, docs/events/FeedbackSubmitted.md and
docs/testing/FeedbackSubmitted_TEST_GUIDE.md.
No model, migration, baseline SQL, seed, environment or frontend file changed.
Test-only tables mirror existing production tables in disposable SQLite; no live
DDL, account linking or feedback submission was executed during implementation.

## Verification and limitations

27 focused tests passed, covering yes/no results, ownership/activity/role rechecks,
all unfinished request states, completed-referral validation, duplicates/conflicts,
outbox rollback/retry, representative primary/fallback recipients, negative alerts,
missing recipients, atomic notification rollback, malformed events, API auth/errors,
no rating and worker dispatch. Actual commands/results are in the testing guide.

SQLite cannot prove simultaneous MySQL locking, foreign keys or live broker delivery.
Direct SQL writers bypassing request locks are unsupported. No editing feedback,
frontend form wiring, reporting API or invitation workflow is included.

The existing guest request form provisions a separate SQL member. Firebase login
does not automatically link accounts by email. Therefore the earlier guest CC-11
cannot be assumed to belong to any Firebase member or its representative. A live
feedback test requires a completed synthetic request owned by the authenticated
member; do not grant roles or change ownership as a workaround. Guest feedback or
account-linking would need a separate approved design and implementation.
