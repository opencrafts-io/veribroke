import json
from unittest.mock import MagicMock

from django.test import TestCase

from rabbit.consumers import ATTEMPT_HEADER
from rabbit.consumers import MAX_DELIVERY_ATTEMPTS
from rabbit.consumers import ConsumerListener


def _method(delivery_tag=1):
    method = MagicMock()
    method.delivery_tag = delivery_tag
    return method


def _properties(headers=None):
    properties = MagicMock()
    properties.headers = headers
    return properties


class ConsumerListenerCallbackTests(TestCase):
    def _make_listener(self, cons_func, queue_name="veribroke.test-queue", notifies=True):
        channel = MagicMock()
        listener = ConsumerListener(
            channel=channel,
            exchange="io.opencrafts.veribroke",
            queue_name=queue_name,
            routing_key=queue_name,
            cons_func=cons_func,
            notifies=notifies,
        )
        return listener, channel

    def test_declares_retry_and_failed_queues_without_touching_main_queue_args(self):
        cons_func = MagicMock(return_value=(True, "ok", None, {}))
        listener, channel = self._make_listener(cons_func, queue_name="veribroke.declare-test")

        main_call = channel.queue_declare.call_args_list[0]
        self.assertEqual(main_call.kwargs, {"queue": "veribroke.declare-test", "durable": True})

        retry_call = channel.queue_declare.call_args_list[1]
        self.assertEqual(retry_call.kwargs["queue"], "veribroke.declare-test.retry")
        self.assertEqual(
            retry_call.kwargs["arguments"]["x-dead-letter-exchange"],
            "io.opencrafts.veribroke",
        )
        self.assertEqual(
            retry_call.kwargs["arguments"]["x-dead-letter-routing-key"],
            "veribroke.declare-test",
        )

        failed_call = channel.queue_declare.call_args_list[2]
        self.assertEqual(failed_call.kwargs["queue"], "veribroke.declare-test.failed")

    def test_success_acks_without_publishing_to_retry_or_failed(self):
        cons_func = MagicMock(return_value=(True, "ok", None, {}))
        listener, channel = self._make_listener(cons_func)

        body = json.dumps({"request_id": "r1", "reply_to": "svc.reply"}).encode()
        listener.callback(channel, _method(1), _properties(), body)

        channel.basic_ack.assert_called_once_with(delivery_tag=1)
        channel.basic_publish.assert_not_called()

    def test_business_failure_notifies_and_acks_same_as_before(self):
        cons_func = MagicMock(return_value=(False, "rejected", "bad phone", {}))
        listener, channel = self._make_listener(cons_func)

        body = json.dumps({"request_id": "r2", "reply_to": "svc.reply"}).encode()
        listener.callback(channel, _method(2), _properties(), body)

        channel.basic_ack.assert_called_once_with(delivery_tag=2)
        publish_kwargs = channel.basic_publish.call_args.kwargs
        self.assertEqual(publish_kwargs["routing_key"], "svc.reply")
        published_body = json.loads(publish_kwargs["body"])
        self.assertFalse(published_body["success"])
        self.assertEqual(published_body["request_id"], "r2")

    def test_unhandled_exception_requeues_to_retry_when_attempts_remain(self):
        cons_func = MagicMock(side_effect=RuntimeError("db is down"))
        listener, channel = self._make_listener(cons_func)

        body = json.dumps({"request_id": "r3", "reply_to": "svc.reply"}).encode()
        listener.callback(channel, _method(3), _properties(headers={}), body)

        channel.basic_ack.assert_called_once_with(delivery_tag=3)
        publish_kwargs = channel.basic_publish.call_args.kwargs
        self.assertEqual(publish_kwargs["exchange"], "")
        self.assertEqual(publish_kwargs["routing_key"], listener.retry_queue_name)
        self.assertEqual(publish_kwargs["properties"].headers[ATTEMPT_HEADER], 1)

    def test_unhandled_exception_goes_to_failed_queue_after_max_attempts(self):
        cons_func = MagicMock(side_effect=RuntimeError("db is down"))
        listener, channel = self._make_listener(cons_func)

        body = json.dumps({"request_id": "r4", "reply_to": "svc.reply"}).encode()
        headers = {ATTEMPT_HEADER: MAX_DELIVERY_ATTEMPTS - 1}
        listener.callback(channel, _method(4), _properties(headers=headers), body)

        channel.basic_ack.assert_called_once_with(delivery_tag=4)
        # one publish to the failed queue, one notification to reply_to
        routing_keys = [c.kwargs["routing_key"] for c in channel.basic_publish.call_args_list]
        self.assertIn(listener.failed_queue_name, routing_keys)
        self.assertIn("svc.reply", routing_keys)

    def test_malformed_json_goes_straight_to_failed_without_retry(self):
        cons_func = MagicMock()
        listener, channel = self._make_listener(cons_func)

        listener.callback(channel, _method(5), _properties(), b"not json")

        cons_func.assert_not_called()
        channel.basic_ack.assert_called_once_with(delivery_tag=5)
        publish_kwargs = channel.basic_publish.call_args.kwargs
        self.assertEqual(publish_kwargs["routing_key"], listener.failed_queue_name)
