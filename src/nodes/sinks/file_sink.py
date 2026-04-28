from __future__ import annotations

from enum import Enum
from pathlib import Path

import cv2
from typing_extensions import override

from constants import OUTPUT_DIR
from core.io_data import IMAGE_TYPES
from core.node_base import SinkNodeBase
from core.params import FilePathParam
from core.path_utils import resolve_against
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

    output_path = FilePathParam(
        "out.png",
        constant=True,
        mode="save",
        filter="Images (*.png *.jpg *.jpeg)",
        base_dir=OUTPUT_DIR,
        description=(
            "Where to write each frame. The file is overwritten on "
            "every frame, so this sink fits a single still or the "
            "last frame of a stream — chain a unique filename per "
            "frame upstream if you need a sequence."
        ),
    )

    def __init__(self):
        super().__init__("File Sink", section="Sinks")
        # ``output_format`` is set programmatically (not a UI param) so
        # it stays as a plain attribute with a hand-rolled property.
        self._output_format: OutputFormat = OutputFormat.SAME_AS_INPUT
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @property
    def output_format(self) -> OutputFormat:
        return self._output_format

    @output_format.setter
    def output_format(self, output_format: OutputFormat) -> None:
        self._output_format = output_format

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
        return resolve_against(self._output_path, OUTPUT_DIR)
