import pika
import os
from dotenv import load_dotenv

load_dotenv()
credentials = pika.PlainCredentials(
    os.getenv("RABBITMQ_USER", "careconnect"),
    os.environ["RABBITMQ_PASSWORD"],
)
parameters = pika.ConnectionParameters(
    host='localhost',
    port=5673,  # Update this to match your active port if it changed from 5672
    credentials=credentials
)

connection = pika.BlockingConnection(parameters)
print("CareConnect: RabbitMQ connected successfully!")
connection.close()