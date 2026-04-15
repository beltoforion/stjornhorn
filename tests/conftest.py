"""Pytest configuration for the image-inquest test suite.

Puts ``src/`` on ``sys.path`` so tests can import ``core.*`` and ``nodes.*``
with the same import layout the application uses at runtime.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
