"""Application-wide logging configuration.

Call ``setup_logging()`` once at startup before creating any other objects.
All modules then obtain their own logger with ``logging.getLogger(__name__)``.

Log destinations:
  - File  : <app-folder>/logs/image-inquest.log  (DEBUG and above, rotating)
  - Console: WARNING and above
"""
from __future__ import annotations

import datetime
import faulthandler
import logging
import logging.handlers
from pathlib import Path

# Module-level handle so the file stays open for the lifetime of the
# process. faulthandler writes directly via the underlying file
# descriptor from its signal handler, so the object must not be GC'd.
_faulthandler_file = None


_STARTUP_BANNER = r"""
  _________                   __   .__         .__                   _____
 /   _____/__________ _______|  | _|  |   ____ |  |__   ____   _____/ ____\
 \_____  \\____ \__  \\_  __ \  |/ /  | _/ __ \|  |  \ /  _ \ /  _ \   __\
 /        \  |_> > __ \|  | \/    <|  |_\  ___/|   Y  (  <_> |  <_> )  |
/_______  /   __(____  /__|  |__|_ \____/\___  >___|  /\____/ \____/|__|
        \/|__|       \/           \/         \/     \/
"""


# Width of the logger-name column. Names longer than this are truncated
# with an ellipsis so the message column always starts at the same
# offset.
_NAME_WIDTH = 24


class _FixedWidthFormatter(logging.Formatter):
    """Formatter that pads/truncates ``record.name`` to ``_NAME_WIDTH``.

    Every field before the message (``asctime`` → 19 chars,
    ``levelname`` → 8, ``name`` → 24) has a fixed width, so the message
    column lines up regardless of which module logged the record.
    """

    def format(self, record: logging.LogRecord) -> str:
        name = record.name
        if len(name) > _NAME_WIDTH:
            name = name[: _NAME_WIDTH - 1] + "…"
        else:
            name = name.ljust(_NAME_WIDTH)
        # Copy so other handlers still see the original unpadded name.
        rec = logging.makeLogRecord(record.__dict__)
        rec.name = name
        return super().format(rec)


def setup_logging(log_dir: Path, level: int = logging.DEBUG) -> None:
    """Configure the root logger.

    Args:
        log_dir: Directory where the log file is written (created if absent).
        level:   Minimum level captured by the file handler (default DEBUG).
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "image-inquest.log"

    _enable_faulthandler(log_dir)

    fmt = _FixedWidthFormatter(
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

    # numba.core.ssa emits a torrent of DEBUG records during JIT compilation
    # that drowns out everything else in the log file. Cap it at INFO.
    logging.getLogger("numba.core.ssa").setLevel(logging.INFO)
    logging.getLogger("numba.core.byteflow").setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    # Each banner line goes through the standard formatter so the log
    # format stays consistent. INFO is below the console handler's
    # threshold, so the banner lands in the file only.
    for line in _STARTUP_BANNER.splitlines():
        if line:
            logger.info(line)

    logger.info("Logging initialised → %s", log_file)
    if _faulthandler_file is not None:
        logger.info("faulthandler dump → %s", _faulthandler_file.name)


def _enable_faulthandler(log_dir: Path) -> None:
    """Route C-level crash dumps (SIGSEGV, SIGABRT, …) to a persistent file.

    main.py enables faulthandler against stderr at import time so crashes
    during Qt startup are still caught. Once we have a writable log dir
    we re-enable it against an append-mode file so post-mortems survive
    the terminal closing.
    """
    global _faulthandler_file
    dump_path = log_dir / "faulthandler.log"
    try:
        _faulthandler_file = open(dump_path, "a", buffering=1, encoding="utf-8")
    except OSError:
        # Keep the stderr-based handler installed by main.py.
        logging.getLogger(__name__).warning(
            "Could not open %s for faulthandler; keeping stderr dump", dump_path
        )
        return
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"\n--- faulthandler attached at {stamp} ---", file=_faulthandler_file)
    faulthandler.enable(file=_faulthandler_file, all_threads=True)
