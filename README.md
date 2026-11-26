# CareConnect

CareConnect is a community wellness referral and follow-up system developed by Group 4 for ENSF 607 and ENSF 608 at the University of Calgary. It connects people with organizations that provide non-medical community support.

**Live application:** https://careconnect-group4.westus2.cloudapp.azure.com

## What it does

- Members find services, submit requests, track progress and give feedback.
- Organizations manage services, respond to referrals and record attendance and completion.
- Coordinators approve organizations, monitor requests and help resolve unmatched requests.

The system automatically looks for backup organizations when a referral is rejected or expires. CareConnect is not an emergency or medical service.

## Technology

| Tool | Purpose |
|---|---|
| Flask and Python | Application and business logic |
| MySQL | Store application data |
| RabbitMQ | Send events between background workers |
| Firebase | Login and email verification |
| HTML, CSS, JavaScript, Bootstrap | User interface |
| Docker, Azure, Caddy | Hosting and HTTPS |

## Run locally

Use Python 3.12 and Docker Desktop. From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For a new setup, copy `.env.example` to `.env` and obtain the approved private configuration from the team. Reuse existing database and broker containers when available. A compatible database must already be prepared.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

Open http://127.0.0.1:5000. See [deployment guide](docs/DEPLOYMENT_GUIDE.md) for setup, health checks and shutdown. Never run reset or seed scripts on an existing database.

## Documentation

- [Project overview](docs/PROJECT_OVERVIEW.md)
- [Requirements](docs/REQUIREMENTS.md)
- [System architecture](docs/SYSTEM_ARCHITECTURE.md)
- [Event-driven architecture](docs/EVENT_DRIVEN_ARCHITECTURE.md)
- [Database mapping](docs/database/FINAL_LOGICAL_MAPPING.md)
- [Final test report](docs/testing/FINAL_TEST_REPORT.md)
- [Demo guide](docs/FINAL_DEMO_GUIDE.md)
- [Submission checklist](docs/FINAL_SUBMISSION_CHECKLIST.md)

The final automated checks recorded 112 regression tests, 12 separate integration tests and 97 browser checks. The application is hosted on Azure; the team owner confirmed all three demo roles can log in. Use synthetic data and keep credentials private.
