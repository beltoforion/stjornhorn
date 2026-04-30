from __future__ import annotations

import pandas as pd
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import StringParam
from core.port import InputPort, OutputPort

#: Maximum number of DATASET inputs the node exposes.
_MAX_INPUTS: int = 4


class JoinDatasets(NodeBase):
    """Merge up to four :data:`IoDataType.DATASET` inputs into one.

    Each connected input contributes its columns to the output. The
    optional ``column_names`` is a comma-separated rename list applied
    to the **first column of each input** before joining — useful when
    several single-column sources all carry the same generic name
    (e.g. ``c0``). Empty keeps original names (which must then be
    distinct). ``df.attrs`` from the first connected input is
    forwarded.
    """

    column_names = StringParam(
        "",
        placeholder="(keep original names)",
        description=(
            "Comma-separated list of new names for the first column of each "
            "connected input. Required when multiple inputs share the same "
            "column name (e.g. all named 'c0' from CsvSource)."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Join Datasets", section="Data")
        for i in range(_MAX_INPUTS):
            self._add_input(InputPort(f"dataset_{i + 1}", {IoDataType.DATASET}, optional=True))
        self._add_output(OutputPort("dataset", {IoDataType.DATASET}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        connected = [p for p in self.inputs if p.has_data]
        if len(connected) < 2:
            return  # not enough data yet — wait for more inputs

        rename_list = self._parse_column_names()

        frames: list[pd.DataFrame] = []
        for i, port in enumerate(connected):
            df: pd.DataFrame = port.data.payload.copy()
            if i < len(rename_list) and rename_list[i]:
                old_name = str(df.columns[0])
                df = df.rename(columns={old_name: rename_list[i]})
            frames.append(df)

        self._check_no_collisions(frames)

        result = pd.concat(frames, axis=1)
        result.attrs = dict(frames[0].attrs)
        self.outputs[0].send(IoData.from_dataset(result))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_column_names(self) -> list[str]:
        """Return the trimmed rename list; empty string = no rename for that slot."""
        raw = self._column_names.strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(",")]

    @staticmethod
    def _check_no_collisions(frames: list[pd.DataFrame]) -> None:
        seen: set[str] = set()
        for df in frames:
            for col in df.columns:
                col_str = str(col)
                if col_str in seen:
                    raise ValueError(
                        f"Column name collision: {col_str!r} appears in more than one "
                        f"input. Use the 'column_names' parameter to rename inputs before "
                        f"joining."
                    )
                seen.add(col_str)
