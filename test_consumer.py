
from app.messaging.event_consumer import consume_events


def handle_event(event):
    print("Event received:", event["event_type"])
    print("Request ID:", event["request_id"])
    print("Payload:", event["payload"])


if __name__ == "__main__":
    consume_events("matching_queue", handle_event)
