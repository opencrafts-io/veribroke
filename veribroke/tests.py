import json
import logging

from django.test import SimpleTestCase

from veribroke.logging import JsonFormatter


def _make_record(level=logging.INFO, msg="test message", extra=None):
    record = logging.LogRecord(
        name="veribroke.tests",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


class JsonFormatterTests(SimpleTestCase):
    def test_produces_valid_json_with_core_fields(self):
        formatter = JsonFormatter()
        record = _make_record(msg="stk push sent")

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "veribroke.tests")
        self.assertEqual(payload["message"], "stk push sent")
        self.assertIn("timestamp", payload)

    def test_extra_fields_are_surfaced_as_structured_keys(self):
        formatter = JsonFormatter()
        record = _make_record(
            msg="stk push sent",
            extra={"request_id": "abc123", "amount": 500},
        )

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload["request_id"], "abc123")
        self.assertEqual(payload["amount"], 500)

    def test_exception_info_is_included(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = _make_record(level=logging.ERROR, msg="failed")
            record.exc_info = sys.exc_info()

        payload = json.loads(formatter.format(record))

        self.assertIn("ValueError: boom", payload["exc_info"])

    def test_non_serializable_extra_value_does_not_crash_formatting(self):
        formatter = JsonFormatter()
        record = _make_record(extra={"errors": ValueError("not json-serializable")})

        payload = json.loads(formatter.format(record))

        self.assertIn("not json-serializable", payload["errors"])
