"""Centralized logging configuration.

Call :func:`setup_logging` once at startup. Every module then obtains its
logger with :func:`get_logger(__name__) <get_logger>`, so log lines carry
the module name.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE_NAME = "release_governance.log"
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5

# Marks handlers created here so repeated setup calls can replace them
# without touching handlers installed by other code (e.g. pytest).
_HANDLER_MARKER = "_release_governance_handler"


def setup_logging(
    log_dir: Path,
    console_level: int = logging.INFO,
    file_level: int = logging.INFO,
) -> Path:
    """Configure console and rotating-file logging for the application.

    Safe to call more than once: handlers from a previous call are replaced.

    Args:
        log_dir: Directory for the log file; created if it doesn't exist.
        console_level: Minimum level written to the console (stderr).
        file_level: Minimum level written to the log file.

    Returns:
        The path of the log file.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    root = logging.getLogger()
    _remove_own_handlers(root)
    root.setLevel(min(console_level, file_level))
    root.addHandler(_build_console_handler(formatter, console_level))
    root.addHandler(_build_file_handler(log_file, formatter, file_level))
    return log_file


def get_logger(name: str) -> logging.Logger:
    """Return the logger for a module.

    Args:
        name: Usually the calling module's ``__name__``.

    Returns:
        A standard :class:`logging.Logger`.
    """
    return logging.getLogger(name)


def _build_console_handler(formatter: logging.Formatter, level: int) -> logging.Handler:
    """Create a stderr handler, keeping stdout free for program output."""
    handler = logging.StreamHandler(sys.stderr)
    return _mark(handler, formatter, level)


def _build_file_handler(
    log_file: Path, formatter: logging.Formatter, level: int
) -> logging.Handler:
    """Create a size-rotating file handler."""
    handler = RotatingFileHandler(
        log_file, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    return _mark(handler, formatter, level)


def _mark(handler: logging.Handler, formatter: logging.Formatter, level: int) -> logging.Handler:
    """Apply format and level to ``handler`` and tag it as ours."""
    handler.setFormatter(formatter)
    handler.setLevel(level)
    setattr(handler, _HANDLER_MARKER, True)
    return handler


def _remove_own_handlers(logger: logging.Logger) -> None:
    """Detach and close handlers previously added by :func:`setup_logging`."""
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()
