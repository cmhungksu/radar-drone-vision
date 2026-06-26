"""Structured logging setup for the radar-drone-vision project."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED = False


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure the root logger with console (and optional file) handlers.

    Calling this function multiple times is safe; handlers are only added once.

    Parameters
    ----------
    level : str
        Logging level name (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``).
    log_file : str, optional
        If provided, also write logs to this file path (parent dirs created automatically).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Optional file handler
    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(log_path), encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (creates one if it doesn't exist).

    Parameters
    ----------
    name : str
        Logger name, typically ``__name__`` of the calling module.
    """
    return logging.getLogger(name)
