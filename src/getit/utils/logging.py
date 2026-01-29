"""Structured logging configuration for getit.

Provides production-ready logging with:
- JSON format for non-TTY (containers, CI)
- Plain format for TTY (user-facing)
- TTY detection and NO_COLOR support
- run_id and download_id correlation
- Secret redaction
- Async-safe logging via QueueHandler
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import queue
import re
import sys
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Generator

_run_id: ContextVar[str | None] = ContextVar("run_id", default=None)
_download_id: ContextVar[str | None] = ContextVar("download_id", default=None)


class LogLevel(str, Enum):
    """Logging level options."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(str, Enum):
    """Log format options."""

    JSON = "json"
    PLAIN = "plain"
    AUTO = "auto"


@dataclass
class LogConfig:
    """Configuration for structured logging."""

    level: LogLevel = LogLevel.INFO
    format: LogFormat = LogFormat.AUTO
    no_color: bool = False

    @classmethod
    def from_env(cls) -> "LogConfig":
        """
        Create a LogConfig populated from environment variables.
        
        Reads LOG_LEVEL (defaults to "INFO") and maps it to LogLevel, falling back to LogLevel.INFO on invalid values. Reads LOG_FORMAT (defaults to "auto") and maps it to LogFormat, falling back to LogFormat.AUTO on invalid values. Reads NO_COLOR and treats "1", "true", or "yes" (case-insensitive) as enabling no-color mode.
        
        Returns:
            LogConfig: A LogConfig instance configured from LOG_LEVEL, LOG_FORMAT, and NO_COLOR.
        """
        level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        try:
            level = LogLevel(level_str)
        except ValueError:
            level = LogLevel.INFO

        format_str = os.getenv("LOG_FORMAT", "auto").lower()
        try:
            format_mode = LogFormat(format_str)
        except ValueError:
            format_mode = LogFormat.AUTO

        no_color = os.getenv("NO_COLOR", "").lower() in ("1", "true", "yes")

        return cls(level=level, format=format_mode, no_color=no_color)

    def should_use_json(self) -> bool:
        """
        Decides whether logs should be emitted in JSON format.
        
        Returns:
            `true` if the configured format is JSON or (when format is AUTO) stdout is not a TTY, `false` otherwise.
        """
        if self.format == LogFormat.JSON:
            return True
        if self.format == LogFormat.PLAIN:
            return False
        return not sys.stdout.isatty()


class SecretRedactor:
    """Redacts sensitive information from log messages."""

    PATTERNS: ClassVar[tuple[str, ...]] = (
        r'token["\s:=]+["\s]*([a-zA-Z0-9_-]{20,})',
        r'password["\s:=]+["\s]*([^\s"\'}]{6,})',
        r'api[_-]?key["\s:=]+["\s]*([a-zA-Z0-9_-]{20,})',
        r'api[_-]?secret["\s:=]+["\s]*([a-zA-Z0-9_-]{20,})',
        r'authorization["\s:=]+["\s]*[Bb]earer\s+([a-zA-Z0-9_-]{20,})',
        r"Bearer\s+([a-zA-Z0-9_-]{20,})",
        r'bearer["\s:=]+["\s]*([a-zA-Z0-9_-]{20,})',
        r'secret["\s:=]+["\s]*([a-zA-Z0-9_-]{20,})',
        r'key["\s:=]+["\s]*([a-zA-Z0-9_-]{20,})',
        r'token["\s:=]+["\s]*([a-zA-Z0-9_-]{20,})',
    )

    REDACTED_PLACEHOLDER: ClassVar[str] = "***REDACTED***"

    _compiled_patterns: ClassVar[list[re.Pattern[str]]] = [
        re.compile(pattern, re.IGNORECASE) for pattern in PATTERNS
    ]

    @classmethod
    def redact(cls, message: str) -> str:
        """
        Redacts sensitive values from a text message.
        
        Parameters:
            message (str): Text that may contain sensitive values to be redacted.
        
        Returns:
            str: A copy of `message` with sensitive substrings replaced by the redaction placeholder.
        """
        for pattern in cls._compiled_patterns:
            message = pattern.sub(cls.REDACTED_PLACEHOLDER, message)
        return message


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a LogRecord into a JSON-encoded log entry string.
        
        Parameters:
            record (logging.LogRecord): The log record to format.
        
        Returns:
            str: A JSON string representing the log record that includes `timestamp`, `level`, `logger`, a redacted `message`, `run_id`, `download_id`, an `exception` field when present, and any other non-standard record attributes; the string ends with a newline.
        """
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": SecretRedactor.redact(record.getMessage()),
            "run_id": getattr(record, "run_id", None),
            "download_id": getattr(record, "download_id", None),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            }:
                log_entry[key] = value

        return json.dumps(log_entry) + "\n"


class PlainFormatter(logging.Formatter):
    """Plain text formatter with optional colors."""

    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def __init__(self, no_color: bool = False) -> None:
        """
        Create a plain-text log formatter that includes timestamp, level, logger name, and message, with optional ANSI color suppression.
        
        Parameters:
            no_color (bool): If True, disable ANSI color codes in formatted output. Default is False.
        """
        self.no_color = no_color
        fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
        super().__init__(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a LogRecord into a plain-text log line with secret redaction, optional ANSI colors, and appended run/download context.
        
        Parameters:
            record (logging.LogRecord): The log record to format.
        
        Returns:
            str: The redacted, context-annotated plain-text message. Includes ANSI color codes when colors are enabled and stdout is a TTY.
        """
        message = super().format(record)
        message = SecretRedactor.redact(message)

        run_id = getattr(record, "run_id", None)
        download_id = getattr(record, "download_id", None)
        context_parts = []
        if run_id:
            context_parts.append(f"run_id={run_id}")
        if download_id:
            context_parts.append(f"dl_id={download_id}")
        if context_parts:
            message = f"[{' '.join(context_parts)}] {message}"

        if not self.no_color and sys.stdout.isatty():
            color = self.COLORS.get(record.levelname, "")
            if color:
                message = f"{color}{message}{self.RESET}"

        return message


