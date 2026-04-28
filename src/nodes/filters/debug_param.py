from __future__ import annotations

from enum import IntEnum

from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import (
    BoolParam,
    EnumParam,
    FilePathParam,
    FloatParam,
    IntParam,
    StringParam,
)
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

    file_path = FilePathParam(
        "",
        filter="All files (*)",
        base_dir=INPUT_DIR,
        description="Demo FILE_PATH parameter — exercises the path widget.",
    )
    count = IntParam(0, description="Demo INT parameter — exercises the int spinbox widget.")
    factor = FloatParam(1.0, description="Demo FLOAT parameter — exercises the float spinbox widget.")
    label = StringParam(
        "",
        placeholder="text…",
        description="Demo STRING parameter — exercises the line-edit widget.",
    )
    enabled = BoolParam(False, description="Demo BOOL parameter — exercises the checkbox widget.")
    mode = EnumParam(
        DebugMode,
        DebugMode.ALPHA,
        description="Demo ENUM parameter — exercises the combo-box widget.",
    )

    def __init__(self) -> None:
        super().__init__("Debug Params", section="Debug")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        self.outputs[0].send(self.inputs[0].data)
