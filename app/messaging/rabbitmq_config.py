
import os
import pika
from pika.exceptions import AMQPConnectionError, ProbableAuthenticationError

# RabbitMQ configuration
EXCHANGE_NAME = "careconnect.events"

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5673"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "careconnect")
RABBITMQ_PASSWORD = os.environ["RABBITMQ_PASSWORD"]

# Event routing configuration
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
    print("\n--- CareConnect RabbitMQ Setup ---")
    print(f"Host: {RABBITMQ_HOST}")
    print(f"Port: {RABBITMQ_PORT}")
    print(f"Username: {RABBITMQ_USER}")

    credentials = pika.PlainCredentials(
        RABBITMQ_USER,
        RABBITMQ_PASSWORD,
    )

    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host="/",
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
        connection_attempts=3,
        retry_delay=2,
    )

    connection = None

    try:
        print("\nConnecting to RabbitMQ...")

        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        print("Connected successfully!")

        # Declare durable topic exchange
        channel.exchange_declare(
            exchange=EXCHANGE_NAME,
            exchange_type="topic",
            durable=True,
        )

        print(f"Exchange created: {EXCHANGE_NAME}")

        # Declare durable queues and bindings
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

                print(f"{routing_key} -> {queue_name}")

        print("\nCareConnect RabbitMQ configuration completed!")

    except ProbableAuthenticationError:
        print("\nERROR: RabbitMQ authentication failed.")
        print("Check the username, password, and broker port.")
        raise

    except AMQPConnectionError as error:
        print(f"\nERROR: Cannot connect to RabbitMQ: {error}")
        print("Check whether the RabbitMQ container is running.")
        raise

    except Exception as error:
        print(f"\nRabbitMQ setup failed: {error}")
        raise

    finally:
        if connection is not None and connection.is_open:
            connection.close()
            print("RabbitMQ connection closed.")


if __name__ == "__main__":
    setup_rabbitmq()
