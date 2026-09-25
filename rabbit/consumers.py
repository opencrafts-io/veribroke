from retry import retry
from veribroke import settings

from typing import Any, Callable, Optional

import json
import logging
import pika
import threading

from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

logger = logging.getLogger(__name__)

# cons_func(request_body) -> (success, message, errors, metadata)
ConsumerFunc = Callable[[dict[str, Any]], tuple[bool, str, Any, dict[str, Any]]]

# How many times a message is redelivered to the main queue before it's
# given up on and parked in the failed queue for manual inspection.
MAX_DELIVERY_ATTEMPTS = 3

# How long a failed message waits in the retry queue before it's
# dead-lettered back into the main queue for reprocessing.
RETRY_TTL_MS = 30000


class ConsumerListener(threading.Thread):
    Consumers: dict[str, "ConsumerListener"] = dict()

    def __init__(
        self,
        channel: BlockingChannel,
        exchange: str,
        queue_name: str,
        routing_key: str,
        cons_func: ConsumerFunc,
        notifies: bool = False,
    ) -> None:
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
        self.retry_routing_key = f"{routing_key}.retry"
        self.retry_queue_name = f"{queue_name}.retry"
        self.failed_queue_name = f"{queue_name}.failed"
        self.notify = notifies

        # A failed message is nacked (requeue=False) straight to the
        # retry queue via this DLX -- no manual republishing needed.
        self.channel.queue_declare(
            queue=self.queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": exchange,
                "x-dead-letter-routing-key": self.retry_routing_key,
            },
        )
        self.channel.queue_bind(
            queue=self.queue_name,
            exchange=exchange,
            routing_key=routing_key,
        )

        # Parks nacked messages for RETRY_TTL_MS, then dead-letters them
        # back to the main queue for reprocessing -- a passive delay
        # buffer, no consumer attached.
        self.channel.queue_declare(
            queue=self.retry_queue_name,
            durable=True,
            arguments={
                "x-message-ttl": RETRY_TTL_MS,
                "x-dead-letter-exchange": exchange,
                "x-dead-letter-routing-key": routing_key,
            },
        )
        self.channel.queue_bind(
            queue=self.retry_queue_name,
            exchange=exchange,
            routing_key=self.retry_routing_key,
        )

        # Terminal holding queue for messages that exhausted their
        # retries, for manual inspection. We publish here directly
        # (rather than via nack) since it's the one routing decision
        # RabbitMQ's static per-queue DLX config can't express.
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
    def __start_con(self) -> None:
        """
        Used to start connections for rabbit mq
        """
        try:
            self.channel.start_consuming()
        # Don't recover connections closed by server
        except pika.exceptions.ConnectionClosedByBroker:
            logger.warning(
                "connection closed by broker",
                extra={"queue_name": self.queue_name},
            )

    def _delivery_attempts(self, headers: Optional[dict[str, Any]]) -> int:
        """
        How many times this message has already been dead-lettered from
        the main queue back into the retry cycle (native x-death count).
        """
        for death in (headers or {}).get("x-death", []) or []:
            if death.get("queue") == self.queue_name:
                return death.get("count", 0)
        return 0

    def _send_to_failed(self, body: bytes, headers: Optional[dict[str, Any]]) -> None:
        self.channel.basic_publish(
            exchange="",
            routing_key=self.failed_queue_name,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                headers=headers,
            ),
        )

    def _notify_failure(
        self,
        request_id: Optional[str],
        reply_to: Optional[str],
        message: Optional[str],
        errors: Any,
        metadata: Optional[dict[str, Any]],
    ) -> None:
        if not (self.notify and reply_to):
            return
        self.channel.basic_publish(
            exchange=settings.env("RABBITMQ_NOTIFICATION_EXCHANGE"),
            routing_key=reply_to,
            body=json.dumps(
                {
                    "request_id": request_id,
                    "success": False,
                    "message": message,
                    "errors": errors,
                    "metadata": metadata,
                }
            ),
            properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent),
        )

    def callback(
        self,
        channel: BlockingChannel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ) -> None:
        headers = properties.headers or {}

        try:
            request_body = json.loads(body)
        except (TypeError, ValueError):
            # Unretryable: the bytes won't parse any differently next
            # time, so skip straight to the failed queue.
            logger.error(
                "unparseable message, sending to failed queue",
                extra={
                    "queue_name": self.queue_name,
                    "failed_queue": self.failed_queue_name,
                },
            )
            self._send_to_failed(body, headers)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        reply_to = request_body.get("reply_to")
        request_id = request_body.get("request_id")

        try:
            success, message, errors, metadata = self.cons_func(request_body)
        except Exception:
            attempt = self._delivery_attempts(headers) + 1
            logger.exception(
                "unhandled error processing message",
                extra={
                    "request_id": request_id,
                    "queue_name": self.queue_name,
                    "attempt": attempt,
                },
            )
            if attempt >= MAX_DELIVERY_ATTEMPTS:
                self._send_to_failed(body, headers)
                self._notify_failure(
                    request_id,
                    reply_to,
                    "processing failed after retries",
                    None,
                    {},
                )
                channel.basic_ack(delivery_tag=method.delivery_tag)
            else:
                # Nack straight to the retry queue via the main queue's
                # DLX -- RabbitMQ handles the routing, no manual
                # republish needed.
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        logger.info(
            "message processed",
            extra={
                "request_id": request_id,
                "queue_name": self.queue_name,
                "success": success,
                "result_message": message,
            },
        )

        if not success:
            self._notify_failure(request_id, reply_to, message, errors, metadata)

        channel.basic_ack(delivery_tag=method.delivery_tag)

    def run(self) -> None:
        logger.info("started listener", extra={"queue_name": self.queue_name})
        self.__start_con()
