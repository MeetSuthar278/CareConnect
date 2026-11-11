# Frontend integration guide

This guide describes the existing frontend contract, not a proposed production API.
Dhairya owns Flask routes, authentication and business logic; Raj owns MySQL data
and queries; Om owns RabbitMQ events; Meet coordinates frontend integration.
No production backend, database, API or queue has been added here.

## A. Project structure

| Path | Purpose |
| --- | --- |
| `frontend/templates/public/` | Homepage, searchable catalogue and service detail |
| `frontend/templates/auth/` | Login, account-type selection and registration forms |
| `frontend/templates/individual/` | Individual dashboard, guest/individual request form, confirmation, requests, feedback and profile |
| `frontend/templates/organization/` | Organization dashboard, referrals, services and profile |
| `frontend/templates/coordinator/` | Oversight dashboard, approvals, organization/request management and reports |
| `frontend/templates/components/` | Role navigation, notifications, flash messages and shared presentation macros; retained footer is intentionally unused |
| `frontend/templates/base.html` | Shared layout and local CSS/JS includes |
| `frontend/static/css/style.css` | Existing appearance and responsive rules |
| `frontend/static/js/main.js` | Validation, confirmation dialogs, delivery selectors, priority hints and request detail expansion; no API calls or demo record storage |
| `frontend/static/vendor/bootstrap/` | Existing locally bundled Bootstrap 5.3.3 and license; menu and notification dropdown behavior |
| `frontend/static/images/.gitkeep` | Existing image-directory placeholder, retained |
| `demo/sample_data.py` | Fictional fixture records, published demo credential and preview choice lists; relative referral dates generated on import |
| `demo/preview_app.py` | Independently runnable Flask preview, fixture imports and existing in-memory interactions; asset paths resolved from this file |
| `preview_app.py` | Compatibility launcher exporting the same Flask `app` |
| `tests/test_preview.py` | Python/Flask regression checks |
| `tests/browser_review.py` | Optional isolated Chrome checks and screenshots |
| `review-artifacts/`, `FRONTEND_REVIEW.md` | Preserved earlier review evidence; generated new screenshots are ignored |
| `requirements.txt`, `.gitignore`, `README.md` | Runtime dependency, local-file exclusions and run instructions |

Run `python -m demo.preview_app` from the repository root. The root command
`python preview_app.py` also works. Do not execute `demo/preview_app.py` directly:
it imports fixtures as a Python module. No package installation is needed.

## B. Page and route mapping

Template paths are relative to `frontend/templates`. Methods below omit Flask's
automatic HEAD/OPTIONS methods. Endpoint names and paths are unchanged. For an
action without its own page, the template column identifies the source interface.

