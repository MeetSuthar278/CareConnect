# CareConnect submission readiness

CareConnect is ready for repository publication review. The final local regression
run passed 112 tests, with 12 opt-in cases covered by the earlier isolated
MySQL/RabbitMQ run. The earlier browser run passed 97 checks, and the hosting
image passed a local HTTP smoke test.

The project owner rehearsed and applied migration 003 to the live database.
All 21 table fingerprints and retained referral attributes matched. The redundant
column and index are gone, and startup completed with 9/9 managed processes.
The owner verified 21 tables, 17 users, seven organizations, 25 offerings,
40 requests, 29 referrals and 10 published outbox events.

Section J records current results. Sections A through I are historical. Human
participant testing, real email delivery and hosted deployment remain unverified.

## J Final integration, testing and submission review

This section separates the final local regression run, prior automated checks,
and live results from the owner?s terminal. The publication pass did not connect
to the live services or stop the running application.

### Scope, initial findings and fixes

The audit read the working tree now on branch `feature/final-submission`, existing source,
Flask's actual frontend loader, all worker entry points, SQL baselines/migrations,
earlier reports and current services before making changes. The existing environment
was reachable; earlier unavailable-service claims were not carried forward as current.

| Confirmed issue | Result |
| --- | --- |
| Earlier schema tests assumed users DDL before the user's Firebase migration | Tests now verify exactly the UID/nullable-password transformation and retain exact checks on all other original tables/academic queries. |
| Two equivalent Firebase migration files could inflate the count | Inventory merges only the reviewed equivalent ALTER statements and keeps both source locations; the duplicate contributes one family. |
| No password-reset action on login | Added compact Forgot your password action using the shared memory-only Firebase client, non-enumerating result, cooldown and friendly errors. Login complexity remains unchanged. |
| ORM User metadata disagreed with migrated SQL | Added nullable unique ASCII UID and nullable password_hash mapping; no create_all/migration executed. |
| Committed development password fallbacks | Current broker code requires the private environment value; Compose/examples use private-variable placeholders. Existing credentials unchanged; history remediation remains manual. |
| Future local infrastructure exposed on all interfaces | Compose source binds localhost; existing containers were not recreated or rebound. |
| Multiple terminals / duplicate-process risk | Added three PowerShell entry scripts and an owned Python supervisor with preflight, lock, health, logs and scoped shutdown. Tested in disposable environment. |
| No reproducible live workflow evidence | Added opt-in isolated MySQL/RabbitMQ test runner and 12 isolated integration tests plus browser/image/read-only audit tools. |
| Eight stale seed capacity values | Corrected only the synthetic seed source. Fresh MySQL test asserts aggregate consistency; the owner corrected the live caches. |
| Historical diagrams omitted workflow/Firebase delta | Added the current 21-relation/34-FK logical mapping; preserved original JPEG/PDF artifacts. |
| Reports risked confusing automation and participants | Added current evidence reports and explicit automation/participant columns; all human outcomes remain unperformed. |

The reviewed paths, staging list and excluded deletions are in [publication review](testing/PUBLICATION_REVIEW.md).
No file that existed at this pass's start was deleted. Earlier uncommitted work,
recovered backend files and teammate contributions were retained. No .env or
external service-account file was edited. Existing migration 002 was not reapplied.

### Current evidence

| Area | Status | Actual result |
| --- | --- | --- |
| Final automated regression | PASS | 112 passed. The 12 opt-in network cases were skipped by default and passed in the prior isolated suite. |
| Network integration | PASS | 12 passed on genuine disposable MySQL/RabbitMQ; fresh initialization, transactions, concurrency, roles, full workflow and supervisor lifecycle. |
| Developer browser | PASS | 97 checks, 15 frontend JS files parsed, 390/1280px role/public layouts; fake Firebase SDK, no live accounts. |
| Source / imports / templates | PASS | 75 Python files parsed, 3 PowerShell scripts parsed, 7 worker imports, 36 active templates, pip check and diff check. |
| Live MySQL and migration 003 | OWNER VERIFIED | Schema checks passed after the rehearsal and live migration. All 21 table fingerprints matched and all retained referral attributes were preserved. The legacy column and index were removed. |
| Existing identities | PASS | 17 users / 3 UIDs / 4 coordinators; only 1 coordinator mapped. Identity snapshot hash unchanged across read-only audits. |
| Existing demo approval | PASS | Organization 7 and application 6 both approved; no decision changed. |
| Live startup and service checks | OWNER VERIFIED | 9/9 managed processes. Flask creation, seven worker entry points, 36 Jinja templates, MySQL schema, Firebase configuration and RabbitMQ topology verified. |
| Live outbox and deadlines | OWNER VERIFIED | Three queued AttendanceOverdue events processed after authorized startup. Nine AttendanceOverdue and one AcceptanceTimedOut published in total. Zero pending outbox events, publication errors or acceptance/attendance candidates. |
| Firebase read-only | PASS | Correct project, three mapped users verified/enabled, Email/Password, localhost and enumeration protection enabled. |
| Intended password policy | PASS | Live Firebase SDK accepted both samples. Lowercase and digits optional. Force upgrade off. |
| Live capacity aggregates | OWNER VERIFIED | Final reconciliation found zero organization capacity counter mismatches. The earlier independent audit also found zero. |
| Local hosting image | PASS | Built separate test tag; non-root/read-only Gunicorn smoke, public/static/DB reads; isolated smoke container cleaned up. |
| Public hosting / DNS / TLS | NOT TESTED | No full hosted Compose deployment or publication attempted. |
| Real inbox / browser sign-ins | NOT TESTED | Admin reads and controlled verifier tests do not prove actual email link delivery/sign-in. |
| Human usability | MANUAL ACTION REQUIRED | 40 checklist tasks prepared; no participant outcomes or feedback fabricated. |

