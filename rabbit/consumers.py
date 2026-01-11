from retry import retry
from veribroke import settings

import json
import pika
import threading


class ConsumerListener(threading.Thread):
    Consumers = dict()

    def __init__(
            self,
            channel,
            exchange,
            queue_name,
            routing_key,
            cons_func,
            notifies=False
        ):
        """
        Initializes an object that declares a queue, binds it to an exchange
        
        :param channel: Pika Channel containing info on how to reach rabbit
        :param exchange: exchange to bind queue
        :param queue_name: queue_name
        :param routing_key: the routing key to use
        :param callback: the function that will be called when queue is being called
        :param notifies: states whether this queue will be sending notifications to other services
        """
        threading.Thread.__init__(self)
        self.channel = channel
        self.cons_func = cons_func
        self.queue_name = queue_name
        self.notify = notifies

        self.channel.queue_declare(
            queue=self.queue_name,
            durable=True,
        )
        self.channel.queue_bind(
            queue=self.queue_name,
            exchange=exchange,
            routing_key=routing_key,
        )
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self.callback,
        )

        # store all consumers
        ConsumerListener.Consumers[self.queue_name] = self
    
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
        print("called")
        request_body = json.loads(body)
        reply_to = request_body.get('reply_to')
        success, message, errors, metadata =  self.cons_func(request_body)
        print(success)
        print(message)
        print(errors)
        if (self.notify and not success and reply_to):
            # sends notifications
            self.channel.basic_publish(
                exchange=settings.env("RABBITMQ_NOTIFICATION_EXCHANGE"),
                routing_key=reply_to,
                body=json.dumps({
                    "request_id": request_body['request_id'],
                    "success": success,
                    "message": message,
                    "errors": errors,
                    "metadata": metadata
                },),
                properties=pika.BasicProperties(
                    delivery_mode = pika.DeliveryMode.Persistent
                )
            )
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        print (f'Started Listener for: {self.queue_name}')
        self.__start_con()