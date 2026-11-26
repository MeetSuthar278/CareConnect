# CareConnect

Community wellness referrals for ENSF 607/608 at the University of Calgary, aligned
with SDG 17 (primary) and SDG 3 (secondary). CareConnect is a university project for non-medical community support,
not emergency assistance. Use synthetic data for demonstrations.

## Project structure

| Path | Purpose |
| --- | --- |
| `app/` | Flask application, API routes, authentication, and business services |
| `frontend/` | Current Jinja templates, styles, scripts, and local Bootstrap assets |
| `app/templates/`, `app/static/` | Separate legacy request demonstration |
| `database/` | SQL baselines, sample data, analytical queries, diagrams, and normalization report |
| `deploy/` | Hosting configuration and read-only schema preflight |
| `tools/` | Interactive Firebase and synthetic workflow verification utilities |
| `tests/` | Focused password, verified-registration, authorization, pagination, and event regression tests |
| `docs/` | Authentication, frontend integration, and hosting documentation |

The frontend is served by Flask; no Node runtime or frontend build is required.
Firebase browser authentication loads its SDK from Google and requires network access.

## Functional and quality requirements

| Role | Implemented scope |
| --- | --- |
| Individual | Verified registration/recovery, login/logout/reset, profile, catalog search, owned requests/tracking/history, notifications and completed-service feedback. |
| Organization | Verified application, separate coordinator approval, profile, service/capacity/availability settings, owned referrals, attendance/completion and authorized notifications. |
| Coordinator | SQL-owned role, application decisions, organization management, all requests/search/filters/sorts/pages/history, attention/manual assignment choices and global reports. |

Security requires verified Firebase identity plus server-owned SQL roles, object
ownership and protected browser mutations. Reliability requires transactional
business/outbox writes, confirmed publication and idempotent processing. Efficiency
requires SQL-side filters/order and bounded lists with global aggregates. Usability
requires consistent branding, responsive forms and clear non-emergency language.
Maintainability requires shared validation/lifecycle code, reproducible isolated
tests and documented provisioning. These are project requirements; broader uptime,
load and production-security guarantees have not been established.

## Checkout status

The Flask application and all seven worker entry points import successfully. The
active frontend, mandatory email verification and registration recovery, bounded
SQL lists, and existing workflow contracts have automated regression coverage.
The November 26, 2026 pass verified 112 regression tests, 36 active templates,
97 synthetic browser checks and real MySQL/RabbitMQ workflows in disposable Docker
containers. The hosting image built and passed a localhost-only Gunicorn/MySQL
smoke. Read-only Firebase Admin checks confirmed all three mapped accounts are
verified; all four coordinator records remain. No live records were changed.

The November 26 checks confirmed the corrected Firebase policy and zero live
capacity mismatches. Participant testing, real inbox links and hosted deployment
remain outstanding. See the

[final test report](docs/testing/FINAL_TEST_REPORT.md),
[submission checklist](docs/FINAL_SUBMISSION_CHECKLIST.md), and
[manual user-testing checklist](docs/testing/ad_hoc_user_testing.csv).

## Local setup

The hosting image uses Python 3.12. For a Windows development environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create a private `.env` from `.env.example` for a new environment; preserve any
existing configuration. Set `SECRET_KEY` and `DATABASE_URL`. Configure Firebase
Application Default Credentials outside the repository and use the project matching
the frontend's public web configuration. See [authentication](docs/authentication.md).
The interactive tools also require `FIREBASE_WEB_API_KEY` in their process environment.

For a new machine only, after choosing unused ports and private MYSQL_*/RABBITMQ_*
credentials, the local infrastructure configuration is started with Docker Desktop running:

```powershell
docker compose up -d mysql rabbitmq
```

Host-run processes use MySQL port 3307 and RabbitMQ port 5673. Container connections
use ports 3306 and 5672. Existing project containers already occupy the host ports;
reuse them. Compose now requires private environment passwords; old development
defaults in Git history need coordinated rotation if reused.

Database provisioning must use a reviewed schema or export containing the required
workflow and Firebase changes. `database/schema.sql` drops the database;
`database/seed.sql` deletes existing rows. `database/schema_safe.sql` still creates
tables and is not a migration. Do not run these scripts against an existing dataset
to resolve startup failures. `database/create_demo_data.py` writes synthetic data
only to an empty, migrated database.

After a valid environment and reviewed existing schema are available, start the
complete local application with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

Use `scripts/check_health.ps1` and `scripts/stop_local.ps1` for managed health/stop.
Startup refuses existing consumers and unreviewed pending work; see
[DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for the explicit -ProcessPending option,
logs and all worker entry points. `run.py` remains a web-only development entry;
do not launch it on top of the managed server. No startup command creates or
migrates application tables.

## Application entry points

The source registers `/`, `/services`, `/login`, `/signup`, and `/get-connected`,
with role-specific pages under `/member`, `/organization`, and `/coordinator`.
The legacy request interface is `/demo/request`; its shared demo identity is
restricted to local debug/testing mode and disabled in hosted mode.

See [frontend integration](docs/frontend_integration.md) for route and template
contracts and [hosting](docs/hosting/HOSTING_RUNBOOK.md) for deployment prerequisites.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools/check_submission_readiness.py
docker compose -f compose.hosting.yml config --no-interpolate --quiet
```

The readiness tool defaults to source/configuration checks. Add `--database` or
`--rabbitmq` for read-only schema/mapping counts and passive topology checks once
services are available. It does not create accounts, queues, tables or migrations.
Browser email-delivery and actual participant testing remain separate from the
automated checks; record real outcomes in the checklist rather than assuming
that developer tests establish participant usability.

## Academic deliverables

`database/` retains the four ER diagram modules, logical database diagram,
`CareConnect_Normalization_608_checkin.pdf`, and numbered analytical queries.
SQL files retain their course and author attribution. A brief historical check-in
record is retained in the frontend integration guide; it is not current validation.
The [final logical mapping](docs/database/FINAL_LOGICAL_MAPPING.md) supplements the
older diagrams with Firebase UID, workflow constraints and the operational outbox.
The SQL inventory still has 206 qualifying families; the normalization report
documents dependencies and limitations rather than claiming every table is 3NF.

The owner applied migration 003 to the current live database and verified all
21 table fingerprints and 9/9 managed processes. The
[migration runbook](docs/database/REFERRAL_MIGRATION_RUNBOOK.md) is retained for
separate legacy installations and recovery.
