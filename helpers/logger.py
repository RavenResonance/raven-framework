# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# This file is part of the Raven Framework and is proprietary
# to Raven Resonance, Inc. Unauthorized copying, modification,
# or distribution is prohibited without prior written permission.
#
# ================================================================

"""
Logging utilities for Raven Framework.

This module provides a centralized logging system with support for console output,
file logging, and remote logging. It automatically detects container environments
and configures appropriate log directories.
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_config() -> dict:
    """
    Load configuration from config.json file.

    Returns:
        dict: Configuration dictionary loaded from config.json.
    """
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, "r") as f:
        return json.load(f)


# Load configuration
_config = load_config()


LOG_NAME = _config["logger"]["LOG_NAME"]

# Constants for log directory paths
DOCKERENV_PATH = _config["logger"]["DOCKERENV_PATH"]
CONTAINER_ENV_VAR = _config["logger"]["CONTAINER_ENV_VAR"]
CONTAINER_LOG_DIR = _config["logger"]["CONTAINER_LOG_DIR"]
LOG_SUBDIR = _config["logger"]["LOG_SUBDIR"]


def get_log_directory() -> str:
    """
    Determine the appropriate log directory based on environment.

    Returns:
        str: Path to the log directory. Returns CONTAINER_LOG_DIR in container
             environments, otherwise returns a LOG_SUBDIR directory relative to the
             framework root.
    """
    if os.path.exists(DOCKERENV_PATH) or os.environ.get(CONTAINER_ENV_VAR) == "true":
        return CONTAINER_LOG_DIR
    else:
        helpers_dir = os.path.dirname(__file__)
        raven_framework_dir = os.path.dirname(helpers_dir)
        root_dir = os.path.dirname(raven_framework_dir)

        return os.path.join(root_dir, LOG_SUBDIR)


LOG_DIR = get_log_directory()

# Constants for log file configuration
BYTES_PER_KB = _config["logger"]["BYTES_PER_KB"]
BYTES_PER_MB = BYTES_PER_KB * 1024
MAX_LOG_SIZE_MB = _config["logger"]["MAX_LOG_SIZE_MB"]
MAX_LOG_SIZE = MAX_LOG_SIZE_MB * BYTES_PER_MB  # 5MB max log file size
BACKUP_COUNT = _config["logger"]["BACKUP_COUNT"]  # Number of backup log files to keep

ENABLE_FILE_LOGGING = _config["logger"]["ENABLE_FILE_LOGGING"]
ENABLE_CONSOLE_LOGGING = _config["logger"]["ENABLE_CONSOLE_LOGGING"]

# EXCLUDED_LEVELS: Dictionary mapping log levels to exclusion flags.
# Currently all levels are False (not excluded), but kept for future configurability.
# Set a level to True to exclude it from file logging.
EXCLUDED_LEVELS: Dict[int, bool] = {
    logging.DEBUG: False,
    logging.INFO: False,
    logging.WARNING: False,
    logging.ERROR: False,
    logging.CRITICAL: False,
}

# Create log directory with error handling
# Note: Potential race condition if multiple processes create directory simultaneously,
# but exist_ok=True handles most cases.
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except (OSError, PermissionError) as e:
    LOG_DIR = CONTAINER_LOG_DIR
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        print(
            f"Warning: Failed to create original log directory, using fallback: {LOG_DIR}",
            file=sys.stderr,
        )
    except (OSError, PermissionError) as fallback_error:
        print(
            f"Error: Failed to create log directory: {fallback_error}", file=sys.stderr
        )
        ENABLE_FILE_LOGGING = False

LOG_FILE = (
    os.path.join(
        LOG_DIR,
        f"{LOG_NAME.lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log",
    )
    if ENABLE_FILE_LOGGING
    else None
)

logger = logging.getLogger(LOG_NAME)
logger.setLevel(logging.DEBUG)
logger.propagate = False

formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] [%(name)s] [%(module)s.%(funcName)s] -> %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ---- Filters ----
class LevelFilter(logging.Filter):
    """
    Filter to exclude specific log levels from handlers.

    Args:
        excluded_levels (Dict[int, bool]): Dictionary mapping log level numbers to
            boolean values. True means the level should be excluded.
    """

    def __init__(self, excluded_levels: Dict[int, bool]) -> None:
        super().__init__()
        self.excluded_levels = excluded_levels

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log records based on excluded levels.

        Args:
            record: Log record to filter.

        Returns:
            bool: True if record should be logged, False if it should be excluded.
        """
        return not self.excluded_levels.get(record.levelno, False)


class ConsoleFilter(logging.Filter):
    """
    Filter to only show logs in console if record has console=True.

    This allows selective console output by setting extra={"console": True}
    when logging.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log records for console output.

        Args:
            record: Log record to filter.

        Returns:
            bool: True if record should be shown in console, False otherwise.
        """
        return getattr(record, "console", False)


level_filter = LevelFilter(EXCLUDED_LEVELS)


# ---- Handlers ----
if ENABLE_CONSOLE_LOGGING:
    # Ensure stdout is UTF-8 on Windows before creating handler
    if sys.platform.startswith("win"):
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(ConsoleFilter())  # show only marked logs
    logger.addHandler(console_handler)

if ENABLE_FILE_LOGGING and LOG_FILE:
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_LOG_SIZE, backupCount=BACKUP_COUNT
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(level_filter)
        logger.addHandler(file_handler)
    except (OSError, PermissionError, IOError) as e:
        # Log to stderr since file logging failed
        print(f"Warning: Failed to create file handler: {e}", file=sys.stderr)
        ENABLE_FILE_LOGGING = False


# ---- Public Accessor ----
def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger with the specified name.

    Args:
        name (str): Name for the child logger. Typically the module or class name.

    Returns:
        logging.Logger: Child logger instance configured with the same handlers
            and formatting as the root logger.

    Raises:
        ValueError: If name is empty or None.
    """
    if not name or not name.strip():
        raise ValueError("Logger name cannot be empty")
    return logger.getChild(name)
