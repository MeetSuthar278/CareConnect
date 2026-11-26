# Authentication and security audit

The tested verification, role and ownership boundaries passed. The live Firebase password policy now matches the intended requirements.

| Boundary | Status / evidence |
| --- | --- |
| Firebase project | PASS: web/backend/Admin use `careconnect-bfb9e`. Read-only Admin calls found 3 mapped, verified, enabled accounts. |
| Sign-in configuration | PASS: Email/Password enabled, localhost authorized, email enumeration protection enabled; `live_environment.json`. |
| Token verification | PASS tested with controlled verifier responses plus source review: Admin SDK, project-bound signature validation, revocation check; cookies independently verified. Real browser sign-in was NOT TESTED in this pass. |
| Mandatory verification | PASS: preliminary browser credentials stay in memory; unverified identities cannot create SQL registration records or obtain role sessions. Fresh reload/token required after verification. |
| Identity mapping | PASS: SQL role and exact Firebase UID determine permissions. No email-only linking or client role promotion. Four coordinator records preserved; three remain unmapped. |
| Session / CSRF | PASS tests: fresh-auth window, CSRF for browser session/mutations, HttpOnly role cookies, Lax SameSite, Secure in hosted mode. Logout clears only this browser's cookies/state. |
| Object authorization | PASS: SQL ownership checks for member requests/feedback, organization referrals/offerings/profiles; anonymous and wrong-role routes denied. |
| Organization approval | PASS: pending/rejected applications cannot manage services/accept work; approval remains separate from email verification. Existing suspended work can finish under current rules. |
| SQL injection | PASS tested malicious search/sort inputs; values bound, sort clauses whitelisted, wildcard escaping; filters before pagination. |
| XSS | PASS tested search payload escaping and reviewed Jinja/tojson/textContent use; no claim of exhaustive penetration testing. |
| Error handling | PASS: fixed user-facing Firebase/policy/network messages; raw credential/provider messages not displayed. |
| Password reset | PASS synthetic browser: validated email, non-enumerating result, cooldown and friendly failure. Actual inbox delivery/reset is NOT TESTED. |
| Production defaults | PASS source/image smoke: debug off, non-root/read-only image, private database/broker hosting network; public TLS remains NOT TESTED. |

## Verified Firebase password policy

On November 26, the real Firebase Web SDK retrieved the policy for
`careconnect-bfb9e` and accepted `Password@` and `PASSWORD@`. All ten password
cases agreed with the shared form validator. The minimum is eight characters,
uppercase and special characters are required, lowercase and digits are optional,
Require mode is enabled, and forced upgrades on sign-in are off. The validator and
test-user utility now also accept hyphen and backtick, which the live SDK lists
as supported special characters.

[Live SDK evidence](firebase_password_policy.json) records only the policy GET
and its CORS preflight. Password examples were evaluated in memory. Signup,
sign-in, reset delivery and password changes were outside this check.

Reset uses Firebase's supported `sendPasswordResetEmail` flow, documented in
[Manage users](https://firebase.google.com/docs/auth/web/manage-users).
The same response for unknown/disabled accounts limits enumeration; the project
also enables [email enumeration protection](https://firebase.google.com/docs/auth/web/password-auth).
The local cooldown is usability protection; Firebase supplies service-side limits.

## Credential exposure review

`secret_scan.json` records a heuristic working-tree and 360-blob reachable-history
pattern scan. No tracked `.env` or private key material was detected. Findings
include historical development passwords in `.env.example`, `docker-compose.yml`
and `app/messaging/rabbitmq_connection.py`. These defaults must be treated as public.
Current source examples now use placeholders and broker runtime code requires the
private environment password. Existing `.env` and containers remain unchanged.

Existing Docker service ports are published on all host interfaces. The local
Compose source now binds future infrastructure to 127.0.0.1; this does not alter
the already-running containers. Review host firewall access and apply the binding
change only during an approved container recreation, preserving persistent volumes.

MANUAL ACTION REQUIRED: rotate any reused development credentials in a coordinated
maintenance window, updating the existing MySQL/RabbitMQ users and private configs
together, with backups and service checks. Editing examples does not rotate running
services. No automatic credential rotation or Git history rewrite was performed.

Historical Firebase web API identifiers appear in `app/frontend.py` and
`tools/create_firebase_test_user.py`; these are client project identifiers rather
than Admin private keys. Review API restrictions/quotas and retire obsolete project
access appropriately. Values are deliberately omitted from all audit output.

`.gitignore` excludes private env variants, service accounts, backups, private keys
and `.local/` supervisor tokens/logs. `.dockerignore` excludes these from build
context, and Docker COPY uses explicit runtime paths. Pattern scanning is not a
proof of absence: review Git staging and secret-manager/Console settings separately.
No public deployment, password change, account verification bypass or role reduction
was used to obtain passing tests.
