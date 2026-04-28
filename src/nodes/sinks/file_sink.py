from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

import cv2
from typing_extensions import override

from constants import OUTPUT_DIR
from core.io_data import IMAGE_TYPES
from core.node_base import (
    NodeParam,
    NodeParamType,
    SinkNodeBase,
    get_current_flow_name,
)
from core.path_placeholders import expand_placeholders, has_placeholders
from core.path_utils import resolve_against, store_relative_to
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

    The ``output_path`` accepts ``$token$`` placeholders that expand
    every frame at write time. Without a frame-varying token the same
    file is overwritten on every frame, so a stream collapses to its
    final frame; chain ``$frame_index$`` or ``$input_stem$`` (when the
    upstream source streams multiple files) to get one output file per
    frame.

    Supported tokens:

      ``$input_stem$``    Originating source filename without extension
                          (``ship`` for ``ship.jpg``). Empty when no
                          upstream source stamped a path on the frame.
      ``$input_name$``    Originating source filename with extension
                          (``ship.jpg``). Empty when unknown.
      ``$input_ext$``     Extension of the originating source, dot
                          stripped (``jpg``). Empty when unknown.
      ``$flow_name$``     Name of the currently-running flow.
      ``$frame_index$``   Zero-padded 4-digit per-run frame counter,
                          starting at ``0000`` and incrementing for
                          each frame written by this sink.
      ``$timestamp$``     Run start time as ``YYYYMMDD_HHMMSS``,
                          stable for the duration of one Run.

    Unknown tokens are left as-is in the resulting filename so typos
    surface visibly. Paths with no tokens are written byte-for-byte
    (the common ``out.png`` case is unchanged). Issue: #159.

    Examples (assuming ``ship.jpg`` is the upstream source and the flow
    is named ``denoise_v2``)::

        out.png                          → out.png
        frame_$frame_index$.png          → frame_0000.png, frame_0001.png, ...
        $input_stem$.$flow_name$.png     → ship.denoise_v2.png
        runs/$timestamp$/$input_name$    → runs/20260428_182300/ship.jpg
    """

    def __init__(self):
        super().__init__("File Sink", section="Sinks")

        self._output_path: Path = Path("out.png")
        self._output_format: OutputFormat = OutputFormat.SAME_AS_INPUT

        # Per-run state for placeholder expansion. Reset in
        # ``_before_run_impl`` so a second run starts at frame 0.
        self._frame_index: int = 0
        self._run_started_at: datetime | None = None

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_param(NodeParam(
            "output_path",
            NodeParamType.FILE_PATH,
            default="out.png",
            metadata={
                "mode": "save",
                "filter": "Images (*.png *.jpg *.jpeg)",
                "base_dir": OUTPUT_DIR,
                "description": (
                    "Where to write each frame. Relative paths are resolved "
                    "against the output folder.\n"
                    "\n"
                    "Accepts $token$ placeholders expanded per frame:\n"
                    "  $input_stem$   — source filename without extension (ship)\n"
                    "  $input_name$   — source filename with extension (ship.jpg)\n"
                    "  $input_ext$    — source extension, no dot (jpg)\n"
                    "  $flow_name$    — currently-running flow name\n"
                    "  $frame_index$  — zero-padded 4-digit frame counter (0000)\n"
                    "  $timestamp$    — run start time (YYYYMMDD_HHMMSS)\n"
                    "\n"
                    "Without a frame-varying token the file is overwritten on "
                    "every frame. Use $frame_index$ for stream → numbered "
                    "stills, or $input_stem$ when the upstream source streams "
                    "multiple files (DirectorySource)."
                ),
            },
        ))
        # Sync attributes with declared port defaults; see
        # NodeBase._apply_default_params for rationale.
        self._apply_default_params()

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
        self._output_path = store_relative_to(output_path, OUTPUT_DIR)

    # ── SinkNodeBase interface ──────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        self._frame_index = 0
        self._run_started_at = datetime.now()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        resolved = self._resolved_path(source_path=in_data.source_path)

        if self._output_format == OutputFormat.SAME_AS_INPUT:
            output = resolved
        elif self._output_format == OutputFormat.PNG:
            output = resolved.with_suffix(".png")
        else:
            raise ValueError(f"Unsupported output format: {self._output_format}")

        output.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output), in_data.image)
        self._frame_index += 1

    # ── Internals ──────────────────────────────────────────────────────────────

    def _resolved_path(self, source_path: Path | None = None) -> Path:
        """Return an absolute path; relative values are joined with OUTPUT_DIR.

        Expands ``$token$`` placeholders before resolving. Issue: #159.
        """
        raw = str(self._output_path)
        if has_placeholders(raw):
            expanded = expand_placeholders(
                raw,
                source_path=source_path,
                flow_name=get_current_flow_name(),
                frame_index=self._frame_index,
                run_started_at=self._run_started_at,
            )
            return resolve_against(Path(expanded), OUTPUT_DIR)
        return resolve_against(self._output_path, OUTPUT_DIR)
