# Individual member registration integration

Policy update approved October 30, 2026: members no longer require email
verification. The current form creates/signs in the Firebase member and saves its
profile immediately without sending a verification email. The two-stage flow below
records the original implementation and is superseded by
[the current policy guide](../testing/EmailVerificationPolicy_TEST_GUIDE.md).
Representatives and coordinators retain their verification requirements.

## Scope and existing design

The existing login Create an account link now opens /signup. The team's individual
choice opens /register/individual with the existing form, fields, labels, button,
layout and CSS. Only a form ID and configuration/module script tags were added
to the template. Existing main.js inline validation and page-messages alerts are
reused. No new visible section was added. Organization registration is a separate
pending workflow; its existing choice link does not create an organization.

## Registration flow

1. The existing individual form validates name, email, phone, address, city and
   matching passwords. JS prevents normal password POST to Flask.
2. Use Firebase's existing modular SDK version and public project configuration.
   Create the email/password account with memory-only persistence.
3. Send Firebase's verification email. No SQL profile is saved and no backend access
   is granted before verification. The alert asks the user to verify, then re-enter
   their password and submit the same form again. Keep the form tab open; profile
   inputs stay in the tab, while password fields are cleared after each attempt.
4. On repeat, Firebase reports the email already exists. Recover only by signing
   in with the actual supplied password. No account linking by email is performed.
5. Once the fresh Firebase login says emailVerified, get a fresh ID token and POST
   only the profile fields to /api/auth/register/profile. Passwords never go to Flask.
6. The backend verifies the token/email and SQL member role using existing auth.
   First verified identity resolution can provision only a member user. It cannot
   grant representative/coordinator roles or link an existing guest SQL identity.
7. Save the member profile transactionally and show registration complete. Sign out
   the memory-only Firebase user; the existing Log in link is the next action.

Firebase account creation, verification-email sending, identity provisioning and
profile persistence are separate operations. A failed email/profile attempt does
not delete the account. Retry with the same email/password after resolving the error.
An already verified account can finish profile registration without sending another email.

## Profile API and data integrity

POST /api/auth/register/profile requires a verified bearer-authenticated SQL member.
JSON fields: full_name, phone, address and city; no password or role input is used.
Split full name into first token and remaining last name; a single name has empty
last_name. First/last names are at most 50 characters each, phone at most 25 with
7–15 ASCII digits and permitted punctuation, address at most 255 and city at most
100. All existing required form fields are retained and validated server-side.

Lock the active SQL member row and recheck member role, then inspect its existing
profile. Insert only if absent. An identical retry returns already_processed=true;
different saved details return 409 and preserve the existing profile. No existing
account, role, credentials, profile or guest ownership is overwritten.
The existing UNIQUE(user_id) profile constraint is the database backstop.

Success is 200 with status registered and already_processed false/true. Missing
auth is 401, unverified/wrong role/inactive account 403, invalid fields 400, existing
different profile or auth identity collision 409, service/database failure 503.
Auth identity resolution retains its existing separate transaction; if profile
creation fails, the verified member user may exist and safely retry profile saving.

## Privacy and failure handling

Browser passwords and tokens remain in memory and are not written to localStorage,
sessionStorage or cookies by this code. Clear password fields after SDK/API work;
sign out after each attempt. Profile JSON contains no email, password, role or UID.
Use textContent for alerts, a 12-second backend fetch timeout, and no raw SDK error
messages/tokens. Repeated clicks are suppressed. Missing JavaScript leaves the
form POST unsupported (405), rather than accepting credentials server-side.
No live account creation, verification email, profile write or role change was
performed during implementation. A real email controlled by the user is required
for the subsequent live verification test; all assistance/profile details may be synthetic.

## Files and architecture

Changed app/frontend.py, app/__init__.py and
frontend/templates/auth/register_individual.html.
Added app/registration.py, frontend/static/js/register.js,
tests/test_registration.py, tests/test_registration_ui.py,
docs/events/MemberRegistration.md and docs/testing/MemberRegistration_TEST_GUIDE.md.
No schema, migration, seed, environment, CSS, login script or messaging changes.
Uses existing users/member_profiles/roles tables. No RabbitMQ event, producer,
consumer, outbox row or notification is needed for this supporting registration step.

## Verification and limits

Tests exercise navigation from login, existing desktop/mobile markup, password
mismatch validation, verification gating, duplicate clicks, hidden password cleanup,
same-account recovery, mail failure/retry, verified profile failure/retry, wrong
password, verified-member authorization, profile validation and no-overwrite retries.
Firebase is mocked in Edge browser tests; SQL is disposable. Actual results are
recorded in the guide. Live mail delivery, Firebase provider/domain configuration,
Admin credentials and concurrent MySQL profile writes still need live verification.

No dashboard redirect or persistent login session was added. Organization signup,
guest-to-Firebase linking and authenticated member request-form integration remain
separate scopes; creating a member does not transfer ownership of guest CC-11.

Implementation follows the official Firebase [password signup documentation](https://firebase.google.com/docs/auth/web/password-auth)
and [email verification documentation](https://firebase.google.com/docs/auth/web/manage-users).
