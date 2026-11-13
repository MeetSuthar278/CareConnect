# Organization Suspend / Reactivate

The existing coordinator Organizations buttons now POST to
`/coordinator/organizations/<org_id>/status`. The existing appearance is preserved.
Application approval remains a separate endpoint; pending/rejected applications
cannot be activated through lifecycle controls.

The verified, current SQL coordinator session and CSRF token are required. The
service locks the organization and rechecks the coordinator's active SQL role
inside the transaction, using the same organization-before-user order as approval.
Suspend changes approved to suspended; Reactivate changes suspended to approved.
An immediate repeated desired state succeeds without another write. Invalid
actions, missing organizations and unauthorized actors fail without a status change.
The redirect is fixed to the directory. SQL failures roll back.

Only organizations.status changes. Offering status, reservation counts, prior
referrals, original deadlines, accounts and application decisions remain intact.
Suspension does not cancel work. Existing portal behavior blocks accepting sent
referrals while suspended; accepted work retains attendance/completion paths.
Bearer referral APIs retain their existing role/ownership rules; this phase does
not add a new organization-status check to those APIs.
Reactivation preserves individually paused offerings. Existing matching requires
organization status approved in its locking candidate query, so suspended partners
cannot receive new referrals. Concurrent transactions may wait; an already committed
referral remains valid. MySQL can choose a deadlock victim; failed actions must retry.

No migration, new table, RabbitMQ event or notification is introduced. Existing
organization_availability records offering pause/resume, not organization suspension,
so it is deliberately not used as a false lifecycle audit. There is no persistent
actor/reason/timestamp history for organization status in the current schema.
There is also no lifecycle version column: immediate duplicate requests are harmless,
but a previously saved form submitted after a full opposite-state cycle is treated
as a new action. Reload before acting; this is not durable action-ID deduplication.

SQLite tests prove logical behavior and rollback, not MySQL locking or deadlocks.
Live organization data was not changed during implementation.
