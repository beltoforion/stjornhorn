from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParamType
from core.port import InputPort, OutputPort

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


class Ncc(NodeBase):
    """Normalised cross-correlation template matching.

    Wraps ``cv2.matchTemplate`` with ``TM_CCORR_NORMED`` and rescales the
    score map to a ``uint8`` greyscale image. The template is loaded from
    disk via the ``template`` file-path parameter; a colour template is
    converted to greyscale once at ``before_run`` time so the conversion
    cost is paid a single time per run, not per frame. The ``image``
    input is single-channel greyscale and the output is always greyscale.

    With ``retain_size=True`` (default) the match map is pasted into a
    canvas the same size as ``image`` and offset by half the template
    size, so each response sits at the pixel it corresponds to (template
    centre). With ``retain_size=False`` the raw ``matchTemplate`` output
    is emitted, which is smaller than the input by ``template.shape - 1``
    on each axis.
    """

    def __init__(self) -> None:
        super().__init__("NCC", section="Processing")
        self._retain_size: bool = True
        self._template_path: Path = Path()
        self._template: np.ndarray | None = None

        self._add_input(InputPort("image", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort(
            "template",
            {IoDataType.PATH},
            optional=True,
            default_value="pad.jpg",
            metadata={"default": "pad.jpg", "filter": "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)", "base_dir": INPUT_DIR, "param_type": NodeParamType.FILE_PATH},
        ))
        self._add_input(InputPort(
            "retain_size",
            {IoDataType.BOOL},
            optional=True,
            default_value=True,
            metadata={"default": True, "param_type": NodeParamType.BOOL},
        ))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def retain_size(self) -> bool:
        return self._retain_size

    @retain_size.setter
    def retain_size(self, value: bool) -> None:
        self._retain_size = bool(value)

    @property
    def template(self) -> Path:
        return self._template_path

    @template.setter
    def template(self, path: str | Path) -> None:
        p = Path(path)
        if p.is_absolute():
            try:
                p = p.resolve().relative_to(INPUT_DIR.resolve())
            except (OSError, ValueError):
                pass  # outside INPUT_DIR — keep absolute
        self._template_path = p

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        self._template = self._load_template()

    @override
    def process_impl(self) -> None:
        if self._template is None:
            # before_run wasn't called (e.g. direct unit-test use); load lazily.
            self._template = self._load_template()

        image: np.ndarray = self.inputs[0].data.image
        template = self._template

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
        if self._template_path.is_absolute():
            return self._template_path
        return INPUT_DIR / self._template_path

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