| Page / action | Template file | Current demo endpoint and path | HTTP method | Backend responsibility |
| --- | --- | --- | --- | --- |
| Home / guest entry | `public/home.html` | `home` `/` (`?guest=1` shows service choices) | GET | Render role-aware entry |
| Browse | `public/browse_services.html` | `browse_services` `/services` | GET | Search/filter available services |
| Service details | `public/service_details.html` | `service_details` `/services/<int:service_id>` | GET | Load available service; unavailable ID currently redirects to browse |
| Login | `auth/login.html` | `login` `/login` | GET, POST | Authenticate and determine role, then redirect to dashboard |
| Logout | `components/navbar.html` | `logout` `/logout` | GET | Clear session and return home; production method/CSRF policy needs agreement |
| Signup choices | `auth/signup.html` | `signup` `/signup` | GET | Show individual/organization signup |
| Individual signup | `auth/register_individual.html` | `register_individual` `/signup/individual` | GET, POST | Validate and create individual account |
| Organization signup | `auth/register_organization.html` | `register_organization` `/signup/organization` | GET, POST | Create representative/application pending approval |
| Guest/individual request | `individual/request_form.html` | `request_form` `/get-connected` (`?service_id=N` preselects) | GET, POST | Validate service, contact and delivery; save request and issue reference |
| Request confirmation | `individual/request_confirmation.html` | `request_confirmation` `/get-connected/done/<reference>` | GET | Load newly submitted request; unknown reference currently redirects home |
| Individual dashboard | `individual/dashboard.html` | `ind_dashboard` `/individual/dashboard` | GET | Current individual's latest requests and counts |
| My requests | `individual/my_requests.html` | `my_requests` `/individual/requests` | GET | Current individual's filtered requests |
| Individual request | `individual/request_details.html` | `request_details` `/individual/requests/<int:request_id>` | GET | Ownership, history and organization contact visibility |
| Cancel | `individual/request_details.html` | `cancel_request` `/individual/requests/<int:request_id>/cancel` | POST | Validate cancellable state; cancel and record history |
| Feedback | `individual/feedback.html` | `feedback` `/individual/requests/<int:request_id>/feedback` | GET, POST | One rating for an owned completed request |
| Individual profile/password | `individual/profile.html` | `profile` `/individual/profile` | GET, POST | Load/update profile or change password |
| Organization dashboard | `organization/dashboard.html` | `org_dashboard` `/organization/dashboard` | GET | Organization identity, counts and incoming referrals |
| Organization referrals | `organization/requests.html` | `org_requests` `/organization/requests` | GET | Scoped referrals and status filter |
| Organization referral detail | `organization/request_details.html` | `org_request_details` `/organization/requests/<int:request_id>` | GET | Scoped referral/history and permitted contact details |
| Accept/reject | `organization/requests.html`, `organization/request_details.html` | `org_respond` `/organization/requests/<int:request_id>/respond` | POST | Validate referral response and deadline |
| Complete | `organization/request_details.html` | `org_update_status` `/organization/requests/<int:request_id>/status` | POST | Complete an accepted request |
| Organization services/add/edit | `organization/services.html` | `org_services` `/organization/services` | GET, POST | Load/add/update owned services |
| Pause/resume | `organization/services.html` | `org_toggle_service` `/organization/services/<int:service_id>/toggle` | POST | Toggle owned service availability |
| Organization profile/password | `organization/profile.html` | `org_profile` `/organization/profile` | GET, POST | Load/update organization or change representative password |
| Coordinator dashboard | `coordinator/dashboard.html` | `coord_dashboard` `/coordinator/dashboard` | GET | Counts, pending organizations, attention queue |
| Approvals | `coordinator/approvals.html` | `coord_approvals` `/coordinator/approvals` | GET | Pending organization applications |
| Organizations | `coordinator/organizations.html` | `coord_organizations` `/coordinator/organizations` | GET | Filtered organization records and service counts |
| Organization management | `coordinator/approvals.html`, `coordinator/organizations.html` | `coord_org_action` `/coordinator/organizations/<int:org_id>/action` | POST | Approve/reject/suspend/reactivate with valid transitions |
| Request oversight/details | `coordinator/requests.html` | `coord_requests` `/coordinator/requests` | GET | Filter requests; prepare attention and eligible organizations; inline details |
| Assign/reassign | `coordinator/requests.html` | `coord_reassign` `/coordinator/requests/<int:request_id>/reassign` | POST | Validate assignment/capacity; select service; record deadline/history |
| Reports | `coordinator/reports.html` | `coord_reports` `/coordinator/reports` | GET | Current counts, breakdowns and feedback aggregate |
| Assets | `base.html` | `static` `/static/<path:filename>` | GET | Serve existing static files |

There is no separate guest dashboard, referral-details page, coordinator request
status form or notification API. Coordinator request details expand inline; the
existing coordinator request action is assignment/reassignment.

## C. Template data requirements

Use plain dictionaries/lists with the existing names. Jinja supports dictionary
fields through dot notation. Do not pass passwords, signing keys or complete user
credential records. Lists should be `[]`, counts `0`, missing optional records
`None`. Date/time inputs for `display_time` are ISO strings, with UTC offsets for
recorded timestamps. A missing timestamp displays `Time not recorded`.

### Shared context and choices

Flask supplies `request`, `session`, `url_for` and `get_flashed_messages`.
Navigation uses `session['role']` (`individual`, `organization`, `coordinator`) and
the individual greeting uses `session['name']`. Absent role means guest.
`request.endpoint` controls active navigation; `request.args` controls guest entry
and filters; `request.form` repopulates non-password fields after validation.
Keep these Flask conventions or adapt the templates together.

