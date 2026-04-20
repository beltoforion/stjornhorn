from __future__ import annotations

from enum import Enum
from pathlib import Path

import cv2
from typing_extensions import override

from constants import OUTPUT_DIR
from core.io_data import IMAGE_TYPES
from core.node_base import SinkNodeBase, NodeParam, NodeParamType
from core.port import InputPort


class OutputFormat(Enum):
    SAME_AS_INPUT = 0
    PNG = 1


class FileSink(SinkNodeBase):
    """Sink node that writes the incoming frame to disk.

    Paths inside the application's :data:`OUTPUT_DIR` are stored — and
    therefore displayed — relative to that folder. Anything outside is kept
    as an absolute path. Relative paths are resolved against ``OUTPUT_DIR``
    at run time, which keeps saved flows portable across machines that
    share the same output layout.
    """

    def __init__(self):
        super().__init__("File Sink", section="Sinks")

        self._output_path: Path = Path("out.png")
        self._output_format: OutputFormat = OutputFormat.SAME_AS_INPUT

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        # Sync attributes with declared NodeParam defaults; see
        # NodeBase._apply_default_params for rationale.
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [NodeParam("output_path", NodeParamType.FILE_PATH, {"default": "out.png", "mode": "save"})]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def output_format(self) -> OutputFormat:
        return self._output_format

    @output_format.setter
    def output_format(self, output_format: OutputFormat) -> None:
        self._output_format = output_format

    @property
    def output_path(self) -> Path:
        return self._output_path

    @output_path.setter
    def output_path(self, output_path: str | Path) -> None:
        p = Path(output_path)
        if p.is_absolute():
            try:
                p = p.resolve().relative_to(OUTPUT_DIR.resolve())
            except (OSError, ValueError):
                pass  # outside OUTPUT_DIR — keep absolute
        self._output_path = p

    # ── SinkNodeBase interface ──────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        resolved = self._resolved_path()

        if self._output_format == OutputFormat.SAME_AS_INPUT:
            output = resolved
        elif self._output_format == OutputFormat.PNG:
            output = resolved.with_suffix(".png")
        else:
            raise ValueError(f"Unsupported output format: {self._output_format}")

        cv2.imwrite(str(output), self.inputs[0].data.image)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _resolved_path(self) -> Path:
        """Return an absolute path; relative values are joined with OUTPUT_DIR."""
        if self._output_path.is_absolute():
            return self._output_path
        return OUTPUT_DIR / self._output_path
