from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import BoolParam, FilePathParam
from core.path_utils import resolve_against
from core.port import InputPort, OutputPort

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


class Ncc(NodeBase):
    """Normalised cross-correlation template matching.

    Searches for ``template`` in the ``image`` input and emits the
    normalised response as a uint8 greyscale image. Both inputs are
    single-channel greyscale; a colour template file is reduced to
    greyscale on load.

    With ``retain_size=True`` (default) each response sits at the
    pixel of the template centre on a canvas matching the input size.
    With ``retain_size=False`` the raw response map is emitted —
    smaller than the input by ``template.shape - 1`` on each axis.
    """

    template = FilePathParam(
        "pad.jpg",
        filter="Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)",
        base_dir=INPUT_DIR,
        description="Path to the template image to search for.",
    )
    retain_size = BoolParam(
        True,
        description=(
            "When on, each response sits at the template-centre "
            "pixel on a canvas matching the input size. When off, "
            "the raw response is emitted (smaller than the input by "
            "template size minus one on each axis)."
        ),
    )

    def __init__(self) -> None:
        super().__init__("NCC", section="Processing")
        # Loaded template image (lazy — populated by before_run /
        # process_impl). Distinct slot from ``self._template`` (which
        # is the descriptor's ``Path`` storage) so the two don't
        # collide.
        self._template_image: np.ndarray | None = None

        self._add_input(InputPort("image", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))
        self._apply_default_params()

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        self._template_image = self._load_template()

    @override
    def process_impl(self) -> None:
        if self._template_image is None:
            # before_run wasn't called (e.g. direct unit-test use); load lazily.
            self._template_image = self._load_template()

        image: np.ndarray = self.inputs[0].data.image
        template = self._template_image

        res = cv2.matchTemplate(image, template, cv2.TM_CCORR_NORMED)
        res = cv2.normalize(
            (res * 255).astype(np.uint8),
            None,
            alpha=0,
            beta=255,
            norm_type=cv2.NORM_MINMAX,
        )

        if self._retain_size:
            h_t, w_t = template.shape[:2]
            h_orig, w_orig = image.shape[:2]
            h_m, w_m = res.shape[:2]

            y0 = h_t // 2
            x0 = w_t // 2

            canvas = np.zeros((h_orig, w_orig), dtype=np.uint8)
            canvas[y0:y0 + h_m, x0:x0 + w_m] = res
            out = canvas
        else:
            out = res

        self.outputs[0].send(IoData.from_greyscale(out))

    # ── Internals ──────────────────────────────────────────────────────────────

    def _resolved_template_path(self) -> Path:
        return resolve_against(self._template, INPUT_DIR)

    def _load_template(self) -> np.ndarray:
        resolved = self._resolved_template_path()
        if not resolved.exists():
            raise FileNotFoundError(f"NCC template not found: {resolved}")

        ext = resolved.suffix.lower()
        if ext not in _SUPPORTED_EXTS:
            raise ValueError(
                f"Unsupported template file type '{ext}'. "
                f"Supported: {_SUPPORTED_EXTS}"
            )

        # cv2.imread() silently fails on Unicode paths on Windows; use
        # np.fromfile + imdecode to go through Python's wide-char I/O.
        img_array = np.fromfile(resolved, dtype=np.uint8)
        template = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
        if template is None:
            raise OSError(f"cv2 could not read template: {resolved}")

        if template.ndim == 3:
            channels = template.shape[2]
            if channels == 4:
                template = cv2.cvtColor(template, cv2.COLOR_BGRA2GRAY)
            elif channels == 3:
                template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            else:
                template = template[:, :, 0]

        return template
