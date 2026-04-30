from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import cv2
from typing_extensions import override

from constants import OUTPUT_DIR
from core.filename_template import expand as expand_template
from core.io_data import IMAGE_TYPES, IoDataType
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

    The optional ``tick`` SCALAR input drives one write per tick when
    connected; otherwise the sink fires on every image frame. The
    ``image`` port latches its last value so a one-shot source can
    sit alongside a streaming ``tick`` clock.
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
            "$flow_name$. Width syntax $tok:N$ zero-pads, e.g. "
            "out_$frame_index:4$.png. With no placeholders the file is "
            "overwritten on every frame."
        ),
    )

    def __init__(self):
        super().__init__("File Sink", section="Sinks")
        # ``output_format`` is set programmatically (not a UI param) so
        # it stays as a plain attribute with a hand-rolled property.
        self._output_format: OutputFormat = OutputFormat.SAME_AS_INPUT
        # Image is held: a one-shot source (ImageSource) feeds it once
        # and stays alive against any tick clock that drives the sink.
        # Without hold_last the second tick would arrive at an empty
        # image port and the dispatcher wouldn't fire.
        self._add_input(InputPort("image", set(IMAGE_TYPES), hold_last=True))
        # Optional clock. When connected, it's the lifecycle driver
        # (its frame_index is what flows into the template); when
        # dangling, the image input is the only input and behaves as
        # the legacy single-write path.
        self._add_input(
            InputPort("tick", {IoDataType.SCALAR}, optional=True),
        )
        self._apply_default_params()

    @property
    def output_format(self) -> OutputFormat:
        return self._output_format

    @output_format.setter
    def output_format(self, output_format: OutputFormat) -> None:
        self._output_format = output_format

    @override
    def process_impl(self) -> None:
        # Combine metas from every connected input — later inputs win
        # on key collisions. tick (declared after image) brings the
        # per-write frame_index; image brings source_path. Resulting
        # bag has both, ready for the template engine.
        meta = self._merged_meta()
        # Plus: every connected SCALAR input is exposed by its port
        # name as a template token (e.g. ``$tick$`` resolves to the
        # current tick value). Lets the user template on the actual
        # scalar value rather than the per-port emit counter — so a
        # ``RangeSource(1..10) → tick`` flow can write ``out_01.png``
        # rather than ``out_00.png`` with 0-based frame_index.
        context = self._scalar_inputs_as_context()

        resolved_template = self._resolved_template(meta, context)

        if self._output_format == OutputFormat.SAME_AS_INPUT:
            output = resolved_template
        elif self._output_format == OutputFormat.PNG:
            output = resolved_template.with_suffix(".png")
        else:
            raise ValueError(f"Unsupported output format: {self._output_format}")

        output.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output), self.inputs[0].data.image)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _merged_meta(self) -> dict[str, Any]:
        """Union of every connected input's :class:`IoMeta`.

        Later-declared inputs win on key collisions so the clock's
        per-tick ``frame_index`` overrides the held image's stale one.
        """
        merged: dict[str, Any] = {}
        for port in self._inputs:
            if port.has_data:
                merged.update(dict(port.data.meta))
        return merged

    def _scalar_inputs_as_context(self) -> dict[str, Any]:
        """Expose every connected SCALAR input as a ``$<port_name>$``
        token in the templating context.

        The actual scalar value (extracted from the 0-d numpy payload)
        becomes the token's value, so a ``tick`` port driven by a
        ``RangeSource(1..10)`` resolves ``$tick$`` to 1, 2, …, 10
        rather than the port's 0-based emit counter.
        """
        ctx: dict[str, Any] = {}
        for port in self._inputs:
            if not port.has_data:
                continue
            if port.data.type is not IoDataType.SCALAR:
                continue
            ctx[port.name] = port.data.payload.item()
        return ctx

    def _resolved_template(
        self,
        meta: dict[str, Any],
        context: dict[str, Any],
    ) -> Path:
        """Expand the user's template against *meta* + *context*, then
        resolve relative paths against :data:`OUTPUT_DIR`.

        ``output_path`` is a :class:`Path` after the param descriptor
        coerces it; the engine works on strings so we round-trip via
        ``str``.
        """
        rendered = expand_template(str(self._output_path), meta, context)
        return resolve_against(Path(rendered), OUTPUT_DIR)
