# Running and deploying CareConnect

CareConnect supports community partnerships (SDG 17), with secondary support for
well-being (SDG 3). It is an academic non-medical referral system. Flask serves
`frontend/templates` and `/team-static`; no Node build is required.

## Existing Windows environment

Keep the current `.env` and external Firebase service account. The existing MySQL
and RabbitMQ containers are `careconnect_demo-om-rabbitmq-demo-mysql-1` and
`careconnect_demo-om-rabbitmq-demo-rabbitmq-1`; their host ports are 3307 and 5673.
Do not start another Compose project on those ports or replace these containers.
The current MySQL schema includes migrations 002 and 003. The owner verified
startup with 9/9 managed processes. Keep the existing database and running
services intact. Use the [migration runbook](database/REFERRAL_MIGRATION_RUNBOOK.md)
for recovery or a separate legacy installation.

Install requirements only if needed, using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools/check_submission_readiness.py --database --rabbitmq
```

Private configuration needs SECRET_KEY, DATABASE_URL, the RABBITMQ_* connection
variables, FIREBASE_PROJECT_ID=`careconnect-bfb9e`, all required FIREBASE_WEB_*/web
identifiers and GOOGLE_APPLICATION_CREDENTIALS pointing outside Git. Use the keys
shown in `.env.example`, with actual values supplied privately. Preserve existing
values; placeholders are not working credentials. New Compose infrastructure also
requires private MYSQL_ROOT_PASSWORD and MYSQL_PASSWORD; changing these variables
does not rotate users already stored in a persistent volume.

Inspect existing work before enabling processors:

```powershell
.\.venv\Scripts\python.exe deadline_checker.py --kind acceptance --once
.\.venv\Scripts\python.exe deadline_checker.py --kind attendance --once
```

These commands preview IDs only. Current historical seed rows include expired
deadlines. The latest read-only capacity reconciliation found zero mismatches. Review
the database report before permitting normal background processing. Starting
workers/scanners processes durable application work and may update those records.

One command starts the application, five consumers, outbox and both scanners:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

If pending messages/outbox rows/deadlines exist, startup refuses to process them
implicitly. After reviewing/authorizing that work, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1 -ProcessPending
```

Open `http://127.0.0.1:5000`. `-Port 5001` selects another free web port. Startup
checks Docker, existing DB schema, passive broker topology, private Firebase
configuration and occupied web port; it refuses existing consumers or separate
outbox/scanner Python processes. A lock prevents competing managed supervisors.
It never creates containers, tables, migrations, queues or Firebase accounts.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_health.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop_local.ps1
```

Stop contacts the authenticated local supervisor, which terminates only its own
Popen children. It does not kill unrelated Python processes or stop Docker services.
The supervisor test verified this behavior. Private control state and per-process
logs are under ignored `.local/`; do not publish them. On a child failure, the
supervisor stops its other children and records failure. Review logs/configuration
and restart; it does not run duplicate auto-repair commands or silently reset data.
Windows task termination can interrupt work, so durable outbox/idempotency handle
replay. Power-loss and OS reboot recovery are not certified by the local smoke test.

## Isolated validation / new installation rehearsal

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools/run_isolated_integration.py
```

The integration runner requires cached `mysql:8.0` and `rabbitmq:3.13-management`
images. It creates its own labeled containers and random localhost ports, uses
fresh synthetic credentials/data, tests baselines/seed/migrations and actual workers,
then removes its own container IDs and temporary storage. Existing data is never
the test target. Allow several minutes for image/service startup.

For a separate permanent fresh environment, first choose empty volumes and free
ports, set private configuration, and review the target. `schema.sql` drops/recreates
careconnect_db; `schema_safe.sql` still creates tables and is only for a fresh
database. `seed.sql` deletes existing rows. None may be run against the current
project database. Current baselines already contain Firebase UID/nullable-hash
support; fresh baseline → optional synthetic seed → workflow migration 001 is the
tested order. Migration 002 is exclusively for an older users table without UID.
The teammate Firebase migration is equivalent, not a second required upgrade.

## Hosting

See [HOSTING_RUNBOOK.md](hosting/HOSTING_RUNBOOK.md) for the Linux VM, secrets,
DNS/TLS and reviewed export/restore sequence. Hosted Compose uses an independent
project/volumes, Gunicorn, Caddy, MySQL, RabbitMQ and all eight background processes.
No SQL is automatically imported at startup. A new empty hosted volume must be
provisioned separately before the schema preflight can pass.

```powershell
docker compose -f compose.hosting.yml config --no-interpolate --quiet
docker build -f Dockerfile.hosting -t careconnect-submission-test:local .
.\.venv\Scripts\python.exe tools/check_container_image.py
```

The last command runs only a localhost image smoke against read-only MySQL/public
endpoints and cleans up its own container. It does not deploy workers or mount an
Admin key. The local image build/smoke passed; a complete hosted Compose deployment
and public HTTPS sign-in remain NOT TESTED. Do not run hosted `up`, purchase hosting
or publish DNS until the team approves the deployment and its data provisioning.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Docker unavailable | Start Docker Desktop; check access. Preserve existing containers/volumes. |
| DB/schema preflight fails | Verify private DATABASE_URL/3307 and already-applied migrations; do not reset/reapply 002. |
| Queue/exchange missing | Review intended broker/vhost and topology separately; health/startup do not create it. |
| Existing consumer/scheduler detected | Identify its owner and use one launch method. Do not kill all Python processes. |
| Pending work refusal | Preview deadlines/queue counts and review data, then explicitly choose -ProcessPending. |
| Intended-valid password rejected | Adjust the two extra Console password requirements described in SECURITY_AUDIT. |
| Verified login cannot resolve SQL role | Verify UID ownership/mapping with the team; never link by email or edit teammates' coordinator records automatically. |
| Supervisor process exits | Review the named .local log privately; fix its dependency and rerun startup. |
| No verification/reset email | Check inbox/spam, Firebase templates/authorized domains/quota; test only an owned account. |

## Expanded synthetic demo rehearsal

Run tools/run_isolated_integration.py to reproduce the expanded demo on a separate
database inside its disposable MySQL container. The test initializes schema.sql,
then seed.sql, then migration 001, and creates the synthetic IDs and partner
offerings required by demo_data.sql. It commits the fixture within the test
container and verifies user, coordinator, organization, offering, request,
referral and capacity totals. Seed contacts use reserved example.invalid addresses.
They do not provide Firebase sign-in accounts.

demo_data.sql is a manually reviewed scenario extension with a transaction kept
open by design. It is not an initializer for production or a rerunnable seed.
Migration 003 is only for an existing legacy database with the stored flag.
Fresh schemas already omit it. Apply it only during the approved maintenance
window in the migration runbook.
