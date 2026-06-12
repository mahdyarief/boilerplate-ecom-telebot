"""Structured logging setup (structlog)."""

from __future__ import annotations

import logging

import structlog

from .config import settings


def setup_logging(level: str | None = None) -> None:
    """Configure structlog + stdlib logging once at startup.

    Parameters
    ----------
    level:
        Optional log level string (e.g. ``"DEBUG"``).  Defaults to
        ``settings.LOG_LEVEL``.
    """
    log_level = level or settings.LOG_LEVEL

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.render_to_json
            if settings.USE_WEBHOOK
            else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