| Variable/filter | Shape/example | Consumers and empty behavior |
| --- | --- | --- |
| `notifications` | `[{"message": "Request updated", "time": "Oct 25"}]` | Shared bell; missing/empty list says `No new notifications.` Times are display strings |
| `request_statuses` | `['Pending', 'Assigned', 'Accepted', 'Rejected', 'Completed', 'Cancelled', 'Expired']` | Individual/coordinator status filters; supply full choice list even with no records |
| `priority_hours` | `{'High': 6, 'Medium': 12, 'Low': 24}` in display order | Request and coordinator priority options; request JS reads option `data-hours` |
| `delivery_methods` | `['In person', 'Phone', 'Online']` | Browse filters and service form checkboxes; service-specific lists constrain request delivery |
| `org_active` | `True` / `False` | Organization response controls; false hides Accept/Reject |
| `display_time` filter | ISO string or `None` -> formatted UTC string | `components/macros.html`: priority deadline and history |

These are supplied by the preview's `add_notifications` context processor. Production
may pass them explicitly or register its own processor. No template calls demo
eligibility, attention or overdue functions: those display fields are prepared in
Python by `request_view`.

### Record shapes

These examples define the field contract; values are illustrative fictional data,
not required database column names. Map Raj's query results to these shapes.

```python
user = {"full_name": "Example Individual", "email": "person@example.com",
        "phone": "403-555-0100", "address": "1 Example Street", "city": "Calgary"}

org = {"org_id": 1, "org_name": "Example Organization", "contact_name": "Example Rep",
       "email": "org@example.com", "phone": "403-555-0110", "address": "2 Example Road",
       "city": "Calgary", "service_area": "Calgary NW", "status": "Active",
       "created_at": "2026-10-01", "service_count": 1}
# Organization display statuses: Active, Pending, Suspended, Rejected.

service = {"service_id": 1, "service_name": "Example service", "category": "Food Assistance",
           "org_name": "Example Organization", "area": "Calgary NW",
           "delivery_method": "In person, Phone",  # display string
           "delivery_methods": ["In person", "Phone"],  # supported choices
           "eligibility": "People in the area", "availability": "Weekdays",
           "description": "Example description", "status": "Active",
           "response_hours": 12, "max_referrals": 10}
# Service statuses: Active, Paused. categories is a list[str].

req = {"request_id": 1, "reference": "CC-1001", "service_id": 1,
       "service_name": "Example service", "category": "Food Assistance",
       "priority": "High", "priority_hours": 6, "status": "Assigned",
       "created_at": "2026-10-29", "submitted_at": "2026-10-29T09:00:00+00:00",
       "response_deadline": "2026-10-29T15:00:00+00:00",
       "org_id": 1, "org_name": "Example Organization", "backup_org_name": None,
       "delivery_method": "In person", "details": "Example support need",
       "contact_name": "Example Individual", "contact_email": "person@example.com",
       "contact_phone": "403-555-0100", "contact_address": "1 Example Street",
       "contact_city": "Calgary", "is_guest": False,
       "history": [{"text": "Request submitted", "time": "2026-10-29T09:00:00+00:00"}],
       "assigned_service_id": None, "assigned_service_name": None,
       "feedback": None}
# Optional feedback: {"rating": 5, "comment": "Helpful"}.
# Optional assigned_service_* preserve the original service when reassigned.
# An unassigned request has org_id/org_name None. Missing notes use existing fallbacks.

# Additional display fields for organization lists/details and coordinator views:
req.update(is_overdue=False, attention_reasons=[])
# Coordinator request rows also supply eligible_orgs=[org, ...] or [].
# attention_reasons contains zero or more of:
# Unmatched, Rejected referral, Expired referral, Overdue, Manual review.
```

The preview retains legacy `overdue`, `backup_org_name` and optional
`manual_attention` fixture fields. Templates use computed `is_overdue` and
`attention_reasons`, not the legacy `overdue` flag. No standalone referral table is
assumed by the frontend; current referral displays are request data with assignment,
deadline and history fields. This is not a proposed database model.

### Every page's context and empty state

Shapes below refer to the records above. All pages also inherit the shared context.
Static copy, labels and enum options are presentation, not sample records.

