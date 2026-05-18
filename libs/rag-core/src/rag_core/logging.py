"""structlog configuration shared by both apps."""

from __future__ import annotations

import logging
import re
import sys
import time
from typing import Any

import structlog
from structlog.types import Processor

_WEBRTC_NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"RtpPacket\(seq="),
    re.compile(r"Rtcp(?:Rr|Sr|Sdes|Bye)Packet"),
    re.compile(r"^Connection\(\d+\) (?:protocol|Check)"),
)


class _WebRTCNoiseRateLimitFilter(logging.Filter):
    """Allow at most one matching aiortc/aioice packet log per ``period`` seconds.

    Per-RTP-packet logs from aiortc / aioice are extremely chatty (multiple
    lines per audio frame). This filter samples one line per pattern every
    ``period`` seconds so the stream stays alive as a heartbeat without
    drowning out application logs.
    """

    def __init__(self, period: float = 120.0) -> None:
        super().__init__()
        self._period = period
        self._last_emit: dict[int, float] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for index, pattern in enumerate(_WEBRTC_NOISE_PATTERNS):
            if pattern.search(message):
                now = time.monotonic()
                if now - self._last_emit.get(index, 0.0) >= self._period:
                    self._last_emit[index] = now
                    return True
                return False
        return True


def configure_logging(*, level: str = "INFO", fmt: str = "json") -> None:
    """Configure structlog + stdlib logging once at process startup."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    noise_filter = _WebRTCNoiseRateLimitFilter(period=120.0)
    for handler in logging.root.handlers:
        if not any(isinstance(f, _WebRTCNoiseRateLimitFilter) for f in handler.filters):
            handler.addFilter(noise_filter)

    # AWS Bedrock bidirectional streaming (used by Nova Sonic) emits one DEBUG
    # log per audio chunk via the smithy SDKs. Pin those namespaces to INFO so
    # the per-chunk "Publishing serialized event", "Preparing to publish",
    # "Received raw event", "Sending request", etc. lines stay out of the log,
    # even when our own app log level is DEBUG.
    for noisy in ("smithy_aws_event_stream", "smithy_core.aio.client"):
        logging.getLogger(noisy).setLevel(logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor
    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound logger with optional initial context."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial_values:
        logger = logger.bind(**initial_values)
    return logger
