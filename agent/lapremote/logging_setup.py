"""Structured JSON-lines logging to ~/.lapremote/logs/agent.log (5 x 1MB) plus the console.

Never pass tokens, pairing codes or typed text to the logger. Log lengths instead.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOGGER_NAME = "lapremote"
LOG_FILE = "agent.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 4  # agent.log + 4 rotated files = 5 x 1MB
_HANDLER_TAG = "_lapremote_handler"


class JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update(fields)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", None)
        extra = ""
        if isinstance(fields, dict) and fields:
            extra = " " + " ".join(f"{k}={v}" for k, v in fields.items())
        line = f"{record.levelname:<7} {record.getMessage()}{extra}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(log_dir: Path, *, console: bool = True, level: int = logging.INFO) -> Path:
    """Configure the ``lapremote`` logger. Safe to call more than once."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_TAG, False):
            logger.removeHandler(handler)
            handler.close()
    logger.setLevel(level)
    logger.propagate = False

    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / LOG_FILE
    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(JsonLinesFormatter())
    setattr(file_handler, _HANDLER_TAG, True)
    logger.addHandler(file_handler)

    if console:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(ConsoleFormatter())
        setattr(stream, _HANDLER_TAG, True)
        logger.addHandler(stream)
    return path


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, event, extra={"fields": fields})
