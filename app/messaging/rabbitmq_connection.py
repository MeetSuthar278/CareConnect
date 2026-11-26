
import os
import pika
from contextlib import contextmanager


def get_rabbitmq_connection():
    """Create a connection to the RabbitMQ broker."""

    credentials = pika.PlainCredentials(
        os.getenv("RABBITMQ_USER", "careconnect"),
        os.environ["RABBITMQ_PASSWORD"]
    )

    parameters = pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", "5673")),
        virtual_host=os.getenv("RABBITMQ_VHOST", "/"),
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
        connection_attempts=3,
        retry_delay=2
    )

    return pika.BlockingConnection(parameters)


@contextmanager
def rabbitmq_channel():
    """Provide a channel and close the connection afterward."""

    connection = get_rabbitmq_connection()

    try:
        channel = connection.channel()
        yield channel
    finally:
        if connection.is_open:
            connection.close()
