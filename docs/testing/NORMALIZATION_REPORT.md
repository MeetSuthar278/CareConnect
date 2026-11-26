# Normalization and dependency analysis

The normalized source schema and migrated live database omit the stored referral
backup flag. The original dependency
`attempt_number ? is_backup` was partial because attempt number is one
component of the alternate key `(request_id, attempt_number)`.

The review covers all 21 tables. The historic PDF and diagrams remain
preserved, with the [final logical mapping](../database/FINAL_LOGICAL_MAPPING.md)
showing the normalized release. Strict 3NF across all stored and projected
fields is unproven.

## Method and assumptions

For a candidate key K, K → all attributes is the basic row-identification dependency.
A relation is 2NF only if no non-prime attribute depends on a proper subset of **any**
candidate key; a surrogate primary key alone does not prove 2NF. For each nontrivial
FD X → A, 3NF requires X to be a superkey or A to be prime. Cross-table repetition,
derived values and cached aggregates need separate examination; their existence
alone does not establish a transitive FD entirely within a relation.

The table below lists declared non-null candidate keys. A nullable UNIQUE Firebase
UID is a key only for mapped rows; nullable notification business keys have the same
qualification. MySQL permits multiple NULLs in these unique indexes. Names/emails
follow their SQL collation semantics. Additional business dependencies must be
confirmed with the team; accidental uniqueness in seven demonstration requests is
not evidence of a candidate key.

## Relation-by-relation review

Each listed candidate key determines the remaining attributes. “No other FD found”
means none established by the reviewed schema and intended business rules; it is
not a proof that undisclosed domain constraints cannot exist.

| Relation | Candidate keys / relevant dependencies | 1NF / 2NF / 3NF assessment |
| --- | --- | --- |
| roles | role_id; role_name. Each determines description/timestamp and the other identifier. | Scalar attributes; no partial/transitive non-key FD found. 3NF under these assumptions. |
| users | user_id; email. firebase_uid is a conditional alternate identifier. role_id does not determine email/profile facts. | Scalar values, no repeating roles in a cell. No partial/non-key transitive FD found. Nullable password_hash permits Firebase identities. |
| member_profiles | profile_id; user_id. Keys determine contact/location/preferences. | Separate 1:0..1 user profile; no assumed phone/address → person dependency. 3NF under listed FDs. |
| organizations | organization_id; name. Keys determine contact/location/status. | One contact address per row; city/name alone is not a new FD unless declared. No partial/transitive non-key FD found. |
| organization_representatives | representative_id; user_id. Keys determine organization, role-specific name/phone/job/contact flag. | A user represents at most one organization, an organization has many reps. Role-specific contact data is not assumed identical to member profiles. No other FD found. |
| organization_applications | application_id. Multiple dated applications per organization are allowed. | organization_id is not a key and does not determine one decision across history. Review/submitter/status/notes belong to an application event. No other FD found. |
| service_categories | category_id; name. | Independent catalog relation; no partial/transitive non-key FD found. |
| services | service_id. Category/name/delivery are not declared unique together. | Category name is joined rather than repeated; no other FD found. |
| service_areas | area_id; (city, region_name). | Neither composite-key component alone determines the area's attributes under the declared model. No partial dependency established. |
| organization_services | organization_service_id; (organization_id, service_id, service_area_id). | Status/limit vary by the whole offering, not one component. No within-row transitive FD found. Active-count cache is a cross-relation materialized aggregate requiring maintenance. |
| priority_levels | priority_id; level_name. level_name → deadline_hours, description. | Determinant is a candidate key. The three distinct hours in sample data do not prove deadline_hours is a key. |
| service_priority_support | support_id; (organization_service_id, priority_id). | is_supported depends on the entire combination; no evidence either component alone determines support. 2NF/3NF under listed FDs. |
| organization_availability | availability_id. | Event log: offering/action/time/actor/reason belong to one occurrence; many events per offering. No other FD found. |
| service_requests | request_id. | Atomic references and request facts. Immutable attendance_deadline snapshots the selected target; recomputing from today's priority settings could rewrite history. No strict within-row transitive FD proven from current assumptions. |
| referrals | referral_id and (request_id, attempt_number). The release derives backup status from attempt_number. | Removing the stored flag resolves the identified partial dependency. The virtual active_slot projection remains a status-derived integrity guard. Under the reviewed FDs no other partial or transitive dependency was found among base attributes. |
| referral_status_history | history_id. | Each transition owns actor/time/status/notes; referral_id has multiple history rows. No other FD found. |
| attendance_records | attendance_id; request_id. Intended valid-data rules make one referral own that request's one attendance, but referral_id is not SQL UNIQUE. | Scalar row. is_on_time derives from first_attended_at and another relation's deadline. This is cross-relation redundancy, not automatically a non-key FD entirely within this table. Parent agreement and timing require invariants. |
| service_completions | completion_id; request_id. Same semantic referral/request agreement qualification. | Outcome/notes belong to completion, not to every referral. No declared partial/non-key transitive FD found; duplicated parent reference needs consistency checks. |
| feedback | feedback_id; request_id. request_id determines the recorded member and completed partner. | Request is an alternate key, so request_id → member/partner is not by itself a 3NF violation. Redundant ownership references still create cross-relation update risks. |
| notifications | notification_id; (user_id, deduplication_key) is conditional on non-null key. | Title/message are opaque display text, not lists of relational recipients. Recipient is scalar. No other proven FD; NULL legacy business keys cannot be treated as a universal candidate key. |
| event_outbox | event_id; deduplication_key. | Event metadata belongs to one business event. JSON payload is an opaque versioned message document at the SQL boundary; claiming every nested JSON property is normalized relational data would be incorrect. Operational event data intentionally repeats business references. |