The [final test report](testing/FINAL_TEST_REPORT.md) records commands, initial
failures, fixes, scope and limits; JUnit/JSON artifacts carry machine-readable results.
The [event report](testing/EVENT_WORKFLOW_TEST_REPORT.md) maps every implemented
event to producer, payload, route, queue, consumer and effects. There are five
consumer processes, outbox and two scanners; Flask does not launch them implicitly.
Actual delivery/replay, backup/escalation, attendance, both feedback outcomes and
concurrent one-slot matching were tested. No invented acceptance/completion event
or external messaging capability is claimed.

### Database, security and professor feedback

The [database compliance report](testing/DATABASE_COMPLIANCE_REPORT.md) confirms
206 qualifying families: 26 DDL, 20 seed INSERT, 150 application and 10 academic.
The full inventory has 306 entries including 100 excluded ancillary/legacy/control
families; extra health/audit statements account for the difference from the prior
253-entry full inventory. Migration 003 adds one qualifying ALTER. SQL query shapes are
reported separately and overlap; no padding through page/sort/test variants occurs.

The [normalization report](testing/NORMALIZATION_REPORT.md) enumerates all 21
relations, candidate keys and functional dependencies. The owner confirmed that
migration 003 removed the stored backup flag from the live database. Isolated
tests verified report parity and migration guards. The generated active_slot
and operational caches still qualify broader normal-form claims. See the
[completed migration and recovery reference](database/REFERRAL_MIGRATION_RUNBOOK.md).

The [security audit](testing/SECURITY_AUDIT.md) covers token verification, mandatory
verified registration, role/session/CSRF/ownership, approval, injection/XSS, safe
errors and secret scanning. Historical development credentials remain public in
Git history; rotate reused values in a coordinated maintenance window. Historical
Firebase web identifiers are distinguished from Admin private keys. No history
rewrite or account/password/verification change occurred.

Professor feedback is addressed by SQL filtering/ordering before default 20-row
pagination, global aggregate counts, complete coordinator access across 250 fixture
requests, grouped partner metrics, compact requirements/messages, non-emergency
time-frame wording and participant task preparation. Previous SQLite timing samples
remain labeled as such. Actual participant sessions and production-scale MySQL
performance/load analysis are still required before making broader claims.

### Startup, delivery and remaining actions

