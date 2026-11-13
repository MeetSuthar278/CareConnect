# Public service browsing

The existing team Browse Services and service-detail templates are now connected:

- GET `/services`: keyword search and category/delivery filters.
- GET `/services/<service_id>`: public details and existing request-form link.

No template, CSS or JavaScript design changes were made. Existing home navigation
still requires anonymous visitors to choose Continue as Guest before showing service
options. Signed-in member/representative presentation still comes from existing
verified cookie and SQL-role middleware. Browsing itself is public and read-only.

`public_services()` reuses `service_choices()` so browsing and the request form
agree on active service/category, approved organization, active offering and active
area. Services with zero or multiple distinct active areas are omitted, preserving
the request form's single-area rule instead of choosing an arbitrary area. Multiple
organizations offering the same shared service in that area produce one card, with
their public names joined in the existing Organization field. No provider is selected
by clicking a card: the request URL carries only service_id and matching still ranks
eligible organizations after submission.

Search is a literal, case-insensitive substring across service name, category,
description, public organization names and area. Category and delivery filters use
exact displayed values; they combine with search. Unknown filters produce no results,
not an unrestricted fallback. Database rows supply displayed content and Jinja keeps
escaping enabled. Inactive/hidden/ambiguous/missing detail IDs return 404. SQL failures
render a generic existing-page error with HTTP 503 rather than exposing SQL messages.

The detail adapter uses the saved shared description and delivery mode, the existing
fixed two-hour response window, and '-' for eligibility because no eligibility field
is stored in the current schema. Availability is a current capacity snapshot:
Capacity available if any displayed provider has free slots, otherwise Currently
at capacity. Full offerings remain visible, consistent with the request form; browsing
does not promise a reservation or match. Contact emails, phones, member details and
account IDs are not selected for the public response. No new contact-disclosure
workflow is implemented in this phase.

Both pages send Cache-Control: no-store so availability and role-specific navigation
are not treated as durable public caches. GETs create no assistance request, referral,
notification, outbox record or capacity change. Existing catalog APIs are untouched.
The request form and its submission validators still recheck their own current data.

## Limits

- Multi-area request selection remains deferred; an otherwise active multi-area
  service is intentionally hidden in browsing and unavailable in this form.
- Capacity can change after viewing. Refresh to obtain a new snapshot; there is
  no browsing-side reservation or polling.
- The existing request-choice helper performs per-service area reads; this is
  proportionate to the university dataset, not a paginated large-directory design.
- No schema, baseline/seed, live data, authentication or matching logic was changed.
