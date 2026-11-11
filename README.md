> Current frontend update: `/` serves the latest team landing page; `/get-connected` serves the
> latest team request form and its session-owned confirmation. The earlier demo is preserved at
> `/demo/request`. See `docs/testing/ServiceRequestCreated_TEST_GUIDE.md` for the current form flow.
> The notes below include earlier verification history; the new path does not reuse demo member 9.

# CareConnect

Community wellness referrals for ENSF 607/608, University of Calgary; SDG 17.
Local synthetic demo only. CareConnect provides non-medical referrals, not emergency assistance.

## Open the frontend

The working Flask application serves the request interface at **http://127.0.0.1:5000/**
and **http://127.0.0.1:5000/get-connected**. There is no separate frontend server or build.
Restart Flask if an older process still serves the previous JSON home response.

The interface reuses the existing CareConnect shared layout, footer and stylesheet from
origin/main, adapting navigation and replacing its placeholder request form. Bootstrap 5.3.3
CSS is stored locally with its license header, so no CDN is required during the demonstration.
No React, Vue, Node runtime or frontend build pipeline is required.

## Start locally (Windows Command Prompt)

Keep Docker Desktop running. Preserve .env credentials. The provided Compose mapping uses
MySQL at 127.0.0.1:3307 and RabbitMQ at 127.0.0.1:5673 for host-run Python processes.
The baseline, migration 001 and synthetic dataset have already been provisioned on the
local database used for verification. Do not rerun schema.sql, seed.sql or initialization.
A new environment needs separate database provisioning; see database/migrations/001_checkin_workflow.sql.

```cmd
.\.venv\python.exe -m pip install -r requirements.txt
docker compose up -d mysql rabbitmq
set RABBITMQ_PORT=5673
.\.venv\python.exe -m app.messaging.rabbitmq_config
```

Run each process in its own terminal from the repository root:

```cmd
REM Terminal 1: Flask frontend and API
.\.venv\python.exe run.py
```

```cmd
REM Terminal 2: matching
set RABBITMQ_PORT=5673
.\.venv\python.exe worker.py
```

```cmd
REM Terminal 3: organization notifications
set RABBITMQ_PORT=5673
.\.venv\python.exe notification_worker.py
```

```cmd
REM Terminal 4: outgoing event dispatcher
set RABBITMQ_PORT=5673
.\.venv\python.exe outbox_dispatcher.py
```

Open http://127.0.0.1:5000/. run.py enables the existing local demo member 9 via debug mode.
Without debug/testing mode, the page shows a disabled preview because authentication is unfinished.
Do not run test_consumer.py: it competes for matching messages without creating referrals.

## Frontend integration

- GET /api/services, /api/service-areas and /api/priorities populate the form with actual IDs.
- POST /api/requests sends service_id, service_area_id, priority_id, title and description.
- Successful submission displays the returned ID and initial status.
- GET /api/requests/<id> polls about every two seconds for up to two minutes.
- Matched/unmatched and other non-pending states stop automatic polling. Manual refresh stays available.
- The tab remembers its latest request ID in sessionStorage; reload retrieves it without another POST.
- Fields disable during submission and remain locked after success. Start another request is explicit.
- Network/validation/catalog failures are shown without automatically retrying POST.
- An ambiguous POST failure may still have saved data. Check /api/requests before choosing to submit again.

The API does not return the selected organization or notification state. The UI therefore does not
invent partner names or claim notification delivery. Its architecture section is explanatory only.
Notification delivery is verified with the read-only SQL queries in the runbook.

## 60-second check-in demonstration

1. Open the page and point out Demo Mode and the non-medical notice (10 seconds).
2. Select service, area and priority; enter a synthetic title/description and submit once (15 seconds).
3. Show the returned ID, initial Submitted status and real polling transition to Matched (15 seconds).
4. Show the workflow explanation and dispatcher events (10 seconds).
5. Show the stored referral/notification using runbook SQL, or saved live evidence (10 seconds).

Each new request reserves capacity. Capacity release is not implemented, so avoid unnecessary repeated
submissions; a full partner pool correctly produces Unmatched. Never reset data for a rehearsal.

## Tests and observed verification

```cmd
.\.venv\python.exe -B -m pytest -p no:cacheprovider -q
```

The 26 original backend tests use isolated in-memory SQL and mocked transport. Browser tests are
optional and require Playwright plus installed Microsoft Edge:

```cmd
.\.venv\python.exe -m pip install -r requirements-browser.txt
.\.venv\python.exe -B -m pytest tests/test_frontend.py -p no:cacheprovider -q
```

Browser tests run a temporary Flask server with an in-memory DATABASE_URL and intercept API calls.
They do not write to live MySQL. Missing Playwright skips them; an installed Playwright with missing
Edge must be supplied with Edge before running them. The runtime application does not require Playwright.
See docs/testing/frontend/verification.md for the observed final results and screenshots.

A separate real browser verification submitted synthetic request 3 through Flask, MySQL and RabbitMQ:
it matched, created one referral, published both events and stored the representative notification.
One POST was observed; polling/manual refresh created no duplicates. Existing requests 1 and 2 remained.

## Backend adjustments and limitations

The only backend change for frontend integration is rendering the request template at / and
/get-connected. The existing APIs, workers, matching logic, tables and migrations are unchanged.
/health and /health/db retain their existing JSON responses.

Authentication, acceptance/rejection, backups, attendance/completion, capacity release and a notification
UI remain outside this implementation. The demo identity is shared; do not use real personal data.
The browser prevents duplicate clicks, but there is no HTTP idempotency key across tabs or ambiguous
manual retries. Polling stops after two minutes; worker outages leave a truthful Submitted status.
The live happy path does not prove MySQL concurrent-worker or crash-recovery correctness.
All work remains local and uncommitted; no Git staging, commits, branches or pushes were performed.

## Further documentation

- CHECKIN_PROGRESS.md: previous backend work and original check-in evidence.
- docs/testing/checkin_runbook.md: process commands and SQL verification queries.
- docs/testing/checkin_test_results.md: original 26-test evidence.
- docs/testing/frontend/: current frontend screenshots and live verification evidence.


## Latest team login (separate integration phase)

Open http://127.0.0.1:5000/login to use the latest teammate login design.
It uses frontend/templates and /team-static assets; the earlier demo request UI remains at /.
Login now connects Firebase email/password to the existing /api/auth/me backend.
No role-dashboard redirect, signup handler or server-session integration is claimed.
See docs/testing/FIREBASE_LOGIN_TEST_GUIDE.md for prerequisites, commands and local checks.