Run from the project root after reviewing pending work:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check_health.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop_local.ps1
```

Startup refuses pending messages/outbox/deadline work unless `-ProcessPending` is
explicitly supplied. The complete guide explains those normal business mutations,
duplicate detection, private logs and startup failure handling. No startup command
seeds, resets, migrates, starts Docker infrastructure or changes Firebase users.

Use [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md),
[FINAL_DEMO_GUIDE.md](FINAL_DEMO_GUIDE.md),
[DEPLOYMENT_TEST_REPORT.md](testing/DEPLOYMENT_TEST_REPORT.md) and
[FINAL_SUBMISSION_CHECKLIST.md](FINAL_SUBMISSION_CHECKLIST.md) for the installation,
demo, final decisions and proposed commit groups. Commit commands are documented
for later review only; nothing was staged, committed, pushed, merged or published.

Remaining actions include reviewing staging, coordinating credential rotation if
historical values are still in use, checking real inbox delivery and running
participant sessions. Hosted deployment requires separate verification. See the
[exact publication review](testing/PUBLICATION_REVIEW.md) for excluded paths and commands.

ENSF 607 implementation/integration evidence: PASS; final submission sign-off:
MANUAL ACTION REQUIRED. ENSF 608 SQL/schema/isolated initialization evidence: PASS;
formal normalization and rubric sign-off: MANUAL ACTION REQUIRED. Full public
deployment and production-scale load or reboot validation are unverified.

## A Implementation summary

The active application uses `app/frontend.py` to render `frontend/templates` and
serve `/team-static` assets. The separate `app/templates` and `/static` trees remain
the local legacy demonstration; hosted mode disables its shared demo identity.
The deleted root Dockerfile is not required: hosting explicitly builds
`Dockerfile.hosting`. Existing cleanup, SQL changes, recovered worker/messaging
files and unrelated uncommitted changes were retained.

| Area | Implementation and reason |
| --- | --- |
| Identity and registration | `app/auth.py`, `app/registration.py` and new `app/services/member_registration.py` enforce verified claims, stop login-time provisioning, and commit user/profile creation atomically. |
| Verification and recovery | New `firebase-client.js`, `registration-verification.js`, `registration-recovery.js`, `_verification_panel.html` and `verify_email.html` share the verification/retry interface and keep credentials in memory. Existing login/register scripts and templates use them. |
| SQL lists | New `app/pagination.py`, shared list controls and pagination, and changes in member/organization/coordinator/frontend routes and browsing/offering/application services apply filters and ordering before bounded retrieval. |
| Coordinator review | New `coordinator/request_details.html` and a protected per-request route defer history and assignment lookups until the request is opened. |
| Language and forms | Display mappings, request notice, descriptive referral controls, required markers, field lengths, live field messages, readable timestamps and responsive controls improve the existing design. |
| Authorization and status | Member cookies require verified email. Referral services enforce approval restrictions; pending/rejected organizations see status without referral/service management. Member organization contact now appears after acceptance. |
| Missing runtime modules | New `app/services/timeouts.py` and `overdue.py` restore modules imported by existing workers/scanners. Their implementations use existing outbox events and request-first transaction locks. These are new implementations at missing paths, not historical files recovered from Git. |
| Reliability | Friendly HTML/JSON errors, configuration validation, optional analytics configuration, mandatory hosted Secure cookies, explicit local debug mode and a consistent broker virtual host address confirmed startup/error gaps. |
| Evidence and guidance | Three new regression-test files, `tools/check_submission_readiness.py`, the manual checklist, account-migration plan, query measurements and updated project guides support review and submission. |

The initial submission-improvement inventory, distinguishing that phase from
pre-existing changes, is [changed_files.json](testing/changed_files.json). Follow-up
database-review changes are recorded in [database_compliance_review.json](testing/database_compliance_review.json). Password validation's shared
JavaScript module, checklist partial and original 18 tests remain byte-for-byte
unchanged. The test-user utility keeps its password rules and now directs users
to registration completion instead of describing obsolete login-time provisioning.

## B Professor feedback resolution

| Original concern | Finding and implemented resolution | Verification and limits |
| --- | --- | --- |
| Feature language suggests emergency support | The request form asked how urgent it was and displayed High/Medium/Low; several tables said Priority and referral actions said Accept/Reject. Display labels now use Preferred time frame, As soon as possible/Soon/Flexible, Accept referral, Decline referral and Referred to coordinator. Organization approval decisions retain Approve/Reject. One notice explains non-emergency scope. | Render tests confirm original form values and 6/12/24-hour targets remain unchanged. Browser checks cover the forms and role pages. A few-day label was deliberately avoided because it conflicts with the existing 12-hour target. Participant comprehension still needs the checklist sessions. |
| Complete records are loaded before filtering/sorting | Member/organization/coordinator lists retrieved whole result sets; public eligibility queried areas once per service; coordinator requests loaded all history and assignment choices per row. SQL now filters and orders before pagination, bulk loads only current-page related records, and defers detailed review queries. | Synthetic SQL tests cover combined filters, ascending/descending ordering, pages, ownership and aggregates. Measured public browse SQL executions fell from 47 to 3. Live MySQL query plans and representative-size timings remain pending. |
| Simple ad hoc user testing would help | A 40-task checklist covers individuals, organization representatives, coordinators and cross-role/mobile/error scenarios, with expected outcomes and blank observation fields. | Developer and automated checks are separated from actual participant testing. No participant feedback or completed sessions are claimed. |

## C Authentication summary

### Password validation

The existing minimum of eight characters, ASCII uppercase and supported special
character, non-empty password and matching confirmation remains enforced before
Firebase account creation. Digits and lowercase remain optional. The live grey/green
checklist and friendly Firebase password-policy errors remain intact. Login and
existing-account recovery impose no new-password complexity rule.

### Email verification and registration completion

1. The form validates all fields and the existing password rules.
2. Firebase creates a preliminary account, or the existing email is recovered only
   by authenticating with its actual password.
3. The page switches to the shared verification screen at `/register/verify` using
   an in-document URL transition. This preserves in-memory details and authentication.
4. Firebase sends the verification link. The screen shows the email, inbox/spam and
   expired-link guidance, resend and check controls, loading state and a 60-second
   resend cooldown. Firebase rate limits remain authoritative.
5. After the link is opened, the application reloads the user and forces a fresh ID
   token. Flask validates it through the Admin SDK and requires the verified claim.
6. Individual user/profile or organization/representative/application creation
   commits in one transaction. Exact retries are idempotent; conflicting retries
   preserve saved details. Completion returns to login.

Unverified tokens are rejected before any registration SQL or session creation.
Unverified member cookies also fail closed. `/api/auth/me` is now a read-only identity
probe: it does not insert incomplete members or convert organization applicants.
It returns `registration-required` for verified identities without completed SQL
registration. CSRF, recent authentication, revoked-token checks and SQL-owned roles
remain enforced. Client role or verification fields cannot grant access.

### Recovery and organization approval

After closing/reloading or verifying on another device, **Finish registration**
authenticates the user in memory. If details are no longer available, the verified
user re-enters them on the same recovery screen. Passwords, ID tokens and pending
profile details are not persisted in browser storage or query strings. Network
failures retain in-memory details; repeated completion uses the same payload and
backend idempotence. Existing SQL accounts are never linked by email alone.

Organization completion creates `pending` / `submitted`, not approval. Pending or
rejected applicants can view their status/profile but cannot access referral or
service management. Rejected applications display a distinct result while the
organization retains the existing unapproved database enum. Acceptance requires an
approved organization, and business services reject pending referral actions.
Suspended partners retain existing handling of work already accepted.

### Firebase configuration still requiring the team

The readiness tool confirmed matching frontend/backend project IDs and the supplied
Admin credential file's project ID for `careconnect-bfb9e`. No private credential
contents were exposed. This does not verify live sign-in or Console settings.

In Firebase Console, verify Email/Password authentication, authorized local/hosted
domains and verification email templates/action links. Check minimum length 8,
uppercase and special required, lowercase/numeric optional, and forced upgrades on
sign-in disabled. No Console policy configuration is claimed.
[Firebase policy guidance](https://firebase.google.com/docs/auth/web/password-auth),
[email verification guidance](https://firebase.google.com/docs/auth/web/manage-users).

The separate [mapping review plan](testing/ACCOUNT_MIGRATION_PLAN.md) requires
identity evidence and explicit approval before any existing UID binding changes.
The live MySQL mapping inventory could not run because the configured service was
unavailable; no mapping audit or automatic migration is claimed.

## D Database optimization summary

| Page or workflow | Previous behavior | Current strategy and pagination |
| --- | --- | --- |
| Public browse services | All catalog services, one area query per service, all eligible providers, then Python filters. | One grouped eligibility query with search/category/delivery and whitelisted sort, bounded page; provider names/capacity only for page service IDs; a small category lookup. Default 20 displayed. |
| Public service details | Loaded the complete public catalog to find one ID. | Requested service ID is applied in SQL; related providers are limited to that service. No pagination. |
| Request service dropdown | Queried each service's eligible areas separately. | One grouped query with the original exactly-one-distinct-active-area eligibility rule. Small reference list remains complete. |
| Individual request history | All owned requests followed by Python status filtering. | Owner and status restrictions in SQL before deterministic sorting and pagination. Default 20. |
| Individual dashboard | All owned requests to count and slice five. | One aggregate over owned requests plus five latest rows; notifications remain bounded. No summary pagination. |
| Organization referrals | All organization referrals followed by Python status filtering. | Organization and status constraints precede sorting/pagination. Cancellation display semantics remain intact. Default 20. Detail lookup is scoped to the owned request. |
| Organization services | All owned offerings were rendered. | Organization, search and availability filters precede SQL sorting/pagination. Small catalog/category/area dropdowns remain full reference lookups. Default 20. |
| Organization dashboard | All referrals to calculate totals and slice incoming rows. | Full organization aggregates plus at most five incoming referrals. Pending/rejected dashboards do not query or reveal referral summaries. |
| Coordinator requests | All requests, every history record and per-request assignment queries, then Python filters. | Complete filters and deterministic order precede pagination. Histories/eligible choices are fetched for one protected detail view. Default 20. |
| Coordinator organizations | All organizations, offerings and representatives, then Python status filtering. | Status and order in SQL; current-page related services/areas/representatives fetched in bulk using bound ID lists. Default 20. |
| Coordinator approvals | All pending applications. | Pending/latest-application rules retained in SQL with whitelisted sort and pagination. Default 20. |
| Coordinator dashboard | All requests/history and all pending applications for summaries/counts. | Full aggregate totals plus five recent attention requests and five pending applications. No summary pagination. |
| Coordinator reports | Existing grouped SQL counts across complete data. | Retained correct full-dataset aggregates; a list page never limits report totals. No artificial pagination of aggregate summaries. |
| Notifications | Already limited to ten or twenty recent unread records. | Existing bounds retained and interface explicitly says Recent unread notifications. The menu count is not presented as the complete unread total. |
| Partner matching | Queried ranking metrics once per eligible partner. | A single grouped query supplies the same load/acceptance/on-time ranking inputs. Existing tie-breaks, locks, deadlines and matching rules are retained. |
| Manual assignment | Loaded all organization names for each list-row eligibility lookup. | Choices load only in a single request review; names are fetched only for eligible organization IDs. |

All growing lists use backend sorting of the full filtered dataset, never a
client-only sort of the displayed page. Parameters are bound; sort expressions
come only from server mappings. Page numbers and 10/20/50 page sizes are validated.
Filter submission resets the page; pagination, detail/back links and service validation errors preserve the active values. Only supported filter parameters are retained, so URL-generation controls cannot be forwarded from user input. Empty
views include recovery links. One lookahead row detects Next without a separate
count query: a full default page fetches at most 21 primary rows and displays 20.
No unqueried total-page count is shown. Small reference APIs retain their existing
array contracts.

### Before and after query examples

Before member history fetched all matching ownership records and filtered status
in Python:

```sql
SELECT ... FROM service_requests sr ...
WHERE sr.member_id=:owner
ORDER BY sr.created_at DESC,sr.request_id DESC;
```

Now status is applied before the bounded, server-selected order:

```sql
SELECT ... FROM service_requests sr ...
WHERE sr.member_id=:owner AND sr.status=:status
ORDER BY sr.created_at DESC,sr.request_id DESC
LIMIT :page_limit OFFSET :page_offset;
```

Before coordinator history selected every history row for a list. It now runs only
when opening one request:

```sql
SELECT r.request_id,h.new_status,h.changed_at
FROM referral_status_history h JOIN referrals r ON r.referral_id=h.referral_id
WHERE r.request_id=:request
ORDER BY h.changed_at,h.history_id;
```

The public eligibility query replaces per-service area queries with grouped active
offerings and `HAVING COUNT(DISTINCT a.area_id)=1`. Browse filters and LIMIT/OFFSET
then select the page, and the provider query uses `os.service_id IN :ids` with
SQLAlchemy expanding bound parameters. Organization lists use the equivalent
owner/status predicates; coordinator organization rows use a derived display status
so Rejected application and Pending organization are filtered correctly before
pagination. Reports continue to use complete `GROUP BY` aggregates.

### Measured evidence

The [measurement data](testing/query_measurements.json) compares the pre-task source
snapshot with this implementation against the same isolated SQLite fixture: 45
eligible services, 50 requests, 45 belonging to the selected member. These are single
local runs, with compilation/cache and SQLite effects; they are not production or
MySQL latency estimates.

| Check | Before | After |
| --- | --- | --- |
| Public browse SQL executions, including eligibility/provider/category work | 47 | 3 |
| Public primary service records loaded/displayed | 45 loaded | 21 fetched, 20 displayed |
| Public single-run elapsed time | 7.417 ms | 1.648 ms |
| Individual history SQL executions | 1 | 1 |
| Individual history primary records loaded/displayed | 45 loaded | 21 fetched, 20 displayed |
| Individual history single-run elapsed time | 2.564 ms | 1.152 ms |

The SQL tests additionally verify one request-dropdown query, exclusion of
multi-area services, current-page ownership, combined filters, last/empty pages,
no list-wide coordinator history/assignment queries, and full report totals.

### Index review without schema changes

The supplied SQL already defines request status/deadline, referral status/deadline,
unique request-attempt, organization status, service category/delivery, notification
user/read and outbox pending/deduplication indexes. Live index presence could not be
verified. No index or migration was applied.

After obtaining real MySQL EXPLAIN output on representative data, consider whether
`service_requests(member_id,created_at,request_id)`,
`referrals(organization_id,referral_id)` and
`organization_applications(organization_id,application_id)` would improve the new
queries. Public eligibility may benefit from a service/status/area/organization
composite only if its plan shows a scan problem. Check existing implicit foreign-key
and InnoDB primary-key extensions to avoid redundant indexes. These are conditional
review candidates tied to actual predicates, not an approved schema change.

## E Testing summary

| Verification | Result |
| --- | --- |
| `python -m pytest -q` | 109 passed, zero failed after the database audit: the original 88 plus 21 focused audit/search/pagination regressions. All 18 original password tests are unchanged. |
| Python syntax | All project app, worker, tool and test Python files parsed successfully. |
| JavaScript syntax | Every first-party frontend script parsed in installed Edge; active authentication/verification modules also executed without script exceptions. |
| Imports and startup | Application factory and all seven worker entry points import; local test HTTP servers served Flask pages successfully. |
| Templates/assets | All 36 active Jinja templates compile; public/auth and protected list/dashboard/details/report templates render on synthetic fixtures and required static assets load. |
| Backend registration/security | Unverified/invalid/unavailable tokens fail closed; no premature SQL provisioning; repeated registration is transactional/idempotent; role injection and email-only linking fail; CSRF, authentication freshness, ownership and pending-organization restrictions tested. |
| Query behavior | First/last/invalid/empty pages, combined filters, ascending/descending sorting, filter retention, report totals, bounded retrieval, safe query-parameter retention, detail/back context, second-page service validation recovery and reduced query counts passed. |
| Event behavior | Timeout replay releases capacity once, outbox failure rolls back effects, overdue processing uses stable deduplication keys, ranking metrics load once, and consumer success/reject/requeue behavior passed. |
| Dependency check | `pip check` passed with no broken requirements. Existing package manifests were retained. |
| Compose checks | Local and hosting `config --no-interpolate --quiet` commands exited 0. The managed environment emitted Docker config-file access warnings. |
| Read-only service checks | MySQL schema/mapping check failed with OperationalError; passive RabbitMQ check failed with AMQPConnectionError. No live schema/mapping/topology success is claimed. |

### Developer browser checks

Installed Edge ran against a temporary local server using synthetic SQLite data
and Firebase/email stubs. Both forms passed all supplied password cases, including
native and forced-submit blocking, optional digits/lowercase and friendly policy
rejections. The verifier passed email display, unverified gating, reloading token
state, cooldown, rate limits, duplicate-email recovery, re-entry after closing a tab,
and existing short-password recovery. A deliberately interrupted completion response
preserved the same payload for a safe retry. Verified member login completed session
and dashboard navigation; unverified login never called the session API.

Public/registration/verification screens and member/organization/coordinator pages
were checked at 390 and 1000 pixel widths without horizontal page overflow. Table
overflow remains inside the table region. Verification screenshots were visually
reviewed. No real inbox messages, Firebase accounts, or project MySQL records were
created by these checks. The temporary browser driver was removed after testing.

### Tests requiring the team

Real email delivery, expired hosted action links, a genuinely signed/refreshed
Firebase token, production Admin SDK session issuance/revocation, MySQL locking and
concurrent behavior, actual RabbitMQ delivery/restart recovery, container image
build, HTTPS/DNS/proxy behavior and participant accessibility/usability sessions
still need the configured services and approved test environment. SQLite fixtures
strip MySQL `FOR UPDATE` only in tests; they do not establish MySQL lock behavior.

Use [the 40-task checklist](testing/ad_hoc_user_testing.csv) and
[session guide](testing/USER_TESTING_GUIDE.md). Every Actual outcome, Pass/fail,
Observed usability issue and Suggested improvement field is blank. Automated and
developer checks are not participant feedback.

## F Deployment readiness

| Component | Status and remaining requirement |
| --- | --- |
| Flask | Factory/import, health, templates, assets and synthetic HTTP flows pass. Missing configuration and request failures have friendly handling. Hosted mode disables debug. |
| MySQL | Existing MySQL/SQLAlchemy/pymysql configuration, enums and parameterized contracts are retained. Live connection and reviewed-schema preflight failed to connect; verify required Firebase/workflow columns, unique constraints and capacity protection before use. Partial ORM metadata is not a schema provisioning tool. |
| RabbitMQ | Existing exchange, routing keys, queues, consumers and at-least-once behavior retained. Setup now respects the same configured virtual host as connections. Live passive topology check could not connect. |
| Workers | All seven entry points import. Missing timeout/overdue modules were supplied; source tests cover their transactional/replay behavior. Real broker/database workflow integration is pending. |
| Firebase | Web/backend/Admin credential project IDs agree. In-memory client persistence and Admin token/session checks are retained. Console policy/domain/template and real inbox checks remain manual. |
| Hosting | Required Dockerfile COPY source paths exist, both Compose files validate, Firebase environment variables remain wired, optional measurement ID formatting is fixed and runtime secrets remain outside the image. The Docker daemon is unavailable, so no image build, Gunicorn/container, public deployment or restart claim is made. |

The original database/broker versions and existing volumes were preserved. The
restored scanners use the existing two-hour referral response cap and original
attendance deadlines; review existing deadlines before starting any `--apply`
scanner. Preview commands remain read-only unless `--apply` is explicitly supplied.

## G Remaining manual tasks

1. Start the intended local services without resetting or replacing volumes. Run
   `python tools/check_submission_readiness.py --database --rabbitmq` and resolve
   connection/schema/topology findings. Do not execute migrations or restore data
   without separate approval.
2. Review existing UID mappings privately using the separate migration plan. Resolve
   only explicitly approved mappings; do not link by email, promote roles, delete
   accounts or automatically verify email.
3. Verify the Firebase Console password policy, authorized domains, Email/Password
   provider and verification templates/action links in `careconnect-bfb9e`. Use a
   team-controlled inbox to complete both registration/recovery/login workflows.
4. Run an approved synthetic request through matching, accept/decline, timeout,
   backup/coordinator referral, attendance, completion, notifications and feedback.
   Exercise redelivery/restart behavior without resetting live records. Confirm
   pending/rejected organization restrictions with real sessions.
5. Run MySQL EXPLAIN and representative-data timing checks. Request approval only
   for concrete, justified schema/index changes, if any are still needed.
6. With Docker Desktop running, build `Dockerfile.hosting` and verify runtime
   services in the approved test environment. Review hosting secrets, DNS and HTTPS.
   Obtain explicit approval before a public deployment.
7. Conduct the 40-task ad hoc sessions, fill in actual outcomes and observations,
   fix reproducible issues and repeat affected tasks. Include only actual anonymous
   participant findings in the academic submission.
8. Review all existing and new working-tree changes with teammates. Any later Git
   commit/push/merge is a separate team action; none was performed here.

## H Git status after the initial submission improvements

This is the initial improvement-phase snapshot. The follow-up database audit is
recorded separately in Section I and its evidence file.

| Working-tree state | Count |
| --- | --- |
| Modified tracked files | 68 |
| Deleted tracked files retained from prior cleanup | 41 |
| Untracked files including prior recovered work | 39 |

Compared with the start of this task: 55 existing files modified, 23 files created, and zero existing files deleted.


These counts include the large pre-existing working tree, not just this task.
Existing deleted files and recovered/untracked backend files remain present in
their prior working-tree states. The task inventory distinguishes modified existing
source files from newly created files; it does not relabel pre-existing recovered
files as new work. No unrelated deletion, staging, commit, push or merge occurred.

## I ENSF 608 database compliance and feature preservation review

The November 25, 2026 follow-up audit satisfies the supplied minimum-25 requirement
without adding queries for counting purposes. There are **205 distinct meaningful
statement families**, including **150 active application query families** independent
of schema creation, seeds, maintenance scripts, legacy demos and transaction markers.
Of the application families, 117 are reads, 18 are inserts and 15 are updates. Even
the application reads alone exceed 25.

### Inventory and counting rules

The complete inventory contains a query number/name, all source locations, SQL or
SQLAlchemy equivalent, category, business purpose, associated feature, verification
status, and optional-clause notes. It is available as
[current CSV](testing/sql_inventory.csv) and [current JSON](testing/sql_inventory.json).
The [HEAD CSV](testing/sql_inventory_head.csv) and
[HEAD JSON](testing/sql_inventory_head.json) provide the historical comparison.
The [query-change mapping](testing/sql_query_comparison.csv) reviews every previously
counted application family, and [review evidence](testing/database_compliance_review.json)
records totals and test results.

| Inventory group | Current meaningful families | Git HEAD meaningful families |
| --- | --- | --- |
| Schema and DDL | 25 | 21 |
| Seed and synthetic data-insert families | 20 | 20 |
| Active application queries | 150 | 122 |
| Standalone academic demonstration queries | 10 | 10 |
| Meaningful total | **205** | **173** |

The full inventory has **253 entries**, including 48 excluded families: 38
maintenance/control/support operations, seven local legacy-demo operations, and
three transaction-boundary equivalents. The 20 seed-cleanup DELETE statements are
listed among excluded maintenance operations; they were not executed and do not
contribute to the 205 meaningful total. The minimum is established by the 150
application families, not by these excluded entries.

Distinct means a parameterized business-query/template family. It does not mean
every possible SQL string after substituting data values. Identical schema creation
in `schema.sql` and `schema_safe.sql` counts once. Seed rows and alternate inserts
for the same entity count as one seed family. Inline keys, indexes and constraints
belong to their enclosing CREATE/ALTER statement and are not extra statements.
Optional filters, page sizes, sort variants, binding-variable names and repeated
executions do not add queries. ORM read variants with ordering/locking or `get`
versus equivalent primary-key selection are conservatively merged. A generic
pagination wrapper is not counted again for each invocation. A nested SELECT is
part of its enclosing statement, so `database/queries.sql` contains ten academic
queries, not a count inflated by its subqueries.

This is a static source inventory, not a claim that all statements executed against
MySQL. Each inventory row explicitly labels its verification status. The JSON also
contains source-text hashes, declared schema relationships and unresolved-expression
checks; none were unresolved in the final run. The tool never imports application
code, opens a database connection or executes the inventoried SQL. It omits seed
row values from the exported statements.

To reproduce the inventories and tests from the project root:

```powershell
.\.venv\Scripts\python.exe tools/audit_sql_inventory.py
.\.venv\Scripts\python.exe tools/audit_sql_inventory.py --revision HEAD --output docs/testing/sql_inventory_head
.\.venv\Scripts\python.exe -m pytest -q
```

### Git history and changes to queries

The comparison uses commit `abad5c82c1b33441ec37ec672d629a34a5f82047` (current HEAD).
Coordinator controls were also checked at `2bb434a` and `61e9ce5`. Recent improvements
remain uncommitted, so they are compared as working-tree changes, not attributed to
a nonexistent optimization commit. The extra workflow migration and recovered
runtime modules were already present before this audit; they are not additions
made to reach the query count.

Of the 122 HEAD application families, **112 retain the same normalized query
pattern** and **ten have source-reviewed changed templates**. No removed business
feature was identified. The current total of 150 also reflects earlier uncommitted
restoration, security/registration work and aggregate queries; the net increase
does not mean this audit added 28 new operations. The only application correction
in this audit adds a search predicate to an existing request-list query family.

| Previous template | Current inventory mapping | Preservation assessment |
| --- | --- | --- |
| HEAD Q051 coordinator request listing | Q057 | Complete filters and deterministic sorting precede pagination; all records remain reachable. |
| HEAD Q052 coordinator history for every request | Q058 | History is fetched for the opened request and still includes all its referral attempts. It was deferred, not deleted. |
| HEAD Q054 organization listing | Q062 | Complete status filtering precedes pagination, including rejected-application presentation. |
| HEAD Q055 organization offerings/areas | Q063 | Same related data is fetched in bulk for the current page's organization IDs. |
| HEAD Q056 organization representatives | Q064 | Same contact selection is fetched for the current page's organization IDs. |
| HEAD Q066 representative identity | Q075 | Latest application status was added to distinguish rejection from pending approval; role and ownership checks remain. |
| HEAD Q082 attendance representative check | Q089 | Approval restrictions were strengthened; valid owned attendance remains supported. This is a security change, not a removed feature. |
| HEAD Q109 service choices | Q117 | Grouped eligibility replaces per-service area reads and retains the one-distinct-active-area rule. |
| HEAD Q118 manual-assignment organization names | Q128 | Names are limited to eligible IDs and loaded on request review; the existing eligibility and attempt rules remain. |
| HEAD Q163 public provider query | Q189 and Q190 | Service fields and provider summaries are fetched with page/ID scope instead of loading the entire catalog. |

Other query rearrangements retain their purposes: dashboard aggregates replace
counting complete Python lists; member/organization status predicates move before
pagination; partner ranking metrics are grouped into one query using the same
ranking criteria. Login-time user insertion was moved to verified registration
transactions, preserving account/profile creation while removing premature access.
All ten standalone academic queries and their actual SQL semantics are unchanged
from HEAD after ignoring comments/formatting. Their original author/course
attribution remains in the SQL files.

Reducing public-browse SQL executions from 47 to three in the earlier synthetic
measurement removed repeated round trips, not 44 independent academic operations.
It remains distinct from the query-family inventory used for ENSF 608.

### Entities, relationships and normalization

Both baseline schema files retain the same **20 domain-table definitions** as Git
HEAD, including primary/foreign keys, referential actions, unique keys, enums and
indexes. The existing workflow migration adds `event_outbox`, giving **21 declared
tables, 21 primary keys and 34 foreign-key relationships**. The static reference
check found no missing target table or referenced column. The five nonduplicate
migration ALTER/CREATE operations and 20 base CREATE TABLE statements produce the
25 DDL count. The Firebase migration, active-referral uniqueness, capacity check,
notification deduplication and outbox uniqueness definitions remain present.

The audit made no schema, model or SQL-script change. All database files and diagrams
were preserved byte-for-byte relative to the audit's starting snapshot. Existing
partial ORM mappings are not a complete schema definition: for example, the User
mapping does not describe the migrated Firebase UID/nullable-password contract.
The authoritative SQL plus approved migrations remain necessary; do not use
`create_all()` to provision or repair the project database.

The normalization PDF was inspected. It explains the separation of roles, service
categories, priorities, offerings and support relationships through 1NF/2NF/3NF
principles. It explicitly qualifies a strict all-table 3NF claim because values
such as `is_backup` and generated `active_slot` follow other workflow values.
Cached capacity/SLA fields also need their business invariants documented. Query
optimization and the search predicate do not alter these dependencies, entities or
relationships. **Preservation of the existing design passes; a formal proof that
every relation is strictly in 3NF is not established by the existing materials.**
That qualification is retained rather than silently changing the schema or
overstating academic compliance.

### Coordinator functionality comparison

| Capability | Previous implementation | Current result |
| --- | --- | --- |
| All service requests | Complete result set loaded into Python. | All remain accessible through backend pagination; 250/250 synthetic records were reached exactly once. |
| Search requests | Absent from the inspected committed and pre-audit implementation. | Added reference, service/category, description, requester-name/email and organization search as a bound SQL predicate before pagination. This fills the requested capability gap; it is not described as a historical regression. |
| Status/time-frame/organization/attention filters | Four controls in the inspected HEAD, integration and original coordinator templates. | All four retained, combinable and applied before pagination. |
| Category/date dropdown filters | Not present in the inspected coordinator versions. | No such existing UI filter was removed. Category text is searchable; standalone dated/category analytical SQL remains unchanged. New date controls were not invented during a preservation audit. |
| Sorting | Fixed SQL ordering in the older template. | Existing recent improvements provide whitelisted newest/oldest, earliest target, and service A–Z/Z–A ordering over the full matching dataset. |
| Individual details and referral history | Expanded inline for every list row. | Protected Review request page retains contacts, service/category, description, delivery, targets, all referral history and valid assignment controls. |
| Pending/completed/coordinator-referred requests | Status and attention filters plus request review. | Preserved; display wording does not change database values. |
| Organization management and decisions | List/detail contacts, approve/reject, suspend/reactivate and transactional service methods. | Preserved with pagination and the existing CSRF, role, approval and state checks. |
| Escalation management | Review attention reasons and assign eligible organizations to unmatched requests under existing attempt/deadline rules. | Preserved through attention filters and individual review/assignment. No bypass or extra attempt was introduced. |
| Dashboard statistics | Counts derived from complete loaded lists. | Full-dataset SQL aggregates with small summaries; the 250-request fixture reports 250, regardless of list page. |
| Reports | Complete request/category, approved-organization and helpful-feedback aggregates. | Reporting service source is unchanged from HEAD, and totals remain independent of list pagination. |

### Feature preservation for other roles

The password module, checklist, existing password tests, verification/recovery
scripts, authentication/approval services and Firebase configuration were untouched
by this audit. The only application edits are coordinator request search and its
template control. The test fixture adds a test-only MySQL CONCAT equivalent;
production continues to target MySQL.

Individual service browsing, owned requests, completion/feedback and organization
service/referral workflows remain covered by the existing regression suite. Primary
matching, backup matching, timeout/overdue processing, notifications, transaction
locks, deduplication, feedback delivery and all RabbitMQ producer/consumer contracts
were retained without modification. Existing follow-up consists of coordinator
attention for overdue/late cases plus the completed-service feedback workflow; no
separate scheduled outreach worker was present in the reviewed source, and none
was introduced or removed here.

### Filtering and pagination evidence

The new `test_coordinator_preservation.py` fixture contains 250 requests and exercises:

- All 13 pages at 20 records per page, including ten records on the last page,
  without missing or duplicate request IDs.
- Oldest/newest ordering across all five pages when using 50 records per page,
  checked against complete-dataset ordering.
- Reference `CC-249`, late-page description text, literal wildcard characters and
  organization searches, with SQL-injection-like input producing no widened access.
- Combined Completed + High + organization + Manual review filters, yielding ten
  records on the first filtered page and six on the second; navigation retains
  filters and Clear restores the unfiltered list.
- All original attention categories, empty search, invalid search length, and
  rejection of member/organization access to coordinator search.
- Dashboard/report totals over all 250 requests and a detail view containing
  sent, declined and accepted history from three referral attempts.

The SQL inventory tests independently check duplicate-schema/seed suppression,
quoted semicolons, ORM-equivalent deduplication, preserved baseline definitions and
academic queries, and the active-query minimum. **The full suite passes 109 tests**,
including all 88 pre-audit tests. Source startup checks also pass for Flask,
all seven worker imports, all 36 Jinja templates and hosting source paths.

The read-only live database preflight was attempted and failed with OperationalError.
No production MySQL statement, constraint, transaction-lock or EXPLAIN result is
claimed. SQLite fixtures use a test-only CONCAT shim and strip MySQL row-lock syntax;
they establish application behavior, not live InnoDB locking or deployed constraints.
No destructive SQL or live data mutation was executed.

### Compliance conclusion and remaining clarification

The minimum-25 requirement as supplied in this request **passes**, independently
of DDL and seeds. No loss of coordinator or other existing business functionality
was found; missing coordinator search was implemented without undoing optimization.
The declared schema, relationships, academic SQL and transaction design are preserved.

Before final academic evaluation, confirm whether the marking rubric accepts the
application query families as requested here. The standalone demonstration file
contains ten queries; it is not being presented as a file containing 25 independent
SELECTs. Also clarify whether strict all-relation 3NF certification or a separate
scheduled follow-up contact feature is expected beyond the existing documented
design. These would require business/rubric decisions, not padding the query count.

Live MySQL schema/constraint, concurrency and query-plan checks remain necessary
once services are available. No migration, data reset, account update, Firebase
configuration change, RabbitMQ contract change, commit, push or merge occurred.

This audit changes only four pre-existing files: `app/coordinator.py`, its request
list template, the isolated list-test fixture, and this report. New files provide
the static inventory tool, two regression-test modules and the CSV/JSON evidence.
All 13 database files/diagrams, 23 business-service modules, six messaging modules
and 14 frontend JavaScript files match their audit-start hashes. The complete
working tree, including prior work, has 68 modified tracked files, 41 prior deleted
tracked files and 48 untracked files. No existing file was deleted by this audit.
