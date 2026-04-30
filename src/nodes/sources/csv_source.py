from __future__ import annotations

from pathlib import Path

import pandas as pd
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType, IoMeta
from core.node_base import SourceNodeBase
from core.params import BoolParam, FilePathParam, StringParam
from core.path_utils import resolve_against
from core.port import OutputPort

#: Literal "\t" (two chars: backslash + t) that the user can type into
#: the delimiter line-edit when they need a real tab. The widget can't
#: easily emit a real tab character, so we expand the escape ourselves.
_TAB_ESCAPE: str = "\\t"

#: Lines beginning with this character are skipped when reading the CSV.
#: Hard-coded rather than configurable so file formats that put a metadata
#: line on top (e.g. seismic ASCII traces with a ``# stat … samp …`` header,
#: gnuplot output, many instrument-log dumps) load without a node-level
#: parameter twist. Free-form ``#`` comments inside the data section are
#: vanishingly rare; opt-out can be added later via a param if a real
#: file demands it.
_COMMENT_CHAR: str = "#"


class CsvSource(SourceNodeBase):
    """Source node that reads a CSV file as an :data:`IoDataType.DATASET`.

    First end-to-end producer of the new ``DATASET`` payload — load any
    CSV (seismic export, instrument log, simulation output, …) and the
    rest of the data-flow nodes pick it up. The DataFrame's columns
    identify channels and ``df.attrs["source_path"]`` records the
    resolved file path so downstream nodes can include it in error
    messages or UI hints.

    Paths inside :data:`constants.INPUT_DIR` are stored — and therefore
    displayed — relative to that folder, so saved flows stay portable
    across machines that share the same input layout. Paths outside
    are kept absolute. Resolution back to an absolute path happens at
    run time.

    This source is *reactive*: editing any parameter re-runs the flow
    immediately, matching :class:`~nodes.sources.image_source.ImageSource`'s
    UX.

    Lines beginning with ``#`` are always skipped, so files that lead
    with a metadata header line (seismic ASCII traces with
    ``# stat … samp …``, gnuplot output, many instrument-log dumps)
    load without any extra configuration — the data section starts on
    the first non-``#`` line.

    Parameters:
      file_path  -- path to the CSV (relative to INPUT_DIR when possible).
      delimiter  -- column separator. Default ``","``. Type ``\\t`` for
                    a tab; ``;`` for European-style CSVs is supported
                    natively.
      has_header -- when True (default), the first row is treated as
                    column names. When False, columns get synthetic
                    ``c0``, ``c1``, … names so downstream column
                    selectors still have something to bind to.
      decimal    -- decimal separator inside numeric cells. Default
                    ``"."``; set to ``","`` for European decimals.
    """

    file_path = FilePathParam(
        "data.csv",
        constant=True,
        filter="CSV (*.csv);;Text (*.txt);;All files (*)",
        base_dir=INPUT_DIR,
        description=(
            "Path to the CSV file. Paths inside the input folder are "
            "stored relative to it so the flow stays portable."
        ),
    )

    delimiter = StringParam(
        ",",
        constant=True,
        max_length=4,
        description=(
            "Column separator. Default is comma. Type \\t for a tab, "
            "or ; for European-style CSVs."
        ),
    )

    has_header = BoolParam(
        True,
        constant=True,
        description=(
            "When checked, the first row is read as column names. "
            "Otherwise columns are auto-named c0, c1, c2, …"
        ),
    )

    decimal = StringParam(
        ".",
        constant=True,
        max_length=1,
        description=(
            "Decimal separator inside numeric cells. Set to ',' for "
            "European decimals; defaults to '.'."
        ),
    )

    def __init__(self) -> None:
        super().__init__("CSV Source", section="Sources")
        self._add_output(OutputPort("dataset", {IoDataType.DATASET}))
        self._apply_default_params()

    @property
    @override
    def is_reactive(self) -> bool:
        return True

    @override
    def process_impl(self) -> None:
        resolved = self._resolved_path()
        if not resolved.exists():
            raise FileNotFoundError(f"CSV file not found: {resolved}")

        sep = self._delimiter.replace(_TAB_ESCAPE, "\t") if self._delimiter else ","
        header_row: int | None = 0 if self._has_header else None

        df = pd.read_csv(
            resolved,
            sep=sep,
            header=header_row,
            decimal=self._decimal,
            comment=_COMMENT_CHAR,
        )

        if not self._has_header:
            # pandas auto-assigns 0,1,2,... as column names when
            # header=None; rename to c0,c1,c2 so a downstream
            # SelectColumns node can bind to something more meaningful
            # than a bare integer.
            df.columns = [f"c{i}" for i in range(len(df.columns))]

        df.attrs["source_path"] = str(resolved)
        self.outputs[0].send(
            IoData.from_dataset(df, meta=IoMeta(source_path=resolved))
        )

    def _resolved_path(self) -> Path:
        """Return an absolute path; relative values are joined with INPUT_DIR."""
        return resolve_against(self._file_path, INPUT_DIR)
