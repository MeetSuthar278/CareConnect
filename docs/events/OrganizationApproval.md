# Organization application approval and rejection

## Scope and existing design

Connect the team's existing Organization Approvals page and Approve/Reject controls.
The approved native rejection-reason prompt collects 1–255 characters. Add hidden
CSRF/application IDs only; retain labels, confirmation, table, CSS and layout.
This phase does not implement organization signup, role grants, suspension,
reactivation, reassignment or automatic rescue of unmatched requests.

## Routes and coordinator authorization

GET /coordinator/approvals lists the latest submitted/under_review application for
each pending organization. Historical/rejected applications, decided applications,
approved/suspended organizations and pending organizations without applications
are excluded. No application is fabricated for legacy/demo partners.
The coordinator dashboard's Organizations to approve count now uses this same
reviewable-application definition, so rejected applications do not remain waiting.

POST /coordinator/organizations/<org_id>/decision requires the existing verified
coordinator Firebase cookie, current active SQL coordinator role, matching session
CSRF token, exact application_id and action approve/reject. Role/actor IDs from
the client are ignored. Unauthenticated requests redirect to login; missing CSRF
returns 403; invalid ID 400; unowned/mismatched application 404. Other service
validation/conflicts appear in the existing flash area with a 303 return to approvals.
The return URL is fixed, never taken from the posted return_to field.

## Transaction and transitions

1. Lock organization first, then the exact organization/application row.
2. Lock/recheck the SQL coordinator's active role inside the transaction.
3. Verify the application is the latest for that organization under lock. An old
   form cannot decide a newer resubmission or another organization's application.
4. Identical decided-action/normalized-reason repeats return already_processed=true
   without updating the original reviewer, timestamp, notes or notification.
   Conflicting decisions/details or changed organization lifecycle return conflict.
5. New decisions require organizations.status=pending and application status
   submitted/under_review, with an existing submitted_by_user_id recipient.
6. Save application status approved/rejected, reviewed_by_user_id, decided_at in
   server UTC whole seconds, and decision_notes (trimmed rejection reason; null on approval).
7. Approval changes the organization to approved. Rejection leaves it pending and
   therefore unapproved/ineligible for matching. Organizations has no rejected enum:
   do not misuse suspended, delete records or add a schema workaround.
8. Insert one applicant system notification and commit together. Notification failure
   rolls back both application and organization changes; a safe retry can finish.

Organization row locks serialize competing decisions; state checks prevent a second
decision and existing notification uniqueness is the delivery backstop. Future
application writers must follow organization-first locking. Old applications remain
stored; this service does not mass-update/delete them when a new application exists.

## Notifications and applicant display

Notify only submitted_by_user_id with type system, no related request and business
key organization-application:<application_id>:decision. The plain message contains
the approved/rejected outcome and rejection reason if present. Existing escaping
protects display; it is not inserted as HTML.
Representatives see their own deliveries in the existing organization bell. The
member dashboard now also loads its own unread notifications (newest ten), so a
member applicant can see the decision without being promoted to representative.
No other user's notification is displayed. This phase creates no role or membership.

There is no new RabbitMQ event type, outbox, queue or worker: decision and in-app
delivery are one MySQL transaction. Matching continues to require approved status,
active service/offering, supported priority, exact area and capacity. Approval
does not activate offerings, add capacity or retroactively rematch old requests.

## Data and exact files

Uses existing organization_applications, organizations, users, roles,
organization_representatives, member_profiles and notifications. Only organization
status (on approval), application decision fields and notification rows are written
when a user intentionally submits a decision. No credential, UID, password or role changes.

Changed app/coordinator.py, app/frontend.py, app/member.py (applicant notification
bell only), frontend/templates/coordinator/approvals.html and
tests/test_coordinator_workflow.py (disposable fixture mirrors existing application table).
Added app/services/organization_approvals.py, frontend/static/js/organization-approvals.js,
tests/test_organization_approvals.py, docs/events/OrganizationApproval.md and
docs/testing/OrganizationApproval_TEST_GUIDE.md.
The earlier CoordinatorWorkflow_TEST_GUIDE.md also points to this phase and updates
its pending-count comparison to the reviewable-application definition.
No schema, model, migration, baseline, seed, environment or CSS change was required.

## Verification and limitations

Focused checks exercise both decisions, actor/time/notes, identical/conflicting
repeats, stale/mismatched applications, active coordinator recheck, pending lifecycle,
under_review state, notification rollback/retry, applicant bell scoping, CSRF,
fixed redirect, existing matching eligibility and native prompt/confirmation cancellation.
Actual results are in the guide. SQL is disposable and Firebase is mocked; no live
organization/application decision was performed by implementation.

MySQL concurrent review/insertion races remain a live integration check. The existing
organization dashboard still displays raw organization pending state after application
rejection; its generic waiting note is not reconciled by this coordinator-only page
phase. The stored application decision, applicant notification and approvals list
are authoritative. Application review history/report UI and full registration/account
lifecycle reconciliation remain separate scopes. Existing city is used for the
approval table's service-area/location cell, not as a new matching rule.