class AsyncSafeLogHandler(logging.Handler):
    """Async-safe logging handler using QueueHandler.

    Ensures logs from async/await contexts are safely queued and processed
    by a background thread to avoid blocking event loops.
    """

    def __init__(self, handler: logging.Handler) -> None:
        """
        Initialize an async-safe log handler that queues records before delegating to the given target handler.
        
        Parameters:
            handler (logging.Handler): The underlying handler that will ultimately process log records; the AsyncSafeLogHandler will enqueue records and forward them to this handler via a background listener.
        """
        super().__init__()
        self.queue_handler = logging.handlers.QueueHandler(queue.Queue(-1))
        self.queue = self.queue_handler.queue
        self.target_handler = handler
        self.listener: logging.handlers.QueueListener | None = None

    def emit(self, record: logging.LogRecord) -> None:
        """
        Attach the current run and download context to the given log record and forward it to the internal queue handler if configured.
        
        Parameters:
            record (logging.LogRecord): Log record to emit. This function sets `record.run_id` and `record.download_id` from the current context before forwarding the record to the internal queue handler when present.
        """
        record.run_id = _run_id.get()
        record.download_id = _download_id.get()
        if self.queue_handler:
            self.queue_handler.emit(record)

    def start_listener(self) -> None:
        """Start the queue listener in a background thread."""
        if self.listener is None:
            self.listener = logging.handlers.QueueListener(self.queue, self.target_handler)
            self.listener.start()

    def stop_listener(self) -> None:
        """
        Stop the background QueueListener if it is running.
        
        If a listener is active, this stops it and clears the internal reference; calling this when no listener is active does nothing.
        """
        if self.listener:
            self.listener.stop()
            self.listener = None


_logger: logging.Logger | None = None
_async_handler: AsyncSafeLogHandler | None = None


def setup_logging(config: LogConfig | None = None) -> None:
    """
    Configure and enable structured logging for the application.
    
    This function is idempotent: if logging has already been initialized it does nothing. If `config` is omitted, configuration is loaded from environment variables. The configured handlers are attached to the application logger and the root logger so logging is available across the process.
     
    Parameters:
        config (LogConfig | None): Optional logging configuration. If `None`, a configuration is created from environment variables.
    """
    global _logger, _async_handler

    if _logger is not None:
        return

    if config is None:
        config = LogConfig.from_env()

    _logger = logging.getLogger("getit")
    _logger.setLevel(getattr(logging, config.level.value))

    _logger.handlers.clear()

    use_json = config.should_use_json()
    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = PlainFormatter(no_color=config.no_color)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    _async_handler = AsyncSafeLogHandler(stream_handler)
    _async_handler.start_listener()

    _logger.addHandler(_async_handler)

    # Configure root logger to propagate all logs
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level.value))
    root_logger.addHandler(_async_handler)

    _logger.info("Logging initialized", extra={"format": "json" if use_json else "plain"})


def shutdown_logging() -> None:
    """Shutdown logging and stop the queue listener."""
    global _async_handler

    if _async_handler:
        _async_handler.stop_listener()
        _async_handler = None


@contextmanager
def set_run_id(run_id: str | None = None) -> Generator[None, None, None]:
    """
    Set the current run identifier for the execution context.
    
    If `run_id` is None, generates an 8-character UUID string and uses that as the run identifier.
    The previous run_id value is restored when the context exits.
    
    Parameters:
        run_id (str | None): Optional run identifier to set for the context. If omitted, a new 8-character UUID is generated.
    """
    if run_id is None:
        run_id = str(uuid.uuid4())[:8]
    token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(token)


@contextmanager
def set_download_id(download_id: str | None = None) -> Generator[None, None, None]:
    """
    Temporarily set the download identifier in context for the duration of a with-block.
    
    Sets the module-level download_id context variable to the provided string or, if None, to a newly generated 8-character UUID. The previous context value is restored when the context manager exits.
    
    Parameters:
        download_id (str | None): The download identifier to set; if None, an 8-character UUID fragment is generated.
    """
    if download_id is None:
        download_id = str(uuid.uuid4())[:8]
    token = _download_id.set(download_id)
    try:
        yield
    finally:
        _download_id.reset(token)


def get_run_id() -> str | None:
    """
    Retrieve the current run identifier from the logging context.
    
    Returns:
        The current run identifier as a string, or `None` if no run id is set.
    """
    return _run_id.get()


def get_download_id() -> str | None:
    """
    Retrieve the current download identifier from the logging context.
    
    Returns:
        str | None: The current download identifier if set, otherwise `None`.
    """
    return _download_id.get()


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    This is a convenience wrapper around logging.getLogger() that ensures
    the logging system has been configured.

    Args:
        name: The name of the logger (typically __name__)

    Returns:
        A logger instance
    """
    if _logger is None:
        setup_logging()
    return logging.getLogger(name)


__all__ = [
    "setup_logging",
    "get_logger",
    "shutdown_logging",
    "set_run_id",
    "set_download_id",
    "get_run_id",
    "get_download_id",
    "LogConfig",
    "LogLevel",
    "LogFormat",
    "SecretRedactor",
]