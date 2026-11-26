# Frontend integration

This guide describes the active frontend and its backend contracts. Source and
synthetic-data checks are recorded in the [submission report](SUBMISSION_READINESS.md);
live infrastructure verification remains a separate team task.

## Template and asset loading

`app.frontend.render_team()` loads `frontend/templates/` and maps template
`url_for('static', ...)` calls to the `team_frontend` blueprint at `/team-static/`.
`app/templates/` and `/static/` remain separate and serve the legacy request demo.
Keep both trees and their local Bootstrap assets, license notices, and distinct layouts.

The current base template includes role navigation, notifications, flash messages,
Bootstrap, and `main.js`. Page-specific scripts handle Firebase authentication,
registration, password changes, request submission guards, and confirmation polling.

## Routes and forms

| Interface | Source routes |
| --- | --- |
| Public catalog | `/`, `/services`, `/services/<int:service_id>` |
| Authentication | `/login`, `/signup`, `/register/individual`, `/register/organization`, `/register/verify` |
| Request form and confirmation | `/get-connected`, `/get-connected/done/<reference>` |
| Member pages | `/member`, `/member/requests`, `/member/requests/<int:request_id>`, `/member/profile` |
| Organization pages | `/organization`, `/organization/requests`, `/organization/requests/<int:request_id>`, `/organization/services`, `/organization/profile` |
| Coordinator pages | `/coordinator`, `/coordinator/approvals`, `/coordinator/organizations`, `/coordinator/requests`, `/coordinator/requests/<int:request_id>`, `/coordinator/reports` |
| Legacy demo | `/demo/request` |

`team_url_for()` maps the templates' existing role-specific endpoint aliases to
registered blueprint endpoints. Preserve field names, IDs, data attributes, and
those aliases when maintaining templates or scripts.

Guest and member request forms post to `/api/guest/requests` and
`/api/member/requests`, respectively, then redirect to the owned confirmation.
Both carry CSRF and submission nonces. Member contact fields are server-owned;
guest ownership remains in the guest session and is not transferred on login.
Confirmation polling performs GET requests for up to two minutes without resubmission.

Organization actions use existing referral services for acceptance, rejection,
attendance, and completion. Coordinator assignment is limited to eligible unmatched
requests without an active referral and retains the original attendance deadline.
Forms do not authorize actions: backend role, ownership, state, and deadline checks
remain authoritative. See [authentication](authentication.md) for identity/session contracts.

## Template data

Templates receive mappings and lists; supply empty lists, zero counts, and `None`
for absent optional records. Use the `display_time` filter for UTC timestamps.

| Context | Important fields |
| --- | --- |
| Notifications | `message`, `time` |
| Requests | `request_id`, `reference`, `status`, `service_name`, `priority`, `priority_hours`, `response_deadline`, `history` |
| History items | `text`, `time` |
| Services | `service_id`, `service_name`, `category`, `area`, `delivery_methods` |
| Organization offerings | `organization_service_id`, `raw_status`, `max_referrals`, `current_active_referrals`, `availability_version` |
| Feedback | `is_helpful` boolean and optional `comment`; star ratings are not accepted |

The request form offers services with exactly one distinct active area; it does
not guess an area for services covering multiple areas. Organization request details
load member contact fields only after acceptance. Navigation role values are
`individual`, `organization`, and `coordinator`; SQL member roles use `member`.

Availability edits include expected state/version fields for stale-form checks.
Shared catalog and geography fields are read-only in organization offering forms.
Changing an offering does not change the underlying service catalog.

## Lists and terminology

Growing public, member, organization and coordinator lists use SQL filtering and
sorting before `LIMIT/OFFSET`. Shared controls default to 20 displayed rows, allow
10/20/50, preserve filters/sort in links and reset to page one when filters are
submitted. One extra row determines Next without an additional count query; no
unqueried total-page count is displayed. Dashboard summaries are limited to five
rows with independent full-dataset aggregates. Notification dropdowns remain
bounded recent-unread lists. Small catalog/category/area dropdowns remain reference
lookups. Reports aggregate complete data rather than a displayed page.

Coordinator request history and assignment choices are loaded on the individual
review page, not for every row on every list request. Service details select the
requested service directly, and the request-form catalog uses one grouped query
rather than one area query per service.

`display_label` maps internal High/Medium/Low to As soon as possible/Soon/Flexible.
The original 6/12/24-hour attendance targets remain visible and unchanged. A few-day
label would conflict with those SLAs. Referral buttons say Accept referral and
Decline referral; organization approval decisions still say Approve and Reject.
Unmatched requests display Referred to coordinator, including confirmation polling.
The request form carries one concise non-emergency-service notice.

## Academic check-in record

The October 28, 2026 ENSF 607 check-in notes recorded synthetic request 2 with
service/area 1/1, High priority, an initial `submitted` response, a later `matched`
response, and attendance deadline `2026-10-28T04:44:31Z`. This retains historical
academic provenance only: supporting API/database outputs are not included, and
these observations are not verification of the current checkout. Database diagrams
and the normalization report remain in `database/`.
