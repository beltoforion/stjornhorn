from __future__ import annotations

from enum import IntEnum
from pathlib import Path

from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class DebugMode(IntEnum):
    """Dummy enum used by :class:`DebugParam` to exercise the ENUM widget."""
    ALPHA = 1
    BETA  = 2
    GAMMA = 3


class DebugParam(NodeBase):
    """Debug node that declares one parameter of every known type.

    Has no effect on its input — the image is passed straight through.
    Exists so every :class:`NodeParamType` can be rendered, edited, saved
    and loaded through a single node, which is convenient for exercising
    the param-widget code paths during development.
    """

    def __init__(self) -> None:
        super().__init__("Debug Params", section="Debug")

        self._file_path: Path = Path()
        self._count:     int   = 0
        self._factor:    float = 1.0
        self._label:     str   = ""
        self._enabled:   bool  = False
        self._mode:      DebugMode = DebugMode.ALPHA

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam(
                "file_path",
                NodeParamType.FILE_PATH,
                {"default": "", "mode": "open", "filter": "All files (*)", "base_dir": INPUT_DIR},
            ),
            NodeParam("count",   NodeParamType.INT,    {"default": 0}),
            NodeParam("factor",  NodeParamType.FLOAT,  {"default": 1.0}),
            NodeParam("label",   NodeParamType.STRING, {"default": "", "placeholder": "text…"}),
            NodeParam("enabled", NodeParamType.BOOL,   {"default": False}),
            NodeParam(
                "mode",
                NodeParamType.ENUM,
                {"default": DebugMode.ALPHA, "enum": DebugMode},
            ),
        ]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def file_path(self) -> Path:
        return self._file_path

    @file_path.setter
    def file_path(self, value: str | Path) -> None:
        self._file_path = Path(value)

    @property
    def count(self) -> int:
        return self._count

    @count.setter
    def count(self, value: int) -> None:
        self._count = int(value)

    @property
    def factor(self) -> float:
        return self._factor

    @factor.setter
    def factor(self, value: float) -> None:
        self._factor = float(value)

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str) -> None:
        self._label = str(value)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def mode(self) -> DebugMode:
        return self._mode

    @mode.setter
    def mode(self, value: int | DebugMode) -> None:
        self._mode = DebugMode(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        self.outputs[0].send(self.inputs[0].data)
