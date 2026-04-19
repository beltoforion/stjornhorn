"""Application-wide logging configuration.

Call ``setup_logging()`` once at startup before creating any other objects.
All modules then obtain their own logger with ``logging.getLogger(__name__)``.

Log destinations:
  - File  : ~/.image-inquest/image-inquest.log  (DEBUG and above, rotating)
  - Console: WARNING and above
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


_STARTUP_BANNER = r"""
  _________                   __   .__         .__                   _____
 /   _____/__________ _______|  | _|  |   ____ |  |__   ____   _____/ ____\
 \_____  \\____ \__  \\_  __ \  |/ /  | _/ __ \|  |  \ /  _ \ /  _ \   __\
 /        \  |_> > __ \|  | \/    <|  |_\  ___/|   Y  (  <_> |  <_> )  |
/_______  /   __(____  /__|  |__|_ \____/\___  >___|  /\____/ \____/|__|
        \/|__|       \/           \/         \/     \/
"""


def setup_logging(log_dir: Path, level: int = logging.DEBUG) -> None:
    """Configure the root logger.

    Args:
        log_dir: Directory where the log file is written (created if absent).
        level:   Minimum level captured by the file handler (default DEBUG).
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "image-inquest.log"

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — keeps the last 5 × 1 MB chunks
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)

    # Console handler — only warnings and above to avoid noise
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Emit the session banner through the standard formatter so every
    # line carries a timestamp and keeps the log format consistent.
    # INFO is below the console handler's threshold, so the banner
    # only lands in the file.
    banner = logging.getLogger("banner")
    for line in _STARTUP_BANNER.splitlines():
        if line:
            banner.info(line)

    logging.getLogger(__name__).info("Logging initialised → %s", log_file)
