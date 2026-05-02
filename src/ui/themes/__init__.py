"""Concrete themes for the Stjörnhorn UI.

Each module in this package contributes one :class:`~ui.theme.Theme`
instance describing palette, node/link colours, status colours, glow
parameters and the QSS stylesheet template. ``ui.theme`` picks one as
the *active* theme at import time and re-exports its fields as
module-level constants so the rest of the codebase can keep doing
``from ui.theme import NODE_BODY_COLOR`` without caring which theme
is in force.

Adding a new theme is "drop a file here that builds a ``Theme`` and
register it in :data:`ui.theme.AVAILABLE_THEMES`" — no edits to
consumer modules needed.
"""
