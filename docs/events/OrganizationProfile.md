# Organization Profile

Password controls have since been connected through Firebase. See
[PasswordChange.md](PasswordChange.md); disabled-password statements below describe
the original contact-only phase. Organization identity/coverage restrictions still apply.

The existing Organization Profile navigation and template now use GET/POST
`/organization/profile`. The existing verified-email Firebase representative cookie,
active SQL role and current organization membership are required. Layout, labels
and sections are preserved. Organization name, organization contact email and
configured service areas are read-only and omitted from the editable payload.
All password controls/button remain visible but disabled; no password API is called.

The editable fields are contact_name (the signed-in representative's name), phone,
address and city. Phone is the organization's shared contact phone and is also
synchronized to the editing representative's phone in the same transaction. Other
representatives' names, phones and primary-contact flags remain unchanged. The email
displayed is organizations.contact_email, which may differ from a representative's
personal login email. Neither that contact email nor Firebase/users.email is edited.

Service areas are derived from distinct configured organization_services/area rows,
including paused offerings, or '-' when none are configured. This is a configuration
display, not a promise of current availability. Changing the organization's city or
address does not create/reassign a coverage area or change matching eligibility.

POST requires the existing organization CSRF token, form_type=details and exactly
the editable fields. Unknown/repeated fields and forged IDs, role, status, service
area, email/name/password fields are rejected. Ownership comes from verified server
identity rather than a submitted organization/user ID. Invalid input retains editable
values with normal template escaping; protected fields remain server-sourced.

Validation follows existing organization registration bounds: contact name 1–100,
phone up to 25 characters with 7–15 digits and existing accepted punctuation, address
1–255 and city 1–100. Values are stripped and contact-name whitespace normalized.
The transaction locks/rechecks the representative's active SQL role and exact current
membership, then locks its organization, matching the existing offering lock order.
It updates organizations.contact_phone/address/city and only that representative's
full_name/phone, skipping unchanged rows. Failure rolls back both tables. Immediate
identical repeats perform no update; success uses POST/redirect/GET with a fresh read.

Pending and suspended organizations may maintain their contact details. Their saved
approval status and application decisions are not altered and My Services remains
blocked until approved. Identity, organization name, emails, role, primary membership,
offerings/support/capacity, existing requests/referrals/history and deadlines stay
unchanged. No outbox event or new notification is needed. The page reads only the
current representative's unread notifications and does not mark them read.

## Limits

The organization phone/address/city are shared organization fields. Other authorized
views reading these rows will show updated contact data, including existing referral
contact views; this does not rewrite request rows. Contact snapshots, change audit,
email/password editing, organization renaming and coverage editing are outside scope.
Concurrent valid edits serialize on locks, with last-save-wins rather than a stale
form version check. MySQL deadlocks may require retry; SQLite does not prove lock
scheduling. No schema, migration, seed or live record was changed during implementation.