| Template | Required page variables and example shape | Empty/missing behavior |
| --- | --- | --- |
| `public/home.html` | No record variables; Flask session and `guest` query | Guest entry or role-specific buttons |
| `public/browse_services.html` | `services=[service]`, `categories=['Food Assistance']`, `search=''`, `selected_category=''`, `selected_delivery=''` | `No services found. Try a different search.` |
| `public/service_details.html` | `service=service` | Preview redirects unavailable IDs to browse; do not render with missing service |
| `auth/login.html` | Optional `email=''` after failed login | Blank initial email/password; invalid credentials flash error |
| `auth/signup.html` | No record variables | Always shows signup choices |
| `auth/register_individual.html` | No record variables; non-password values read from `request.form` | Blank first visit, validation messages after POST |
| `auth/register_organization.html` | Same form convention | Blank first visit; approval notice remains |
| `individual/request_form.html` | `services=[service]`, `selected_service_id=1` or `None`, `user=user` for individual or `None` for guest | Empty catalogue message and disabled submit; guest contact fields blank on fresh GET |
| `individual/request_confirmation.html` | `req=req` | Unknown reference redirects home; guest sees reference and signup/home choices |
| `individual/dashboard.html` | `requests=[req]` (latest three), `active_count=0`, `completed_count=0` | First-request prompt and zero counts |
| `individual/my_requests.html` | `requests=[req]`, `selected_status=''` | `No requests found.` |
| `individual/request_details.html` | `req=req`, `assigned_org=org` or `None` | Invalid/guest request redirects to My Requests; contact unavailable until Accepted/Completed; missing feedback offers link only if Completed |
| `individual/feedback.html` | `req=req` | Non-completed/already-rated requests redirect to details; unknown/guest request redirects to My Requests |
| `individual/profile.html` | `user=user` | Requires current profile; no blank-profile page defined |
| `organization/dashboard.html` | `org=org`, `counts={'incoming': 0, 'active': 0, 'completed': 0, 'services': 0}`, `requests=[req]` (incoming) | No-new-requests message; Pending/Suspended notices; zero counts |
| `organization/requests.html` | `requests=[req]` with `is_overdue`, `selected_status=''` | `No requests found.`; response controls depend on state, deadline, `org_active` |
| `organization/request_details.html` | `req=req` with `is_overdue` | Invalid/unowned request redirects to referrals; contact hidden until Accepted/Completed; no-action explanation when unavailable |
| `organization/services.html` | `services=[service]`, `categories=['Food Assistance']` | No-services message plus usable add form; shared service macro reads `request.form` for failed add/edit |
| `organization/profile.html` | `org=org` | Requires current organization; status always shown |
| `coordinator/dashboard.html` | `counts={'pending_orgs': 0, 'unmatched': 0, 'overdue': 0, 'total': 0}`, `pending_orgs=[org]`, `attention_requests=[req]` with `attention_reasons` | `No organizations are waiting.` / `Nothing needs attention.` |
| `coordinator/approvals.html` | `orgs=[org]` (Pending only) | `No organizations are waiting for approval.` |
| `coordinator/organizations.html` | `orgs=[org]` with `service_count`, `selected_status=''` | `No organizations found.` |
| `coordinator/requests.html` | `requests=[req]` with `attention_reasons` and `eligible_orgs`, `orgs=[org]`, `selected_status=''`, `selected_priority=''`, `selected_org=''` (string ID), `selected_attention=''` | `No requests found.`; empty eligible choices explain coverage/status/capacity review |
| `coordinator/reports.html` | `totals={'requests': 0, 'completed': 0, 'organizations': 0, 'feedback_count': 0, 'average_rating': None}`, `by_status=[{'name': 'Pending', 'count': 1}]`, `by_category=[{'name': 'Food Assistance', 'count': 1, 'completed': 0}]` | Both empty tables say `No requests to report.`; missing average shows em dash |

The preview still passes `timeline=req['history']` to individual detail and
`active_orgs=[org]` to coordinator requests for compatibility with the earlier
preview; current templates do not read those variables. History macros read
`req.history`. Every history item needs `text` and `time`; unknown historical times
may be `None`. `components/macros.html` also exposes `status_label(text)`,
`priority_deadline(req)`, `status_history(req)` and
`service_fields(s, categories, methods, form_values)`; the last receives a dictionary
service or `{}` for add, and Flask's `request.form` MultiDict for retained values.

`base.html` and `components/navbar.html`, `notification_panel.html`, `messages.html`
use the shared Flask context. Messages use `flash(message, 'success'|'error'|'info')`.
`components/footer.html` is intentionally unused and has no data requirements.

## D. Form integration requirements

