from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from typing_extensions import override

from constants import OUTPUT_DIR
from core.filename_template import expand as expand_template
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

    Paths inside :data:`OUTPUT_DIR` are stored relative to that folder
    so saved flows port cleanly. ``output_path`` is a filename
    template — ``$frame_index$``, ``$source_stem$`` etc. expand at
    write time, with width syntax ``$tok:N$`` for zero-padding.

    The sink writes one file per arriving frame. To produce N files
    from a single source use :class:`~nodes.filters.repeat.Repeat` with
    a clock; any SCALAR-port value the upstream pipeline reads ends
    up as a ``$<port_name>$`` token in the template (refactor M13).
    """

    output_path = FilePathParam(
        "out.png",
        constant=True,
        mode="save",
        filter="Images (*.png *.jpg *.jpeg)",
        base_dir=OUTPUT_DIR,
        description=(
            "Where to write each frame. May contain $token$ placeholders: "
            "$frame_index$, $source_stem$, $source_name$, $source_ext$, "
            "$flow_name$, plus any SCALAR port value an upstream filter "
            "stamped (e.g. $tick$ from a Repeat). Width syntax $tok:N$ "
            "zero-pads, e.g. out_$frame_index:4$.png. With no placeholders "
            "the file is overwritten on every frame."
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
        # Auto-stamped SCALAR-port values from upstream filters land
        # in IoMeta directly (refactor M13), so the templating engine
        # reads everything from one source.
        meta: dict[str, Any] = dict(self.inputs[0].data.meta)
        resolved_template = self._resolved_template(meta)

        if self._output_format == OutputFormat.SAME_AS_INPUT:
            output = resolved_template
        elif self._output_format == OutputFormat.PNG:
            output = resolved_template.with_suffix(".png")
        else:
            raise ValueError(f"Unsupported output format: {self._output_format}")

        output.parent.mkdir(parents=True, exist_ok=True)
        self._encode_and_write(output, self.inputs[0].data.image)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _encode_and_write(self, output: Path, image: np.ndarray) -> None:
        """Encode *image* in memory then stream the bytes to *output*.

        ``cv2.imwrite`` opens the destination through the C runtime's
        ANSI ``fopen`` on Windows and silently fails on any path with
        characters outside the active code page (the ``ö`` in
        ``stjörnhorn`` was a real-world reproducer). Encoding via
        ``cv2.imencode`` and writing through Python's ``open()``
        sidesteps that limitation — the same trick lives on the read
        side in :class:`~nodes.sources.image_source.ImageSource`.
        """
        ok, buf = cv2.imencode(output.suffix, image)
        if not ok:
            raise OSError(
                f"File Sink failed to encode image for {output!s}. "
                f"The extension {output.suffix!r} may not be supported "
                "by OpenCV's encoders."
            )
        output.write_bytes(buf.tobytes())

    def _resolved_template(self, meta: dict[str, Any]) -> Path:
        """Expand the user's template against *meta*, then resolve
        relative paths against :data:`OUTPUT_DIR`.
        """
        rendered = expand_template(str(self._output_path), meta)
        return resolve_against(Path(rendered), OUTPUT_DIR)
