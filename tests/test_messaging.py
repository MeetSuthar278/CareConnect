"""Transport contract tests with mocked RabbitMQ; no network connections."""
import json
from unittest.mock import MagicMock, patch
import pytest
from app.messaging.event_consumer import consume_events
from app.messaging.event_publisher import publish_event


@pytest.mark.parametrize("failure", [False, True])
def test_ack_only_after_handler_success(failure):
    connection = MagicMock()
    channel = connection.channel.return_value
    handler = MagicMock(side_effect=ValueError("database processing failed") if failure else None)
    event = {"event_id":"fixed", "event_type":"ServiceRequestCreated", "event_version":1,
             "timestamp":"2026-10-27T12:00:00Z", "request_id":1,"payload":{}}
    def register(**kwargs):
        def deliver():
            kwargs["on_message_callback"](channel, MagicMock(delivery_tag=7), None, json.dumps(event).encode())
        channel.start_consuming.side_effect = deliver
    channel.basic_consume.side_effect = register
    with patch("app.messaging.event_consumer.get_rabbitmq_connection", return_value=connection):
        if failure:
            with pytest.raises(RuntimeError):
                consume_events("matching_queue", handler)
            channel.basic_ack.assert_not_called()
            channel.basic_nack.assert_called_once_with(delivery_tag=7, requeue=True)
        else:
            consume_events("matching_queue", handler)
            channel.basic_ack.assert_called_once_with(delivery_tag=7)
            channel.basic_nack.assert_not_called()
    handler.assert_called_once()


def test_publish_preserves_id_and_requests_confirmation():
    with patch("app.messaging.event_publisher.rabbitmq_channel") as context:
        channel = context.return_value.__enter__.return_value
        result = publish_event("ReferralCreated", 1, {"referral_id":2},
                               event_id="fixed", timestamp="2026-10-27T12:00:00Z")
    assert result["event_id"] == "fixed"
    channel.confirm_delivery.assert_called_once()
    sent = channel.basic_publish.call_args.kwargs
    assert sent["mandatory"] is True
    assert sent["properties"].message_id == "fixed"
    assert sent["properties"].delivery_mode == 2
