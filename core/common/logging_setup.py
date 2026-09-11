"""Structured logging setup for AT-CORE.

Every AT process (CLI tools, tests, eventually firmware-side Python tooling)
should call ``configure_logging`` once at startup and then use
``logging.getLogger(__name__)`` as usual. Log records are emitted as
single-line JSON so they can later be shipped to the diagnostics/telemetry
pipeline (Phase 31) without a reformatting step.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class JsonFormatter(logging.Formatter):
    """Renders each log record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": round(time.time(), 6),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


_CONFIGURED = False


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Idempotently configure the root logger.

    Args:
        level: Standard logging level name (DEBUG/INFO/WARNING/ERROR).
        json_output: When True, emit one JSON object per line (good for log
            shipping). When False (default), emit human-readable lines (good
            for interactive terminal use during development).
    """
    global _CONFIGURED
    root = logging.getLogger()
    root.setLevel(level.upper())

    if _CONFIGURED:
        return

    handler = logging.StreamHandler(stream=sys.stderr)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    root.handlers.clear()
    root.addHandler(handler)
    _CONFIGURED = True


def log_with_fields(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Log a message with extra structured fields (only surfaces in JSON mode)."""
    logger.log(level, message, extra={"extra_fields": fields})
