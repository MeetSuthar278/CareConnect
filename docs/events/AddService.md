# Add an organization service offering

An approved representative can use My Services -> Add a service to select an active
shared catalog service, active service area, initial
Active/Paused status and a referral limit from 1 to 1000. The existing styling and
labels are retained, with approved service/area dropdowns. All new offerings must
support High, Medium and Low; there is no priority-selection control.
Category, description, delivery mode and the fixed two-hour response window are
display-only. Eligibility/availability text is not stored in the current schema and
remains disabled. The small organization-services.js module displays catalog details
only; the backend remains authoritative without JavaScript.

POST `/organization/services/add` requires the existing verified representative
cookie, current SQL membership and CSRF token. The payload contains only CSRF,
service_id, service_area_id, status and max_referrals. Priority IDs come exclusively
from the database, not the browser. Unknown fields (including priority_ids)
and repeated scalar fields are rejected; organization ownership never comes from
form data. Pending/suspended organizations cannot use this endpoint.

The service transaction follows the existing representative -> organization lock
order, rechecks active SQL representative role and approved organization status,
then validates/locks active service/category, area and existing priority definitions.
It locks/checks the organization's service/area tuple before inserting:

- One organization_services row, with current_active_referrals=0.
- Three service_priority_support rows (High, Medium, Low), is_supported=true.

Missing/inconsistent priority definitions fail with 503 and no offering is created.
No priority IDs are hardcoded. Existing offerings are never backfilled or changed:
an existing partial-priority offering conflicts on Add rather than silently gaining
support. Updating legacy records would require a separately approved data change.

The organization lock serializes Add operations from multiple representatives of
the same organization. Existing MySQL unique(org,service,area) and unique(offering,
priority) constraints are additional protections. Identical desired-state repeats
return the existing offering without resetting reservations, status or priority rows.
Conflicting duplicate settings return 409, preserving the original. Constraint
conflicts return 409; database failures return 503 and roll back the entire insert.
The user can retry with the same settings. MySQL lock/deadlock behavior still needs
live validation; SQLite does not prove concurrency.

Only the two offering tables are written. Existing shared services, categories,
areas, priority definitions, accounts, old referrals and deadlines are unchanged.
No capacity is reserved until matching creates a referral. A new Active offering
can receive eligible requests of all three priorities through the unchanged matcher;
Paused offerings are excluded. The matcher retains its support checks for existing
legacy records. Creation is not a pause/resume transition,
so no fake organization_availability entry is written. No outbox event is required
for this synchronous configuration action. Adding capacity does not automatically
rematch requests already marked unmatched.

Existing Edit settings still changes only status/referral limit; priority/coverage
editing, new shared catalog services and configurable response windows remain outside
this phase. No migration or baseline/seed changes are required. No live offering
was added during implementation.
