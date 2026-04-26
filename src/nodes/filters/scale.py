from __future__ import annotations

from enum import IntEnum

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoDataType
from core.node_base import NodeBase, NodeParamType
from core.port import InputPort, OutputPort


class Interpolation(IntEnum):
    """Resampling method used by :class:`Scale`.

    Values mirror the corresponding ``cv2.INTER_*`` flags exactly so the
    enum member can be passed straight into :func:`cv2.resize` without a
    lookup table. Backed by :class:`IntEnum` so the integer
    representation (persisted in saved flows) round-trips cleanly: JSON
    stores the int, the setter accepts both ints and enum members, and
    the ``ENUM`` param widget renders a combo box of ``name``-based
    labels.
    """
    NEAREST   = cv2.INTER_NEAREST
    LINEAR    = cv2.INTER_LINEAR
    CUBIC     = cv2.INTER_CUBIC
    AREA      = cv2.INTER_AREA
    LANCZOS4  = cv2.INTER_LANCZOS4


class Scale(NodeBase):
    """Resize an image by a percentage factor.

    The input is resized by ``scale_percent`` (100 = no change). Ported
    from the original OCVL ``ScaleProcessor`` — the target-size mode is
    omitted here because there is no tuple param type; if an absolute
    size is needed, compute the matching scale factor.
    """

    def __init__(self) -> None:
        super().__init__("Scale", section="Transform")
        self._scale_percent: int = 100
        self._interpolation: Interpolation = Interpolation.LINEAR

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_input(InputPort(
            "scale_percent",
            {IoDataType.SCALAR},
            optional=True,
            default_value=100,
            metadata={"default": 100, "param_type": NodeParamType.INT},
        ))
        self._add_input(InputPort(
            "interpolation",
            {IoDataType.ENUM},
            optional=True,
            default_value=Interpolation.LINEAR,
            metadata={
                "default": Interpolation.LINEAR,
                "enum": Interpolation,
                "param_type": NodeParamType.ENUM,
            },
        ))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def scale_percent(self) -> int:
        return self._scale_percent

    @scale_percent.setter
    def scale_percent(self, value: int) -> None:
        v = int(value)
        if v <= 0:
            raise ValueError(f"scale_percent must be > 0 (got {v})")
        self._scale_percent = v

    @property
    def interpolation(self) -> Interpolation:
        return self._interpolation

    @interpolation.setter
    def interpolation(self, value: int | Interpolation) -> None:
        try:
            # Interpolation(int) validates the integer and raises on unknown
            # values; passing an Interpolation member just returns itself.
            self._interpolation = Interpolation(value)
        except ValueError as e:
            raise ValueError(
                f"interpolation must be one of {[m.value for m in Interpolation]} (got {value!r})"
            ) from e

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        h, w = image.shape[:2]
        factor = self._scale_percent / 100.0
        new_w = max(1, int(round(w * factor)))
        new_h = max(1, int(round(h * factor)))

        resized = cv2.resize(
            image,
            (new_w, new_h),
            interpolation=int(self._interpolation),
        )
        self.outputs[0].send(in_data.with_image(resized))
