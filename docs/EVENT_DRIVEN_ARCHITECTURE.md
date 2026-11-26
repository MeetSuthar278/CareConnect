# Event-driven architecture

An event tells the system that something important has happened. RabbitMQ delivers events to background workers so that the web application does not have to complete all follow-up work during a user request.

| Event | Producer | Consumer | Result |
|---|---|---|---|
| ServiceRequestCreated | Request service | Matching worker | Finds a partner and creates a referral |
| ReferralCreated | Matching service | Notification worker | Notifies the organization |
| ReferralRejected | Referral service | Matching worker | Tries another eligible partner |
| AcceptanceTimedOut | Response deadline checker | Matching worker | Tries a backup or escalates |
| RequestAttended | Attendance service | SLA worker | Checks whether attendance was on time |
| AttendanceOverdue | Attendance deadline checker | Coordinator worker | Alerts coordinators |
| FeedbackSubmitted | Feedback service | Feedback worker | Notifies the partner; alerts coordinators for negative feedback |

## Example workflow

1. A member submits a request.
2. MySQL saves the request and event together in the outbox.
3. The dispatcher publishes the event to RabbitMQ.
4. The matching worker selects an approved partner with the right service, area, time frame and available capacity.
5. The notification worker alerts the organization.
6. If rejected or timed out, matching tries a different partner, up to three attempts. Unresolved requests are escalated.

The durable `careconnect.events` exchange routes messages to five queues. Events may be delivered more than once, so workers check existing records to avoid duplicate effects. Acceptance and completion are direct database actions, not separate RabbitMQ events.

See [workflow test evidence](testing/EVENT_WORKFLOW_TEST_REPORT.md).

## Event-Driven Architecture Diagram

![Event-Driven Architecture](architecture/EVENT_DRIVEN_ARCHITECTURE.jpeg)

[Editable Draw.io Diagram](architecture/EVENT_DRIVEN_ARCHITECTURE.drawio)
