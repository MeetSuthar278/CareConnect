
import json
import logging

import pika

from app.messaging.rabbitmq_connection import get_rabbitmq_connection
from app.messaging.rabbitmq_config import QUEUE_BINDINGS


logger = logging.getLogger(__name__)


def consume_events(queue_name, handler):
    """
    Consume events from a RabbitMQ queue.

    handler(event) processes the received event.
    """

    if queue_name not in QUEUE_BINDINGS:
        raise ValueError(f"Unknown queue: {queue_name}")

    connection = get_rabbitmq_connection()

    try:
        channel = connection.channel()

        # Require queue to already exist (Task 5).
        channel.queue_declare(
            queue=queue_name,
            passive=True,
        )

        channel.basic_qos(prefetch_count=1)

        def callback(ch, method, properties, body):
            try:
                event = json.loads(body.decode("utf-8"))

                if not isinstance(event, dict):
                    raise ValueError("Event must be a JSON object")

                required = {
                    "event_id",
                    "event_type",
                    "event_version",
                    "timestamp",
                    "request_id",
                    "payload",
                }

                if not required.issubset(event):
                    raise ValueError("Missing required event fields")

                if not isinstance(event["payload"], dict):
                    raise ValueError("Invalid event payload")

                if type(event["request_id"]) is not int or event["request_id"] <= 0:
                    raise ValueError("Invalid request_id")
                if type(event["event_version"]) is not int or event["event_version"] != 1:
                    raise ValueError("Unsupported event version")
                if not isinstance(event["event_id"], str) or not event["event_id"]:
                    raise ValueError("Invalid event_id")

                # Handler errors are processing failures, not malformed envelopes.
                try:
                    handler(event)
                except Exception as error:
                    raise RuntimeError("Business processing failed") from error

                # Acknowledge only after successful processing.
                ch.basic_ack(
                    delivery_tag=method.delivery_tag
                )

            except (ValueError, UnicodeDecodeError) as error:
                logger.error("Invalid event: %s", error)

                # Discard malformed messages to avoid infinite retries.
                ch.basic_reject(
                    delivery_tag=method.delivery_tag,
                    requeue=False,
                )

            except Exception:
                logger.exception("Event processing failed")

                # Preserve failed work and reconnect with backoff in worker_runtime.
                ch.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=True,
                )
                raise

        channel.basic_consume(
            queue=queue_name,
            on_message_callback=callback,
            auto_ack=False,
        )

        print(f"Listening on {queue_name}...")
        channel.start_consuming()

    except KeyboardInterrupt:
        print("Consumer stopped.")

    finally:
        if connection.is_open:
            connection.close()