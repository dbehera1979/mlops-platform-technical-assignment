"""Structured JSON logging with correlation-id propagation.

Every log line is a single JSON object so it's directly queryable in any
log aggregator (CloudWatch Logs Insights, Loki, etc.) without a parsing
step. The correlation id is carried via a contextvar so any log call
anywhere in the request/task lifecycle picks it up without threading it
through every function signature.
"""
import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }
        # Structured extras passed via logger.info(..., extra={"extra_fields": {...}})
        extra_fields = getattr(record, "extra_fields", None)
        if extra_fields:
            payload.update(extra_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Quiet down noisy third-party loggers unless we're debugging.
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(
            "WARNING" if level != "DEBUG" else "DEBUG"
        )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    message: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor: str | None = None,
    outcome: str | None = None,
    **extra,
) -> None:
    """Convenience wrapper so every domain log line carries a consistent
    shape (entity_type/entity_id/actor/outcome) per architecture.md §9."""
    fields = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "actor": actor,
        "outcome": outcome,
        **extra,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    logger.info(message, extra={"extra_fields": fields})
