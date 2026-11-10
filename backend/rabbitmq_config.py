
import os
import pika

EXCHANGE_NAME = "careconnect.events"

QUEUE_BINDINGS = {
    "matching_queue": [
        "request.created",
        "referral.rejected",
        "referral.timeout",
    ],
    "notification_queue": [
        "referral.created",
    ],
    "sla_queue": [
        "request.attended",
    ],
    "coordinator_queue": [
        "attendance.overdue",
    ],
    "feedback_queue": [
        "feedback.submitted",
    ],
}


def setup_rabbitmq():
    credentials = pika.PlainCredentials(
        os.getenv("RABBITMQ_USER", "guest"),
        os.environ["RABBITMQ_PASSWORD"],
    )

    parameters = pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )

    connection = pika.BlockingConnection(parameters)

    try:
        channel = connection.channel()

        # Create one durable topic exchange
        channel.exchange_declare(
            exchange=EXCHANGE_NAME,
            exchange_type="topic",
            durable=True,
        )

        # Create durable queues and routing bindings
        for queue_name, routing_keys in QUEUE_BINDINGS.items():
            channel.queue_declare(
                queue=queue_name,
                durable=True,
            )

            for routing_key in routing_keys:
                channel.queue_bind(
                    exchange=EXCHANGE_NAME,
                    queue=queue_name,
                    routing_key=routing_key,
                )

                print(
                    f"{routing_key} -> {queue_name}"
                )

        print("CareConnect RabbitMQ configuration completed!")

    finally:
        connection.close()


if __name__ == "__main__":
    setup_rabbitmq()
