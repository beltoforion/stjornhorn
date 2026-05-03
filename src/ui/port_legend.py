from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QWidget,
)

from core.io_data import IoDataType
from ui.theme import (
    PORT_DIRECTION_GLYPH_COLOR,
    PORT_TYPE_COLORS,
    PORT_TYPE_DEFAULT_COLOR,
    get_active_theme,
)

# Display label per IoDataType. Decoupled from the enum's ``value``
# (which doubles as the persistence token in saved flows) so the
# legend can read in plain English without renaming the enum.
_TYPE_LABELS: dict[IoDataType, str] = {
    IoDataType.IMAGE:      "Image",
    IoDataType.IMAGE_GREY: "Image (grey)",
    IoDataType.SCALAR:     "Scalar",
    IoDataType.MATRIX:     "Matrix",
    IoDataType.DATASET:    "Dataset",
    IoDataType.BOOL:       "Bool",
    IoDataType.STRING:     "String",
    IoDataType.ENUM:       "Enum",
    IoDataType.PATH:       "Path",
}


class _Swatch(QWidget):
    """Tiny port-shaped widget used for legend rows.

    Renders the same darker-fill + bright-ring shape as
    :class:`ui.port_item.PortItem` so the legend reads as a 1:1
    miniature of an actual port. Optional knobs let the caller pick
    the ring stroke style (solid/dotted), ring thickness (mirroring
    required vs. optional ports), and whether to draw the small
    right-pointing glyph (mirroring outputs).
    """

    DOT_SIZE: int = 12
    _RING_WIDTH_DEFAULT: float = 1.4
    _RING_WIDTH_THIN: float = 1.0
    _FILL_DARKEN: int = 200

    # Glyph geometry — kept in sync with PortItem's output triangle so
    # the legend mirrors the canvas without numeric drift.
    _GLYPH_BASE_OFFSET: float = 1.0
    _GLYPH_LENGTH: float = 4.5
    _GLYPH_HALF_HEIGHT: float = 3.0

    def __init__(
        self,
        color: QColor,
        *,
        ring_width: float = _RING_WIDTH_DEFAULT,
        ring_style: Qt.PenStyle = Qt.PenStyle.SolidLine,
        show_glyph: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = color
        self._ring_width = ring_width
        self._ring_style = ring_style
        self._show_glyph = show_glyph
        # Reserve glyph space on the right side so the dot stays
        # left-aligned with neighbouring (glyph-less) swatches in the
        # grid.
        extra = (self._GLYPH_BASE_OFFSET + self._GLYPH_LENGTH + 1.0) if show_glyph else 0.0
        self.setFixedSize(int(self.DOT_SIZE + extra), self.DOT_SIZE)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Inset the rect by half the pen width so the ring sits inside
        # the widget bounds and isn't clipped on either side.
        inset = self._ring_width / 2
        rect = QRectF(inset, inset, self.DOT_SIZE - 2 * inset, self.DOT_SIZE - 2 * inset)

        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(self._color.darker(self._FILL_DARKEN)))
        painter.drawEllipse(rect)

        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.setPen(QPen(self._color, self._ring_width, self._ring_style))
        painter.drawEllipse(rect)

        if self._show_glyph:
            cy = self.DOT_SIZE / 2
            base_x = self.DOT_SIZE - inset + self._GLYPH_BASE_OFFSET
            tip_x = base_x + self._GLYPH_LENGTH
            h = self._GLYPH_HALF_HEIGHT
            path = QPainterPath()
            path.moveTo(base_x, cy - h)
            path.lineTo(tip_x, cy)
            path.lineTo(base_x, cy + h)
            path.closeSubpath()
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(PORT_DIRECTION_GLYPH_COLOR))
            painter.drawPath(path)


class PortLegendContent(QWidget):
    """Embeddable port-language legend.

    Pure content widget — no chrome, no overlay positioning, no close
    button. Renders two sections:

      * **Port types** — one row per :class:`IoDataType` showing the
        colour used for that type's ring and (darker) fill.
      * **Port roles** — required / optional / latched input
        variants and the output glyph, all rendered in the neutral
        default colour so the variation is purely about ring stroke
        and direction marker rather than type colour.

    Embed it directly in any layout. Used by the Node Documentation
    panel as part of its empty-state hint.
    """

    @staticmethod
    def _build_style() -> str:
        """Compose label colours from the active theme so the legend
        tracks the rest of the app — navy text under neon, grey text
        under classic — without needing a dedicated panel background."""
        theme = get_active_theme()
        text = theme.PALETTE_TEXT
        title_text = theme.NODE_TITLE_TEXT_COLOR
        return f"""
        QLabel#PortLegendTitle {{
            color: {title_text.name()};
            font-weight: bold;
            background: transparent;
        }}
        QLabel.PortLegendItem {{
            color: {text.name()};
            background: transparent;
        }}
        """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(self._build_style())

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        row = 0
        row = self._add_section(layout, row, "Port types", self._type_rows())
        row = self._add_section(layout, row, "Port roles", self._role_rows())

    # ── Row builders ───────────────────────────────────────────────────────────

    def _type_rows(self) -> list[tuple[_Swatch, str]]:
        rows: list[tuple[_Swatch, str]] = []
        for t in IoDataType:
            color = PORT_TYPE_COLORS.get(t, PORT_TYPE_DEFAULT_COLOR)
            rows.append((_Swatch(color, parent=self), _TYPE_LABELS.get(t, t.value)))
        return rows

    def _role_rows(self) -> list[tuple[_Swatch, str]]:
        # Neutral colour so the variation reads as ring-style only —
        # the type-colour story stays in the upper section.
        c = PORT_TYPE_DEFAULT_COLOR
        return [
            (
                _Swatch(c, ring_width=_Swatch._RING_WIDTH_DEFAULT, parent=self),
                "Required input",
            ),
            (
                _Swatch(c, ring_width=_Swatch._RING_WIDTH_THIN, parent=self),
                "Optional input",
            ),
            (
                _Swatch(
                    c,
                    ring_width=_Swatch._RING_WIDTH_DEFAULT,
                    ring_style=Qt.PenStyle.DotLine,
                    parent=self,
                ),
                "Latched input (holds last value)",
            ),
            (
                _Swatch(c, show_glyph=True, parent=self),
                "Output",
            ),
        ]

    def _add_section(
        self,
        layout: QGridLayout,
        start_row: int,
        title_text: str,
        rows: list[tuple[_Swatch, str]],
    ) -> int:
        # First section sits flush; subsequent ones leave a small gap by
        # adding extra vertical room on the title row.
        title = QLabel(title_text)
        title.setObjectName("PortLegendTitle")
        if start_row > 0:
            title.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(title, start_row, 0, 1, 2)

        next_row = start_row + 1
        for swatch, text in rows:
            label = QLabel(text)
            label.setProperty("class", "PortLegendItem")
            layout.addWidget(swatch, next_row, 0)
            layout.addWidget(label, next_row, 1)
            next_row += 1
        return next_row