All forms use ordinary URL-encoded Flask submissions. There are no fetch/API
submissions. Every visible control has a meaningful name and label; buttons have
explicit types. Repeated `delivery_methods` checkbox values require
`request.form.getlist('delivery_methods')`. IDs in paths are not extra form fields.

Each mutation must be validated again by Dhairya's handler, including ownership,
role and allowed state. Browser validation is for usability. Current signup and
password minimum length is six; final password policy is unconfirmed. Password
inputs are never populated from submitted values.

| Form location | Method / demo action | Fields / required fields | Demo result; expected backend operation and success/error behavior |
| --- | --- | --- | --- |
| `auth/login.html` | POST `login` | Required `email`, `password` | Published fixture login redirects by role; invalid values re-render with error and email retained. Backend must authenticate and create session |
| `auth/register_individual.html` | POST `register_individual` | All required: `full_name`, `email`, `phone`, `address`, `city`, `password`, `confirm_password` | Validates then says account creation unavailable (info); invalid fields flash error. Backend creates account only after validation, with real success/error outcome |
| `auth/register_organization.html` | POST `register_organization` | All required: `org_name`, `address`, `city`, `service_area`, `contact_name`, `email`, `phone`, `password`, `confirm_password` | Same honest unavailable message; backend saves representative/application and pending approval |
| `individual/request_form.html`, individual | POST `request_form` | Required `service_id`, `priority`, `delivery_method`, `details`; saved profile supplies contact fields, no editable contact inputs | Appends in-memory request then redirects to confirmation; invalid fields re-render with HTTP 400 and retained values. Backend uses authenticated contact data and persists before success |
| Same form, guest | POST `request_form` | Above plus all required `contact_name`, `contact_email`, `contact_phone`, `contact_address`, `contact_city` | Same validation/save behavior; guest flag true. Backend handles guest submission without a registered guest role |
| `individual/request_details.html` cancel | POST `cancel_request` | No body fields; `request_id` in URL | Pending/Assigned/Rejected/Expired can cancel; changed records get history/notification and success flash; invalid action currently redirects silently. Backend must validate and return an honest error for failure |
| `individual/feedback.html` | POST `feedback` | Required `rating` integer 1..5; optional `comment` | Stores feedback once on Completed request and redirects to detail with success; bad rating HTTP 400, other invalid states redirect. Backend persists one owned feedback record |
| `individual/profile.html` details | POST `profile` | Hidden `form_type=details`; all required `full_name`, `email`, `phone`, `city`, `address` | Updates fixture/session name then redirects and flashes success; errors flash and redirect. Backend updates authenticated profile; login-email behavior needs agreement |
| `individual/profile.html` password | POST `profile` | Hidden `form_type=password`; all required `old_password`, `password`, `confirm_password` | Checks required values/length/match, then info: password changes unavailable; never claims changed. Backend verifies current password and changes stored credentials |
| `organization/profile.html` details | POST `org_profile` | Hidden `form_type=details`; all required `org_name`, `contact_name`, `phone`, `email`, `address`, `city`, `service_area` | Updates fixture and related display names, redirect/flash; errors flash and redirect. Backend persists owned organization data |
| `organization/profile.html` password | POST `org_profile` | Same password fields and hidden discriminator as individual | Same unavailable demo behavior; backend changes representative credentials |
| `organization/requests.html` and `organization/request_details.html` response | POST `org_respond` | Submit-button field `action=accept` or `reject`; `request_id` in URL | Active organization can respond to Assigned referral; accept before deadline succeeds, late accept records Expired/error; reject adds coordinator attention. Backend rechecks ownership/deadline, persists response and events |
| `organization/request_details.html` complete | POST `org_update_status` | Submit-button field `status=Completed`; `request_id` in URL | Accepted -> Completed, history and success flash; otherwise redirect without false success. Backend validates transition and persists |
| `organization/services.html` add | POST `org_services` | All required: `service_name`, `category`, `area`, `eligibility`, `availability`, `description`, `status`, `response_hours`, `max_referrals`; at least one `delivery_methods` | Appends fixture, redirects/success. Invalid input re-renders HTTP 400 retaining values. Backend creates owned service. `response_hours` 6/12/24; `max_referrals` integer 1..1000; `status` Active/Paused |
| Same page edit settings | POST `org_services` | Same fields plus hidden `service_id` | Updates matching owned fixture; invalid ID/fields HTTP 400; backend updates owned service. Hidden ID distinguishes edit from add |
| Same page pause/resume | POST `org_toggle_service` | No body fields; `service_id` in URL | Active <-> Paused, success only when found; redirect otherwise. Backend changes owned service availability |
| `coordinator/approvals.html` approve/reject | POST `coord_org_action` | Submit-button `action=approve` or `reject`; hidden `return_to=approvals`; `org_id` in URL | Pending -> Active/Rejected; success flash only when changed, then approvals redirect. Backend validates and persists decision |
| `coordinator/organizations.html` suspend/reactivate | POST `coord_org_action` | Submit-button `action=suspend` or `reactivate`; `org_id` in URL | Active -> Suspended, Suspended -> Active; redirects to organizations. Invalid transitions do not claim success. Backend enforces valid decision |
| `coordinator/requests.html` assign/reassign | POST `coord_reassign` | Required `org_id`; `request_id` in URL | Validates open state and eligible organization, chooses first matching service, sets deadline/history/notification and redirects to request anchor. Invalid choice flashes error; same live assignment gives info. Backend owns real matching, capacity and transaction |

