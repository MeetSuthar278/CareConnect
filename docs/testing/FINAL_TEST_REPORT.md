# Final integration test report

Updated November 26, 2026 (America/Edmonton). Historical results in earlier reports
are retained as dated evidence; this report describes the final integration pass.

| Check | Status | Evidence / limits |
| --- | --- | --- |
| Regression suite | PASS | 112 tests. The default run skipped 12 opt-in cases, which were run separately. Raw JUnit stays local. |
| Disposable MySQL/RabbitMQ integration | PASS | 12 tests on disposable MySQL 8 and RabbitMQ. See `isolated_integration.json`. Raw JUnit stays local. |
| Browser checks | PASS | 97 checks, including 15 JavaScript files parsed, in `browser_smoke.json`. Edge executes real frontend modules with a local fake Firebase SDK. |
| Python syntax | PASS | 75 Python files parsed; `source_validation.json`. |
| PowerShell syntax | PASS | All three scripts parsed with the PowerShell language parser. |
| Templates / runtime imports | PASS | 36 active templates compiled, seven worker entry points imported. |
| Dependencies / whitespace | PASS | `python -m pip check`, `git diff --check`. |
| Current MySQL | PASS | Schema preflight, 21 tables, 34 FK orphan checks, no orphans. Existing records were read only. |
| Current RabbitMQ | PASS | Exchange and five queues passively inspected; zero ready messages/consumers. No live consumer started. |
| Firebase Admin | PASS | Three mapped users read successfully; all verified, none disabled. No user changed. |
| Firebase requested password policy | PASS | Real SDK accepted Password@ and PASSWORD@. Ten policy cases matched the app validator. |
| Current capacity cache invariant | PASS | Owner reports correcting eight offerings. Independent read-only reconciliation found zero mismatches. |
| Real inbox verification/reset and browser sign-in | NOT TESTED | No passwords requested, actual emails sent, users created or verification states changed. User-reported prior sign-ins are separate evidence. |
| Human participant usability | MANUAL ACTION REQUIRED | Checklist outcome fields remain blank; no participant feedback invented. |

## Reproduce

Run from the repository root with the existing private configuration:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=docs/testing/regression.junit.xml
.\.venv\Scripts\python.exe tools/check_submission_readiness.py --database --rabbitmq
.\.venv\Scripts\python.exe tools/run_isolated_integration.py
python tools/browser_smoke.py --venv-site-packages .venv/Lib/site-packages
.\.venv\Scripts\python.exe tools/audit_live_environment.py
.\.venv\Scripts\python.exe tools/audit_sql_inventory.py
.\.venv\Scripts\python.exe tools/audit_repository_security.py
```

The browser command used system Python 3.11 with installed websocket-client and
the project's venv packages. Alternatively install `requirements-browser.txt` in
the venv and use its Python without the extra path option. Microsoft Edge is needed.
Docker access is needed for the integration runner. It creates new services using
cached MySQL/RabbitMQ images and removes only its own labeled container IDs/storage.

## Coverage and observed fixes

Existing tests verify all requested password examples, mismatch/empty confirmation,
early Firebase-call guards, friendly policy rejection, verified registration,
recovery, recent-auth/session CSRF, role restrictions and SQL pagination. The
coordinator fixture still traverses all 250 requests over 13 pages, including late
search results, combined filters, full referral histories and global report counts.

The network suite runs five real consumer subprocesses and an outbox dispatcher.
It tests creation through matching, notifications, decline/timeout backups, three
attempt escalation, no-capacity escalation, manual rescue, overdue/late attendance,
completion, positive/negative feedback, idempotent replay, transactional rollback,
outbox retry, member/organization registration, approval/rejection, offering/profile
updates, ownership, CSRF and concurrent capacity reservation. The final test runs
the complete nine-process local supervisor, duplicate-start, health and owned-stop
checks while an unrelated Python process remains alive.

The first fresh regression run returned 107 passes and two failures because earlier
tests assumed the pre-Firebase users DDL. They now compare the exact approved UID /
nullable-hash transformation and all other original schema/query definitions.
A new assertion merges the two equivalent Firebase migration copies. The first
network run exposed an incorrect test exception expectation: MySQL CHECK error
3819 uses `OperationalError`; the test now asserts that exact code. No production
constraint or assertion was removed to bypass either failure.
The expanded profile ownership test initially expected 404; the existing service
uses 403 for a representative/org mismatch. The final test asserts that exact
documented denial and verifies the target organization's data remains unchanged.
Broker configuration also imports safely without a password, while actual topology
setup fails before connecting if the private password is missing; this was checked
directly after removing the old hardcoded fallback.

Browser harness development exposed navigation/async/form-selector issues in the
new harness; those were corrected before its final 97-check run. No application
redesign was needed. Mobile and desktop screenshots were inspected; filenames are in
the JSON evidence. These developer checks do not constitute participant research.

## Limits

This is an academic readiness check, not a penetration-test certification or a
load/availability guarantee. Broker crash between confirmed publication and SQL
commit can replay an event; handlers use business keys and state checks. Existing
tests mock malformed-message handling and broker failures where noted; a complete
broker outage/restart and Windows machine-reboot exercise was not performed.
Production DNS/TLS, backups/restore, live inbox action links and participant sessions
remain unverified. The live capacity follow-up returned zero mismatches.

The November 26 follow-up also rehearsed demo SQL and the final referral migration, precondition rejection and row parity on disposable MySQL. Live signup and inbox delivery remain untested.

The built normalized image passed read-only HTTP smoke using the existing data.
Guarded schema startup also passed on disposable MySQL.

## Owner-executed live verification

The owner rehearsed migration 003 and applied it live. All 21 table fingerprints
matched and every retained referral attribute was preserved. The owner confirmed
removal of the is_backup column and its index. Startup reached 9/9 managed
processes. Flask creation, seven worker entry points, 36 Jinja templates, MySQL
schema, Firebase configuration and RabbitMQ topology checks all passed.

Authorized startup processed three pending AttendanceOverdue events. The final
outbox contained nine published AttendanceOverdue events and one published
AcceptanceTimedOut event. It had zero pending events and zero publication errors.
Both deadline candidate counts and the capacity mismatch count were zero.

Final live totals were 21 tables, 17 users, seven organizations, 25 offerings,
40 requests, 29 referrals and 10 published outbox events. See the
[owner-verified results](referral_normalization_live.json). These terminal results
are separate from the automated regression, isolated tests and browser checks.
Participant sessions, real email delivery and hosted deployment are unverified.
