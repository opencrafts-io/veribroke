import json
import pika
from retry import retry
import threading

from payments.utils import make_mpesa_stk
from veribroke import settings

# STKPUSH_ROUTING_KEY = 'veribroke.mpesa-stk'


class PaymentListener(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        creds = pika.PlainCredentials(
            settings.env("RABBITMQ_USER"),
            settings.env("RABBITMQ_PASSWORD"),
        )
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=settings.env("RABBITMQ_HOST"),
                port=settings.env("RABBITMQ_PORT"),
                credentials=creds,
            ),
        )
        self.channel = connection.channel()
        self.channel.exchange_declare(
            exchange=settings.env("RABBITMQ_EXCHANGE"),
            exchange_type='direct',
        )
        self.channel.queue_declare(
            queue=settings.env("RABBITMQ_QUEUE"),
            durable=True,
        )
        self.channel.queue_bind(
            queue=settings.env("RABBITMQ_QUEUE"),
            exchange=settings.env("RABBITMQ_EXCHANGE"),
            routing_key=settings.env("RABBITMQ_STKPUSH_ROUTING_KEY"),
        )
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue=settings.env("RABBITMQ_QUEUE"),
            on_message_callback=self.callback,
        )
    
    @retry(pika.exceptions.AMQPConnectionError, delay=5, jitter=(1, 3))
    def __start_con(self):
        """
        Used to start connections for rabbit mq
        """
        try:
            self.channel.start_consuming()
        # Don't recover connections closed by server
        except pika.exceptions.ConnectionClosedByBroker:
            print("Got here")
            pass
        
        
    def callback(self, channel, method, properties, body):
        print("And here")
        message = json.loads(body)
        print(message)
        returned = make_mpesa_stk(message)
        print("from returning")
        print(returned)
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        print ('Inside LogginService:  Created Listener ')
        self.__start_con()
        