from retry import retry
from veribroke import settings

import json
import logging
import pika
import threading

logger = logging.getLogger(__name__)

# How many times a message is redelivered to the main queue before it's
# given up on and parked in the failed queue for manual inspection.
MAX_DELIVERY_ATTEMPTS = 3

# How long a failed message waits in the retry queue before it's
# dead-lettered back into the main exchange for reprocessing.
RETRY_TTL_MS = 30000

# Header we manage ourselves to count delivery attempts across the
# retry cycle. Not RabbitMQ's native x-death, because that would require
# declaring x-dead-letter-exchange on the *main* queue -- and that queue
# already exists in production without that argument, so redeclaring it
# with new arguments would raise PRECONDITION_FAILED and crash the
# consumer on startup. Routing through app-managed retry/failed queues
# avoids touching the main queue's declaration at all.
ATTEMPT_HEADER = "x-veribroke-attempt"


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
        self.exchange = exchange
        self.routing_key = routing_key
        self.cons_func = cons_func
        self.queue_name = queue_name
        self.retry_queue_name = f"{queue_name}.retry"
        self.failed_queue_name = f"{queue_name}.failed"
        self.notify = notifies

        # Unchanged from before: must stay byte-identical to how this
        # queue is already declared in production, or a redeclare with
        # different arguments raises PRECONDITION_FAILED.
        self.channel.queue_declare(
            queue=self.queue_name,
            durable=True,
        )
        self.channel.queue_bind(
            queue=self.queue_name,
            exchange=exchange,
            routing_key=routing_key,
        )

        # Brand new queues -- safe to declare with whatever arguments we
        # want, nothing pre-existing to conflict with.
        self.channel.queue_declare(
            queue=self.retry_queue_name,
            durable=True,
            arguments={
                "x-message-ttl": RETRY_TTL_MS,
                "x-dead-letter-exchange": exchange,
                "x-dead-letter-routing-key": routing_key,
            },
        )
        self.channel.queue_declare(
            queue=self.failed_queue_name,
            durable=True,
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
            logger.warning("Connection closed by broker for %s", self.queue_name)

    def _requeue_for_retry(self, body, headers, attempt):
        headers = dict(headers or {})
        headers[ATTEMPT_HEADER] = attempt
        self.channel.basic_publish(
            exchange="",
            routing_key=self.retry_queue_name,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                headers=headers,
            ),
        )

    def _send_to_failed(self, body, headers):
        self.channel.basic_publish(
            exchange="",
            routing_key=self.failed_queue_name,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                headers=headers,
            ),
        )

    def _notify_failure(self, request_id, reply_to, message, errors, metadata):
        if not (self.notify and reply_to):
            return
        self.channel.basic_publish(
            exchange=settings.env("RABBITMQ_NOTIFICATION_EXCHANGE"),
            routing_key=reply_to,
            body=json.dumps({
                "request_id": request_id,
                "success": False,
                "message": message,
                "errors": errors,
                "metadata": metadata,
            }),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent
            ),
        )

    def callback(self, channel, method, properties, body):
        headers = properties.headers or {}
        attempt = headers.get(ATTEMPT_HEADER, 0)

        try:
            request_body = json.loads(body)
        except (TypeError, ValueError):
            logger.error(
                "Unparseable message on %s, sending to failed queue",
                self.queue_name,
            )
            self._send_to_failed(body, headers)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        reply_to = request_body.get('reply_to')
        request_id = request_body.get('request_id')

        try:
            success, message, errors, metadata = self.cons_func(request_body)
        except Exception:
            logger.exception(
                "Unhandled error processing %s on %s (attempt %s)",
                request_id, self.queue_name, attempt + 1,
            )
            if attempt + 1 >= MAX_DELIVERY_ATTEMPTS:
                self._send_to_failed(body, headers)
                self._notify_failure(
                    request_id, reply_to,
                    "processing failed after retries", None, {},
                )
            else:
                self._requeue_for_retry(body, headers, attempt + 1)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        logger.info(
            "Processed %s on %s: success=%s message=%s",
            request_id, self.queue_name, success, message,
        )

        if not success:
            self._notify_failure(request_id, reply_to, message, errors, metadata)

        channel.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        logger.info("Started listener for: %s", self.queue_name)
        self.__start_con()
