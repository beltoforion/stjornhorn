from __future__ import annotations

import pandas as pd
from typing_extensions import override

from core.dynamic_ports import MAX_DYNAMIC_INPUTS, DynamicInputGroup
from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import StringParam
from core.port import OutputPort


#: Stable key under which JoinDatasets publishes its dynamic input
#: group in the saved-flow JSON. Renaming would invalidate every
#: previously-saved flow that loaded a JoinDatasets node, so treat
#: this string as on-disk schema.
_DATASET_GROUP_KEY: str = "dataset"


class JoinDatasets(NodeBase):
    """Merge two or more :data:`IoDataType.DATASET` inputs into one.

    The node starts with a single ``dataset[1]`` input. Whenever the
    tail input is wired to an upstream, a fresh empty ``dataset[N+1]``
    appears below it, up to a hard cap of nine — past that, the user
    has almost certainly modeled themselves into a corner that a
    different topology would solve more cleanly.

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
        constant=True,
        description=(
            "Comma-separated list of new names for the first column of each "
            "connected input. Required when multiple inputs share the same "
            "column name (e.g. all named 'c0' from CsvSource)."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Join Datasets", section="Data")
        self._dataset_group = DynamicInputGroup(
            self,
            name_template="dataset[{i}]",
            accepted_types={IoDataType.DATASET},
            max_count=MAX_DYNAMIC_INPUTS,
        )
        self._dynamic_input_groups: dict[str, DynamicInputGroup] = {
            _DATASET_GROUP_KEY: self._dataset_group,
        }
        self._add_output(OutputPort("dataset", {IoDataType.DATASET}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        connected = [p for p in self._dataset_group.ports if p.has_data]
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