The organization listing retains an empty form wrapper for Pending/Rejected records;
only Active/Suspended rows submit actions. Pending rows link to approvals.

| Search/filter form | Method / endpoint | Optional query fields | Behavior |
| --- | --- | --- | --- |
| `public/browse_services.html` | GET `browse_services` | `search`, `category`, `delivery` | Case-insensitive text match; selected choices retained; clear link resets |
| `individual/my_requests.html` | GET `my_requests` | `status` | Current individual's requests only |
| `organization/requests.html` | GET `org_requests` | `status` | Current organization's referrals only |
| `coordinator/organizations.html` | GET `coord_organizations` | `status` | Filter organizations |
| `coordinator/requests.html` | GET `coord_requests` | `status`, `priority`, `org_id`, `attention` | Combined filters; clear resets all; `attention` values match display reasons |

Confirmation dialogs cover cancellation, rejection, completion, suspension and
assignment; assignment names current and selected organizations. Cancelling the
dialog prevents submission. UI messages follow the actual in-memory change.
Several invalid demo actions only redirect; production errors and field-error
presentation still need agreement. Profile validation currently redirects and
reloads saved values rather than retaining invalid edits. No real CSRF/authentication
scheme has been added; integrate that scheme with every form together.

## E. User roles

| Role | Existing workflow |
| --- | --- |
| Individual | Browse, submit requests using saved contacts, track own requests, cancel eligible requests, rate completed requests, edit profile/password form |
| Organization representative (`organization`) | Manage own organization's services/profile, receive/respond to referrals, complete accepted requests; approval status affects availability |
| Coordinator | Review organizations, manage approval/suspension, oversee requests/attention, assign/reassign referrals, view reports |

Guest access belongs to the individual request workflow. It means no registered
role/session identity. Guests enter contact details each time and receive a
reference, with no separate dashboard, account migration or claim-request flow.
The preview role decorator and signed cookie are demonstrations, not real user
authorization. One individual identity and one organization identity are shared by
all corresponding demo logins; production must scope data by authenticated IDs.

## F. Backend integration notes

1. Configure Dhairya's Flask app with absolute `frontend/templates` and
   `frontend/static` paths (as shown in `demo/preview_app.py`) and keep `/static` or
   adapt `url_for('static', filename=...)` together. Keep the existing local vendor
   assets. Do not import/run the preview application inside the production app.
2. Register handlers for the current endpoint names, or map existing backend
   handlers to them with Flask's `endpoint=` argument. If using Blueprint names,
   update every affected `url_for`, navbar link call and active endpoint comparison
   together. Search with `rg -n 'url_for|nav_link|request.endpoint' frontend demo`.
   The route table above is the reference; it does not prescribe final backend names.
3. Render the current template paths with the records in section C. For example,
   `render_template('individual/my_requests.html', requests=owned_requests,
   selected_status=status)` plus shared context. Register `display_time` before
   rendering the imported macros. Build attention reasons, overdue flags and
   eligible organization lists in Python before rendering coordinator/organization
   views. Templates should not query a database or import demo rules.
4. Process the forms in section D using current names and `getlist` for delivery
   checkboxes. Verify state/role/ownership independently of hidden fields or UI
   controls. Populate Flask session role/name after real authentication. Preserve
   existing redirect destinations and inline validation where possible. Decide
   success/error behavior with the team before replacing the honest unavailable
   signup/password messages and button labels.
