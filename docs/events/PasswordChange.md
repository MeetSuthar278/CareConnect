# Member and representative password changes

Both existing Profile forms now enable Current password, New password and Confirm
new password. The action is labeled Change password. Layout/styles and the separate
contact-detail forms are preserved; email/organization identity remain read-only.

`/member/password-context` and `/organization/password-context` are read-only,
cookie-protected, no-store endpoints returning only the signed-in SQL user's linked
Firebase UID and login email. An organization's shared contact email is not used for
its representative's login. Current active SQL role is rechecked; missing identities
fail closed. There is no client-supplied account/organization ID.

The shared password-change.js module initializes the existing Firebase web config
using memory-only persistence. It validates confirmation/minimum length and a changed
password, reads the current identity, signs in with its fixed login email and the
entered current password, and requires the returned Firebase UID to match. Only then
does it call Firebase updatePassword. Fresh password authentication satisfies
[Firebase's recent-sign-in requirement](https://firebase.google.com/docs/auth/web/manage-users).
No Admin password reset bypass is provided.

The password inputs intentionally have IDs but no HTML name attributes. JS reads
their values directly; even a native submission without JavaScript cannot serialize
password values into a Flask form POST. The existing contact-profile POST handlers
continue rejecting password-form operations or extra credential fields. Passwords
are sent only through the Firebase SDK, never written to MySQL, browser storage,
application logs, tokens or custom Flask payloads. Fields are cleared and the SDK
is signed out after each attempted operation. Duplicate clicks are blocked.

After success, POST `/api/auth/logout-browser` uses the existing signed-session CSRF
token in a header to clear browser state and all role cookies, then the UI redirects
to Login. This endpoint grants no account permission, performs no database/Firebase
operation and accepts no account/password payload. It deliberately does not require
the old Firebase cookie to remain valid after the password update. Invalid CSRF
fails; the existing bearer-only business APIs retain their authorization contract.

The browser is asked to sign in again with the new password. If browser-cookie cleanup
fails after Firebase succeeds, the UI still reports success and redirects to Login;
it does not repeat the password update with an old password. Existing Admin cookie
verification continues check_revoked=true, using Firebase's session behavior. See
[Firebase session management](https://firebase.google.com/docs/auth/admin/manage-sessions)
and [session cookies](https://firebase.google.com/docs/auth/admin/manage-cookies).

## Limits

This changes the signed-in member or representative's own Firebase password only.
There is no forgot-password email flow, email editing or coordinator Profile in this
phase. Firebase password policies still apply. Current Firebase/email/password provider,
network access and matching project/SQL identity are required. A lost network reply
can make the result uncertain; do not assume the old password remains valid or
automatically repeat a credential update. Cross-device revocation timing is Firebase's
responsibility and was not live-tested here.

No schema, SQL password hash, role, account link, contact profile, organization status,
request/referral, capacity or outbox change is made. Automated tests mock Firebase
password operations; no live password change or email send was performed.