## Derived fields and consistency risks

Migration 001 adds virtual `referrals.active_slot = CASE status ...`. Thus status →
active_slot is another non-key dependency if this generated projection is counted
as a base relation attribute. The database computes it, preventing independent
updates, to enforce at most one active referral per request. Exclude the virtual
projection when describing normalized stored base facts; do not silently claim
every displayed attribute satisfies 3NF.

`organization_services.current_active_referrals` caches the number of sent,
accepted or attended referrals for the same partner/service/area. It supports
atomic capacity reservation and must change in the same transaction as transitions.
CHECK bounds alone cannot establish aggregate equality. The owner corrected eight
live caches. The November 26 read-only recheck found zero capacity, backup flag,
attendance parent, completion parent and feedback owner mismatches. A fresh
disposable seed and demo run also checks capacity equality.

The database's separate request/referral FKs do not enforce matching parent pairs
in attendance/completion or that feedback refers to the completed organization.
Business services check these relationships while holding the parent request lock.
Composite FKs/uniqueness could strengthen this in a future approved migration,
after reviewing existing rows, cascading behavior and indexes.

## Referral implementation and live evidence

Automatic matching starts at 1. Declines, acceptance timeouts and manual
rescue advance the last attempt if history exists. Manual assignment with no
history starts at 1. The shared constructor persists only the attempt number.
Event payloads and existing HTTP response fields are unchanged. The templates
do not read the flag. SQLAlchemy exposes a read-only hybrid property for
instance reads and ORM filtering. Academic and demo SQL retain the is_backup
output alias where it was previously displayed.

The November 26 read-only audit found 29 referrals, with 26 first attempts
and three second attempts. Flag mismatches and invalid attempt sequences
both totaled zero. The same snapshot counted 76 history rows, 17 users, four
coordinators, seven organizations, 25 offerings and 40 requests.

Migration 003 validates the legacy shape and attempt history before dropping
the flag and its index in one ALTER. Disposable MySQL verified the mismatch
and rerun guards, complete row parity for referrals and related tables,
all ten academic results, ORM filtering and the hosted schema preflight.
Fresh baselines already omit the flag. The owner rehearsed and applied migration
003 to the live database. All 21 table fingerprints and retained referral
attributes matched, and the redundant column and index were removed. The
post-migration capacity reconciliation returned zero mismatches.

The [live migration runbook](../database/REFERRAL_MIGRATION_RUNBOOK.md) gives
the exact backup, rehearsal, migration, verification and recovery commands.
The generated active slot, attendance snapshot, cross-relation parent
agreement, cached capacity and JSON outbox concerns above still apply.