5. Replace fixture records with normalized query/application results, preserving
   frontend keys and list/null conventions. Raj need not use identical database
   columns. Keep `demo/sample_data.py` available for isolated testing, with no
   imports into production configuration and no production secrets in that file.
6. Keep existing layout, CSS classes, IDs and data attributes. JavaScript reads
   request service option `data-delivery` (JSON list), `data-area`, priority
   `data-hours`, delivery `data-selected`, `data-delivery-group` and assignment
   confirmation attributes. Bootstrap handles menu/dropdown toggles. Request
   anchors use `request-N` and adjacent inline details. No API URL needs replacing.
7. Rerun regression and browser checks after adaptation. Preview tests exercise
   in-memory simulation; production needs its own handler/auth/data checks.

Existing preview rules have been retained, not implemented as a new backend:
category, delivery, city substring and capacity determine eligibility; active
services and organizations determine public availability. Priority windows are
6/12/24 hours. Assignment uses the shorter of priority/service response windows.
Overdue is computed while rendering; a late accept marks Expired, but there is no
scheduler. Notifications are simple in-memory entries, not RabbitMQ or live push.
Guest confirmation reference lookup is a demo shortcut, not production access
control. Profile email edits update contacts, not published demo login identifiers.

## G. Known integration dependencies

Confirmed frontend requirements are the existing form fields, endpoint references,
role values, layouts, status labels, timestamps, contact visibility after acceptance,
empty states and interactions documented above. Demo implementation choices below
are assumptions that need team agreement, not final backend requirements.

| Owner(s) | Decision still needed |
| --- | --- |
| Dhairya + Meet | Final route/Blueprint names; session identity keys alongside role/name; signup/password labels when connected; error status/field feedback; CSRF integration and logout method |
| Dhairya + Raj | IDs/ownership/query adapters; user vs representative relationship; organization application persistence; profile email vs login identifier; feedback uniqueness and aggregate rounding |
| Dhairya + Raj + Meet | Valid status transitions including cancellation after acceptance; matching by actual geography/eligibility; capacity meaning; first service vs explicitly selected service; deadline/reset and reassignment rules |
| Dhairya + Om | Event names/payloads, event creation after successful writes, delivery/retry/idempotency, expiry scheduling, notification audience/storage/read state; frontend currently expects only message/time lists |
| Dhairya + Meet | Guest reference privacy/access, tracking/claiming requests if later desired, contact disclosure and authentication boundaries |
| All | Agree UTC storage/display and production date handling; enum/category source; repeatable integration fixtures without deploying demo credentials |

No MySQL schema, RabbitMQ event contract, API path, authentication implementation
or production secret policy is selected by this refactor.

## Validation

Run from the repository root:

```powershell
python -m unittest discover -s tests -v
python -m flask --app demo.preview_app routes
python tests/browser_review.py --artifacts-dir review-artifacts
```

The browser runner is optional: Chrome and `websocket-client` must be installed;
see README. Python checks cover template compilation, static assets, role pages,
navigation, form destinations/methods/names/button types, fixture imports, guest and
individual requests, assignment/response/completion/feedback, management edits,
validation and empty states. Browser checks exercise 75 page/viewport combinations
at 1280, 768 and 390 pixels, plus key JavaScript interactions and resource errors.

Executed for this integration preparation on 29 October 2026:

- All 16 unittest checks passed, including all 30 Jinja templates and existing workflows.
- Chrome passed all 75 page/viewport combinations and the interaction checks, with
  no JavaScript errors observed. The mobile coordinator and desktop services
  screenshots were inspected and saved under ignored `review-artifacts/integration/`.
- An additional comparison against Git HEAD found identical rendered HTML for 28
  page cases, allowing only the added nonvisual priority `data-hours` attribute.
- Both `python -m demo.preview_app` and `python preview_app.py` started and served
  the homepage over HTTP; the module preview also served CSS in the HTTP smoke check.
- Flask's route listing and `git diff --check` passed. Requirements were checked
  with pip's dry-run against the installed environment; a fresh virtualenv dependency
  installation was not performed.

Other browser engines, assistive technology and the future production backend still
require validation. No failing frontend checks remain from this run.
