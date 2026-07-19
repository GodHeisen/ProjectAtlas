"""Logging configuration for Project Atlas."""

import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging for the application."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a named logger instance."""
    return logging.getLogger(name or "atlas")
