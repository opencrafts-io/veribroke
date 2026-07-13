import json
import logging

# Attributes logging.LogRecord already sets on every record -- anything
# else found on a record came from a caller's `extra={...}` and should
# be surfaced as its own structured field in the JSON output.
_RESERVED_RECORD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
})


class JsonFormatter(logging.Formatter):
    """
    Renders each log record as a single JSON line: timestamp, level,
    logger name, the formatted message, source location, and any
    structured fields passed via `extra={...}` -- e.g.
    `logger.info("stk push sent", extra={"request_id": request_id})`
    produces `{"request_id": "...", ...}` as its own queryable key
    rather than baking it into the message string.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "line": record.lineno,
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str)
