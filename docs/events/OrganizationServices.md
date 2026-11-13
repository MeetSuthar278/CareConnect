# My Services — owned availability and referral limits

## Approved scope and existing UI

Connect the existing My Services page to real organization-service-area offerings.
Enable Pause/Activate and Save Settings for Service status and Maximum active
referrals only. Keep shared catalog name/category/delivery/description, configured
area and unsupported eligibility/availability text read-only. Add Service and its
inputs remain disabled. No new sections, labels or CSS were introduced.

The existing response-window table/disabled select now show the actual fixed maximum
two-hour matching response window. It is still capped by the original attendance SLA;
it is not a configurable per-offering field. Shared services.delivery_mode supports
one existing mode, not a new multiselect persistence model. Unstored eligibility/
availability fields show dash. No schema workaround or invented data was added.

## Routes and authorization

- GET /organization/services: owned offerings, shared read-only data, history version
  and current capacity limits through the existing verified representative cookie.
- POST /organization/services: existing offering settings, with organization CSRF,
  exact organization_service_id, desired status/limit and expected state/version/limit.
- POST /organization/services/<offering_id>/availability: explicit target active/paused,
  expected status/history version and CSRF. This is not a blind toggle.

The existing role/UID/verified-email middleware applies. The transaction additionally
locks/rechecks active SQL representative membership, then locks only an offering
belonging to that representative's current organization. Wrong owner/missing offering
returns 404, missing CSRF 403, bad fields/types/range 400, stale state/capacity conflict
409, database failure 503. Successful save redirects 303 to My Services with the
existing message area. Client org IDs and shared/unsupported fields cannot grant
access; unexpected settings fields are rejected. No Add Service route is provided.

Form/DOM IDs now use organization_service_id, preserving actual catalog service_id
as data. Two areas sharing one service therefore have separate unambiguous controls.
No partner can pause a shared service globally or modify another partner's offering.

## Transactions and capacity

Follow the existing referral services' representative/user-before-offering lock
order. Recheck owned offering status, reservation count and current limit under
FOR UPDATE. A limit must be an integer 1–1000 and at least current_active_referrals.
The browser minimum reflects reservations at page load; the backend rechecks fresh
counts after locking. A conditional UPDATE repeats the count <= limit safeguard.
Reservations are neither created nor released by these settings actions.

Idempotent identical desired state/limit returns already_processed without writes.
Changed state requires expected status, latest per-offering availability history ID
and (for limit edits) previous limit to match saved values. This prevents stale
availability forms from undoing later pause/resume cycles and prevents overwriting
a different current limit. It does not introduce a schema version column.

On a real status change, insert one organization_availability row: pause/resume,
server UTC whole-second recorded_at, real representative user actor and no fabricated
reason. Journal and status/limit changes commit atomically; journal failure rolls
everything back. Limit-only edits do not invent a new availability action type or
history row, since the existing enum supports only pause/resume.

## Matching and existing work

Paused offerings are excluded by the unchanged matching eligibility query. Previously
sent/accepted/attended referrals keep their state and reservations; their existing
acceptance/attendance/completion rules continue to apply. Activate changes only
this offering's status: organization approval, catalog/area activity, supported
priority and available capacity remain required for new matching. It does not
automatically rematch old unmatched requests. No priority support or service-area
mapping is edited by this page.

This supporting workflow needs no RabbitMQ event/outbox/consumer. Existing SQL
organization_availability provides the approved pause/resume audit. There is no
new framework, schema, baseline, migration, seed, credential or role change.

## Exact files

Changed app/organization.py, app/frontend.py,
frontend/templates/organization/services.html and frontend/templates/components/macros.html.
The shared macro has optional restricted/disabled modes; its default behavior remains
available, while all current My Services calls use the restricted mode.
Added app/services/offerings.py, tests/test_organization_services.py,
docs/events/OrganizationServices.md and docs/testing/OrganizationServices_TEST_GUIDE.md.
Earlier organization navigation documentation links to this current implementation.
Matching/referral services and capacity constraints were reused without edits.

## Verification and limitations

Tests cover owned area-specific forms, role/activity/membership changes within the
transaction, pause/resume history, repeat submissions, stale cycle/limit guards,
boundary limits, preserved reservations/catalog/priority support, journal rollback,
matching exclusion while paused, existing reserved work acceptance, disabled shared/
Add controls, CSRF and a browser pause -> activate -> limit edit flow.
Actual results are recorded in the guide. SQL is disposable and Firebase mocked.
No live offering update was executed during implementation.

MySQL concurrent matching/settings contention still needs live verification. Limit-only
changes have no separate actor/history table; they compare the current expected limit.
The view's fixed RESPONSE_HOURS=2 must remain aligned if matching's shared policy is
changed later. Adding offerings, shared catalog editing, supported-priority editing,
per-offering response windows and broader availability schedules require separate
approved scope/schema/UI decisions. Existing narrow-screen table styling is unchanged.
# Approval access guard follow-up

Add Service is now implemented: see [AddService.md](AddService.md). Earlier
creation-deferred statements describe the initial status/limit implementation.

Only currently approved organizations may open My Services or update offerings.
Pending/suspended representatives retain dashboard access; the services page
redirects there with an approval message and service POST routes return 403.
The settings transaction checks the active SQL representative, locks its organization
and requires approved status before locking/updating the owned offering. This also
rejects otherwise idempotent repeats while unapproved and serializes status changes
with coordinator lifecycle updates. Lock waits/deadlocks still require normal retry.
No schema, navigation design, live data or referral workflow changes are introduced.
