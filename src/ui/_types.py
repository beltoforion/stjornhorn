from __future__ import annotations

DpgTag = int | str
"""Identifier for a DearPyGUI item.

Integer tags are produced by ``dpg.generate_uuid()``; string tags are
user-supplied via the ``tag=`` parameter on widget constructors.
"""
