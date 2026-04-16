from __future__ import annotations

import os
from enum import Enum

import cv2
from typing_extensions import override

from core.io_data import IoDataType
from core.node_base import SinkNodeBase, NodeParam, NodeParamType
from core.port import InputPort


class OutputFormat(Enum):
    SAME_AS_INPUT = 0
    PNG = 1


class FileSink(SinkNodeBase):
    def __init__(self):
        super().__init__("File Sink", section="Sinks")

        self._output_path: str = "output/out.png"
        self._output_format: OutputFormat = OutputFormat.SAME_AS_INPUT

        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        # Sync attributes with declared NodeParam defaults; see
        # NodeBase._apply_default_params for rationale.
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [NodeParam("output_path", NodeParamType.FILE_PATH, {"default": "output/out.png", "mode": "save"})]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def output_format(self) -> OutputFormat:
        return self._output_format

    @output_format.setter
    def output_format(self, output_format: OutputFormat) -> None:
        self._output_format = output_format

    @property
    def output_path(self) -> str:
        return self._output_path

    @output_path.setter
    def output_path(self, output_path: str) -> None:
        self._output_path = output_path

    # ── SinkNodeBase interface ──────────────────────────────────────────────────

    @override
    def process(self) -> None:
        file_name, file_ext = os.path.splitext(self._output_path)

        if self._output_format == OutputFormat.SAME_AS_INPUT:
            output = file_name + file_ext
        elif self._output_format == OutputFormat.PNG:
            output = file_name + ".png"
        else:
            raise ValueError(f"Unsupported output format: {self._output_format}")

        cv2.imwrite(output, self.inputs[0].data.image)
