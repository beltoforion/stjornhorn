from __future__ import annotations

import numpy as np
import pandas as pd
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import FloatParam, StringParam
from core.port import InputPort, OutputPort


class AddIndexColumn(NodeBase):
    """Prepend a synthetic numeric column to a :data:`IoDataType.DATASET`.

    Useful when a downstream renderer (``PlotXY``, ``Hodogram``)
    needs an explicit X axis but the DATASET has no natural one (e.g.
    a one-column trace from ``CsvSource``). The new column is
    inserted at position 0 so it becomes the default X. Set
    ``step = 1 / sample_rate`` to produce a time axis in seconds.
    """

    name = StringParam(
        "index",
        max_length=64,
        description=(
            "Name for the new index column. Inserted at position 0 "
            "so it becomes the default X axis downstream."
        ),
    )
    start = FloatParam(
        0.0,
        description="First value of the index.",
    )
    step = FloatParam(
        1.0,
        min=0.0,
        min_exclusive=True,
        description=(
            "Increment per row. Use 1.0 for sample numbers, "
            "1/sample_rate for a time axis in seconds."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Add Index Column", section="Data")
        self._add_input(InputPort("dataset", {IoDataType.DATASET}))
        self._add_output(OutputPort("dataset", {IoDataType.DATASET}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        df: pd.DataFrame = self.inputs[0].data.payload

        if self._name in df.columns:
            raise ValueError(
                f"Cannot add index column {self._name!r}: "
                f"a column with that name already exists "
                f"in the input dataset (columns: {list(df.columns)})"
            )

        n = len(df)
        index_values = self._start + np.arange(n) * self._step

        new_df = df.copy()
        new_df.insert(0, self._name, index_values)
        # ``DataFrame.copy`` preserves ``.attrs`` in modern pandas, but
        # be explicit about it — the metadata channel is the whole
        # reason ``DATASET`` exists as a typed payload, and a regression
        # here would silently strip ``sample_rate`` and friends.
        new_df.attrs = dict(df.attrs)
        self.outputs[0].send(IoData.from_dataset(new_df))
