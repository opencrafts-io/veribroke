from retry import retry
from veribroke import settings

from pika.adapters.blocking_connection import BlockingChannel

import pika


class RabbitSetup():
    def __init__(self) -> None:
        creds = pika.PlainCredentials(
            settings.env("RABBITMQ_USER"),
            settings.env("RABBITMQ_PASSWORD"),
        )
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=settings.env("RABBITMQ_HOST"),
                port=settings.env.int("RABBITMQ_PORT"),
                credentials=creds,
            ),
        )
        self.channel: BlockingChannel = connection.channel()

    def declare_default_exchanges(self) -> None:
        """
        Used to declare the default exchanges for the app
        """
        # direct exchange
        self.channel.exchange_declare(
            exchange=settings.env("RABBITMQ_EXCHANGE"),
            durable=True,
            exchange_type='direct',
        )
        # notifications exchange
        self.channel.exchange_declare(
            exchange=settings.env("RABBITMQ_NOTIFICATION_EXCHANGE"),
             durable=True,
            exchange_type='topic',
        )
    
    def publish_message(
            self,
            exchange: str,
            routing_key: str,
            body: str | bytes,
            persist: bool,
        ) -> None:
        """
        Will Publish Message To RabbitMQ

        :param exchange: the exchange to publish the message to
        :param routing_key: the routing key to use to publish the message to
        :param body: the body to send
        :param persist: whether to persist the message sent to the queue
        """
        delivery_mode = pika.DeliveryMode.Persistent if persist else pika.DeliveryMode.Transient
        self.channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=delivery_mode,
            )
        )

    def close(self) -> None:
        """
        Used to close the connection for rabbitmq
        """
        self.channel.close()