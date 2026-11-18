# Backend Firebase authentication foundation

Current policy (approved October 30, 2026): member accounts do not require email
verification. Representatives and coordinators still require email_verified=true.
The backend resolves the SQL-owned role before enforcing that rule; custom claims,
form roles and email collisions cannot grant privileged access. See
[the policy test guide](testing/EmailVerificationPolicy_TEST_GUIDE.md).

Implemented locally after backend-only approval. Frontend integration and database migration
execution are separate approval gates. No frontend template, stylesheet, database definition,
existing account or schema was changed in this phase.

## Contract

GET /api/auth/me requires Authorization: Bearer <Firebase ID token>.
Success returns user_id, email, SQL role and organization_id (null for nonrepresentatives).
Missing/invalid/revoked/expired tokens return 401; unverified privileged email, inactive user or invalid
representative linkage returns 403. Existing-email account linking conflicts return 409.
Missing credentials, SDK, migration or database availability produces 503 without exposing details.

Firebase Admin verifies the configured project and revoked/disabled accounts. Roles and organization
ownership come from MySQL, not from client fields or Firebase custom role claims. A new authenticated
identity can create only a member. Existing accounts are never linked by email automatically.
Administrator-controlled representative/coordinator UID linking is a later separately approved task.

This adapts Dhairya's implementation while preserving the working application factory and ORM models.
Authentication uses an independent SQLAlchemy Session/transaction. It deliberately reads the Firebase
column through authentication-only SQL so adding the endpoint does not make existing User ORM queries
fail before the team-approved migration is applied. The existing model metadata remains partial;
SQL migrations remain authoritative. No fallback to demo identity occurs on the new auth endpoint.

## Dependencies and prerequisites

requirements.txt adds firebase-admin>=7.0,<8.0 without replacing existing pinned packages.
FIREBASE_PROJECT_ID uses the reviewed default careconnect-7132c and can be overridden in the environment.
Do not commit service-account keys or paste them into chat. Configure Application Default Credentials
locally using the team's approved credentials arrangement. Revocation checks require backend access to
Firebase Auth. The project must match the client configuration.

The pending teammate_review/dhairya/001_firebase_auth.sql adds nullable unique firebase_uid and allows
password_hash=NULL. It has NOT been applied by this phase and is not copied into migration history.
It must receive explicit execution approval and team confirmation first. Do not run seed or baseline SQL.

## Integration boundaries

firebase_required supplies g.current_user as a frozen Identity. roles_required authenticates then
checks a SQL-owned role. Business endpoints must additionally enforce record ownership and valid state.
No rejection API, backup consumer or other event was implemented in this phase.

Existing demo request endpoints remain unchanged and are NOT yet secured by Firebase. They must not
be presented as production-private APIs. Their authentication integration belongs to the next approved
phase. No auth cookies or session-login endpoints were introduced: this foundation uses explicit bearer
headers only, not automatic browser credentials. Cookie-based login would need CSRF/session design.

GET /api/auth/me provisions a first-time member, matching Dhairya's account behavior; it is not a purely
read-only account probe. Repeated login retains the same member. Profile creation and registration UX
remain separate work. No member profile is automatically created here.

The existing frontend/templates/auth/login.html is preserved. Dhairya's auth.js is not activated because
its expected DOM elements differ. Login UI wiring, session navigation and visible verification/error
states require the next precise design approval. The earlier demo UI remains active.

## Evidence and limitations

Authentication tests use a disposable SQLite database with the expected future columns and mocked
Firebase verification. They verify business authorization/SQL behavior, not live Google credentials,
signature/certificate verification, MySQL migration compatibility or complete login UI behavior.
A live Firebase login has not been performed. No SDK installation or Firebase network request was
needed for the mocked tests. See testing/AUTHENTICATION_TEST_GUIDE.md.

Official references:
- https://firebase.google.com/docs/auth/admin/verify-id-tokens
- https://firebase.google.com/docs/auth/admin/manage-sessions


## Latest-team login integration (October 29, 2026)

This update supersedes the earlier statement that no login route is active.
GET /login now renders frontend/templates/auth/login.html using the latest team's
base, navbar, messages and Bootstrap/CSS. The older app/templates tree is not used
for that route. /team-static/ serves the team assets without shadowing existing /static/.
The active request UI at / and /get-connected remains unchanged for this phase.

The login template gained only a form ID and nonvisual script/config hooks. The existing
messages component gained an empty message wrapper; errors/success reuse its alert styling.
No CSS, labels, headings, input fields, navigation layout or visible technical explanations changed.
The added login.js signs in with the reviewed Firebase web config, requires verified email,
obtains a fresh ID token and calls /api/auth/me. Failed backend verification signs out the
client. Duplicate clicks cannot run simultaneous submissions. Password is cleared after attempts.
The web API key is public client configuration, not an Admin private key.

Persistence is memory-only. There is no new server session or cookie-based authorization,
no new dashboard redirect, no registration/reset/verification-email action and no account linking.
A successful API response is shown through the existing success-message style. Signing in does
not secure the earlier demo request endpoints; that remains a separately approved integration.
Services and signup links preserve the team's intended destinations but those pages are not yet
routed. Continue as Guest uses the existing request route. Only /login uses the new template tree
at this point. No mock dashboard or stub private-data endpoint was introduced.

Firebase Admin 7.7.0 was installed in the earlier environment setup. The approved users migration
was applied and verified separately, preserving four existing users. No migration or database
transaction ran during this login-UI implementation. Credentials reportedly exist in the user's
Flask terminal; this implementation process does not inherit another terminal's environment.
No live Firebase credentials/password/token were obtained or tested here.

Observed full suite: 60 passed, 18 existing SQLite warnings in 34.12s. Seven new login tests use
mocked browser Firebase SDK responses and mocked identity API responses; they do not prove live
Firebase authentication. Screenshots in testing/login were visually inspected on desktop/mobile.
See testing/FIREBASE_LOGIN_TEST_GUIDE.md before proceeding to another phase.
