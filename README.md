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

### Requirements Artifact

- [System Requirements](docs/requirements/REQUIREMENTS.md)
- [User Stories](docs/requirements/USER_STORIES.md)
- [Use Case Diagram](docs/requirements/USE_CASE_DIAGRAM.jpg)

### Architecture Artifact

- [System Architecture](docs/SYSTEM_ARCHITECTURE.md)
- [Event-Driven Architecture](docs/EVENT_DRIVEN_ARCHITECTURE.md)

### Software Quality Artifact

- [Software Quality](docs/testing/SOFTWARE_QUALITY.md)
- [Final Test Report](docs/testing/FINAL_TEST_REPORT.md)
- [Event Workflow Test Report](docs/testing/EVENT_WORKFLOW_TEST_REPORT.md)
- [Test Suite](tests/)

### Implementation Artifact

- [Project Overview](docs/PROJECT_OVERVIEW.md)
- [Team Contributions](docs/TEAM_CONTRIBUTIONS.md)
- [AI Usage and References](docs/AI_USAGE_AND_REFERENCES.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [Demo Guide](docs/FINAL_DEMO_GUIDE.md)

### Database Documentation

- [Logical Database Mapping](docs/database/FINAL_LOGICAL_MAPPING.md)
- [Normalization Report](docs/testing/NORMALIZATION_REPORT.md)
- [Database Compliance Report](docs/testing/DATABASE_COMPLIANCE_REPORT.md)

### Final Submission

- [Submission Checklist](docs/FINAL_SUBMISSION_CHECKLIST.md)
