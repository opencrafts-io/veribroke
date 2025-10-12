import json
import pika
from retry import retry
import threading

from payments.utils import make_mpesa_stk

STKPUSH_ROUTING_KEY = 'veribroke.mpesa-stk'
EXCHANGE = 'io.opencrafts.veribroke'
QUEUE = 'veribroke.mpesa-stk'


class PaymentListener(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host='localhost'),
        )
        self.channel = connection.channel()
        self.channel.exchange_declare(
            exchange=EXCHANGE,
            exchange_type='direct',
        )
        self.channel.queue_declare(
            queue=QUEUE,
            durable=True,
        )
        self.channel.queue_bind(
            queue=QUEUE,
            exchange=EXCHANGE,
            routing_key=STKPUSH_ROUTING_KEY,
        )
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue=QUEUE,
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
        