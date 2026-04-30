from __future__ import annotations

from typing_extensions import override

from core.io_data import IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class ThrowException(NodeBase):
    """Debug node that raises a RuntimeError whenever it processes.

    Use during development to exercise the pipeline's exception path
    (status bar message, log entry, run abort). The output is never
    produced because the node always raises before sending.
    """

    def __init__(self) -> None:
        super().__init__("Throw Exception", section="Debug")
        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

    @override
    def process_impl(self) -> None:
        raise RuntimeError(
            "Throw Exception node: intentional failure triggered to exercise "
            "the pipeline's exception-handling path.\n"
            "This is line two of the message, long enough to make sure the "
            "status bar truncates it and the tooltip shows the full text.\n"
            "Line three carries more filler so the log entry wraps across "
            "several lines and proves that multi-line messages render correctly.\n"
            "Line four: if you are reading this in the UI, the Throw Exception "
            "node is working exactly as intended — there is no bug to fix here."
        )
