
from app.messaging.rabbitmq_connection import rabbitmq_channel


def test_connection():
    with rabbitmq_channel() as channel:
        result = channel.queue_declare(
            queue="matching_queue",
            passive=True
        )

        print("RabbitMQ connection successful!")
        print("Queue:", result.method.queue)
        print("Messages waiting:", result.method.message_count)


if __name__ == "__main__":
    test_connection()
