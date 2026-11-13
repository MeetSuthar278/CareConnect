# Member Profile

Password controls have since been connected through Firebase. See
[PasswordChange.md](PasswordChange.md); disabled-password statements below describe
the original contact-only phase. Contact/email editing restrictions still apply.

GET/POST `/member/profile` now uses the existing team My Profile template and the
member's verified Firebase session cookie. The existing Profile navigation link is
connected. Layout, section headings and button labels are preserved. Email remains
visible/read-only and is not included in the editable form payload. Existing password
inputs/button remain visible but disabled; there is no password-change operation.

The personal-details form sends CSRF, form_type=details, full_name, phone, city and
address. The route rejects unknown fields, repeated scalar fields, another form type,
user/role/UID/email/password fields and invalid CSRF. The owner ID is always taken
from the existing verified-cookie/SQL-role middleware, never from the submitted form.
Members still do not require verified email; this phase does not alter that policy.

The profile service validates the same field bounds used during registration:
full name up to 101 characters, individual first/last names up to 50, phone up to 25
characters with 7–15 digits and existing accepted punctuation, city up to 100 and
address up to 255. Required values are stripped, full-name whitespace is normalized,
and a single name is supported with an empty last_name. Invalid submissions preserve
editable input through the existing escaped template while showing the saved email.

One database transaction locks/rechecks the active member SQL role, locks the existing
owned profile and updates only first_name, last_name, phone, city and address. Missing
profiles are not silently recreated. Identical saved values return without an update.
SQL errors roll back and produce a fixed 503 message without SQL/token/password data.
Success redirects to GET (303), which reloads the current profile and greeting.
The page retains no-store behavior and displays only that member's unread alerts;
viewing it does not mark notifications read.

No users/email/Firebase identity, role, password hash, request/referral/history,
capacity, feedback or outbox rows are modified. No event is needed for this synchronous
profile update. Shared catalog data, database schema, baseline/seed and live records
were not changed during implementation.

## Limits

Existing request/contact views read the current member profile. A changed phone or
address can therefore appear when viewing older requests, even though no request
row or original priority/deadline is rewritten. This phase does not introduce contact
snapshots. Concurrent valid edits serialize on the profile lock; the last save wins,
with no stale-form version check. Email/password change and organization Profile
remain separate scopes. SQLite tests prove logical rollback/ownership, not MySQL
lock scheduling. No live profile save was executed by implementation tools.
