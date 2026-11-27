# System architecture

CareConnect uses a web application with separate background workers.

```mermaid
flowchart LR
 U[Browser] --> F[Flask application]
 U --> A[Firebase authentication]
 F --> D[(MySQL)]
 D --> O[Outbox dispatcher]
 O --> R[RabbitMQ]
 R --> W[Background workers]
 W --> D
 T[Deadline checkers] --> D
```

| Component | Responsibility |
|---|---|
| Frontend | Forms, dashboards and request tracking |
| Flask | Validates requests, checks permissions and handles business actions |
| Firebase | Verifies user identity |
| MySQL | Stores users, organizations, requests, referrals and events |
| Outbox dispatcher | Publishes saved events to RabbitMQ |
| Workers | Handle matching, notifications, deadlines and feedback |
| Deadline checkers | Find expired response and attendance deadlines |

The hosted version runs in Docker on Azure. Caddy provides HTTPS. The database and message broker are not exposed directly to the internet.

See [event architecture](EVENT_DRIVEN_ARCHITECTURE.md) for the seven implemented events.

## System Architecture Diagram

![System Architecture](architecture/SYSTEM_ARCHITECTURE.jpg)

[Editable Draw.io Diagram](architecture/SYSTEM_ARCHITECTURE.drawio)
