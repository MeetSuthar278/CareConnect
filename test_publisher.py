
from app.messaging.event_publisher import publish_event

publish_event(
    event_type="ServiceRequestCreated",
    request_id=101,
    payload={
        "member_id": 12,
        "service_id": 3,
        "area_id": 2,
        "priority": "High",
        "attendance_deadline": "2026-10-26T22:00:00Z"
    }
)
