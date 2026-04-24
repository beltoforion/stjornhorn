"""Regression tests for source-node path normalization.

Both :class:`ImageSource` and :class:`VideoSource` are expected to
store paths under :data:`INPUT_DIR` as bare relative names (so saved
flows port cleanly across machines) and to resolve those relative
names against ``INPUT_DIR`` at run time. The two used to diverge —
``VideoSource`` persisted absolute paths and resolved relatives
against ``cwd`` — so the behaviour is locked down here for both
nodes in parallel to keep them from drifting again.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from constants import INPUT_DIR
from nodes.sources.image_source import ImageSource
from nodes.sources.video_source import VideoSource


@pytest.fixture(params=[ImageSource, VideoSource])
def source(request):
    """Run the same behavioural contract against every file-based source."""
    return request.param()


def test_absolute_path_under_input_dir_is_stored_relative(source) -> None:
    """Picking a file under INPUT_DIR strips the INPUT_DIR prefix so the
    saved flow carries a short, portable name rather than the host path.
    """
    absolute = (INPUT_DIR / "clip.bin").resolve()
    source.file_path = absolute
    assert source.file_path == Path("clip.bin")
    assert not source.file_path.is_absolute()


def test_absolute_path_outside_input_dir_is_kept_absolute(
    tmp_path: Path, source,
) -> None:
    """Paths that can't be made relative to INPUT_DIR stay absolute —
    relative_to() would raise ValueError and should be swallowed.
    """
    outside = (tmp_path / "elsewhere.bin").resolve()
    source.file_path = outside
    assert source.file_path == outside
    assert source.file_path.is_absolute()


def test_bare_relative_name_resolves_against_input_dir(source) -> None:
    """A bare filename on the setter is left relative, and the node's
    internal resolver joins it with INPUT_DIR — never with cwd.
    """
    source.file_path = "clip.bin"
    assert source.file_path == Path("clip.bin")
    resolved = source._resolved_path()
    assert resolved == INPUT_DIR / "clip.bin"
