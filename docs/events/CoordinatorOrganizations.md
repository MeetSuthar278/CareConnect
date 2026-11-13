# Coordinator organization directory (read-only)

## Approved scope

Connect the existing coordinator Organizations page, status filter and expandable
details to real SQL data. My Services is deferred. Suspend/Reactivate controls keep
their existing labels/styles but are disabled type=button controls in read-only
mode, with no mutation forms. Review remains available only for a latest application
that is actually reviewable through the already implemented Approvals page.
No new page sections, labels, CSS or lifecycle actions were introduced.

## Route and authorization

GET /coordinator/organizations uses the existing verified coordinator Firebase
cookie, revocation/expiry verification, active SQL user and current coordinator
role checks. A member/representative cookie or forged Flask role cannot read it.
Responses are no-store. POST to the directory has no handler (405). No suspension,
reactivation, service editing or account-role change occurs from this page.

## Real data and status mapping

Read organizations and their latest organization_application by application ID.
Map stored approved -> Active, pending -> Pending and suspended -> Suspended to
the existing template vocabulary. If raw organization status is pending and its
latest application is rejected, display Rejected. This is an application-derived
display state; no nonexistent rejected organization enum is written. A later
submitted application returns that unapproved organization to the Pending view.
Current approved/suspended organization state takes precedence over older application outcomes.

The existing status filter applies to these displayed states. Unknown filter
strings match no rows; they are not used to construct SQL.
Contact person prefers an active SQL representative, primary first then lowest user
ID, and falls back to the latest applicant's stored member-profile name or dash.
Email, phone and location are the organization's stored fields. Applied on uses
latest application creation time, or organization creation time if none exists.

Services counts distinct configured service IDs, not area-offering rows. Areas list
configured region/city pairs from offerings, with dash when none exist. Paused
offerings still count as configured services; this is not an eligibility/capacity
claim. No data is invented for approved test organizations without offerings.
Existing unread notifications remain scoped to the current coordinator, not other users.

## Database and exact files

Reads organizations, latest applications, applicant profiles, active representative
membership/roles, offerings/areas and current-coordinator notifications. No database
writes, event/outbox rows, new routes for mutation, workers or services are introduced.
Existing matching eligibility and capacities remain unchanged.

Changed app/coordinator.py, app/frontend.py and
frontend/templates/coordinator/organizations.html.
Added tests/test_coordinator_organizations.py, docs/events/CoordinatorOrganizations.md
and docs/testing/CoordinatorOrganizations_TEST_GUIDE.md. The earlier coordinator
guide also links to this phase so its original pending-page statement is not mistaken
for the current implementation. No schema, baseline, migration, seed, role, credentials,
environment or CSS change was needed. Existing accounts and partners were not modified.

## Verification and limits

Tests cover organization details, distinct service counts across multiple areas,
all existing status filters, latest-application rejected/pending mapping, raw-state
preservation, disabled lifecycle controls/no mutation forms, coordinator-only verified
access and browser navigation/filter/keyboard expansion. Actual results are recorded
in the testing guide. SQL is disposable and Firebase mocked; no live mutation occurred.

Suspend/reactivate, My Services, reports, pagination and existing narrow-screen table
CSS behavior remain separate scopes. Existing Approvals decisions still work through
their own protected route; this list does not automatically decide applications.
