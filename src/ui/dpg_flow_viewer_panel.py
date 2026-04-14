from __future__ import annotations

import logging

import cv2
import dearpygui.dearpygui as dpg
import numpy as np

from core.io_data import IoDataType
from core.node_base import NodeBase
from ui._types import DpgTag

logger = logging.getLogger(__name__)

# Upper bound for the texture uploaded to DPG. Larger images are
# downsampled preserving aspect ratio so 4K frames do not hammer VRAM.
_MAX_TEXTURE_DIM: int = 1024

# Horizontal padding subtracted from the panel width when computing the
# target image width (accounts for the scroll-bar and child-window border).
_PANEL_H_PADDING: int = 24


class DpgFlowViewerPanel:
    """Bottom-of-editor viewer that renders every image output of a node.

    Call :meth:`show` with the currently-selected ``NodeBase`` (or ``None``).
    The panel clears itself and re-creates one labelled ``dpg.add_image``
    per ``IoDataType.IMAGE`` output port that has data cached on it.

    The caller is responsible for creating the panel inside an active DPG
    container; the panel itself owns its child window so its parent just
    needs to exist.
    """

    def __init__(self, parent: DpgTag, *, height: int) -> None:
        self._container_tag: DpgTag = dpg.generate_uuid()
        self._texture_registry_tag: DpgTag = dpg.generate_uuid()
        self._texture_tags: list[DpgTag] = []
        self._current_node: NodeBase | None = None

        # Textures live in a dedicated registry so they can be wiped
        # without touching any other DPG texture state in the app.
        with dpg.texture_registry(tag=self._texture_registry_tag):
            pass

        with dpg.child_window(
            tag=self._container_tag,
            parent=parent,
            width=-1,
            height=height,
            border=True,
        ):
            dpg.add_text("(select a node to view its output)", color=(120, 120, 120, 255))

    # ── Public API ─────────────────────────────────────────────────────────────

    def show(self, node: NodeBase | None) -> None:
        """Render every image output of ``node`` in the panel.

        Non-image outputs are shown as a small placeholder line. If no
        data has been emitted yet, a hint is shown instead of the image.
        """
        self._current_node = node
        self._clear()

        if node is None:
            dpg.add_text("(select a node to view its output)",
                         color=(120, 120, 120, 255),
                         parent=self._container_tag)
            return

        if not node.outputs:
            dpg.add_text(f"{node.display_name}: node has no outputs",
                         color=(120, 120, 120, 255),
                         parent=self._container_tag)
            return

        panel_w = max(64, dpg.get_item_rect_size(self._container_tag)[0] - _PANEL_H_PADDING)

        for port in node.outputs:
            if IoDataType.IMAGE not in port.emits:
                dpg.add_text(f"{port.name}: (non-image output)",
                             color=(120, 120, 120, 255),
                             parent=self._container_tag)
                continue

            data = port.last_emitted
            if data is None or data.is_end_of_stream() or data.type != IoDataType.IMAGE:
                dpg.add_text(f"{port.name}: (no data — click Run)",
                             color=(120, 120, 120, 255),
                             parent=self._container_tag)
                continue

            try:
                self._render_image(port.name, data.image, panel_w)
            except Exception:
                logger.exception("Viewer failed to render port '%s'", port.name)
                dpg.add_text(f"{port.name}: (render error — see log)",
                             color=(220, 80, 80, 255),
                             parent=self._container_tag)

    def refresh(self) -> None:
        """Re-render the currently-shown node. Call this after a flow run."""
        self.show(self._current_node)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _render_image(self, label: str, image: np.ndarray, panel_width: int) -> None:
        # OpenCV produces BGR or grayscale arrays; DPG expects RGBA float32.
        rgba = self._to_rgba(image)

        h, w = rgba.shape[:2]
        # Downsample oversized images so the GPU upload stays cheap. The
        # aspect ratio is preserved; the final on-screen width is set
        # separately below via the add_image call.
        max_dim = max(h, w)
        if max_dim > _MAX_TEXTURE_DIM:
            scale = _MAX_TEXTURE_DIM / max_dim
            rgba = cv2.resize(rgba, (max(1, int(w * scale)), max(1, int(h * scale))),
                              interpolation=cv2.INTER_AREA)
            h, w = rgba.shape[:2]

        tex_data = (rgba.astype(np.float32) / 255.0).flatten()
        tex_tag = dpg.add_raw_texture(
            width=w,
            height=h,
            default_value=tex_data,
            format=dpg.mvFormat_Float_rgba,
            parent=self._texture_registry_tag,
        )
        self._texture_tags.append(tex_tag)

        # Fit-to-width: scale to the panel's current inner width, preserving
        # aspect ratio. Don't upscale beyond the texture's native size.
        display_w = min(panel_width, w)
        display_h = max(1, round(display_w * (h / w)))

        dpg.add_text(f"{label}  ({w}×{h})", parent=self._container_tag)
        dpg.add_image(tex_tag, width=display_w, height=display_h, parent=self._container_tag)
        dpg.add_spacer(height=6, parent=self._container_tag)

    @staticmethod
    def _to_rgba(image: np.ndarray) -> np.ndarray:
        """Coerce a NumPy image to a uint8 RGBA array (H, W, 4)."""
        if image.dtype != np.uint8:
            # Normalise floats / ints into 0..255 uint8 before colour conversion.
            image = np.clip(image, 0, 255).astype(np.uint8)

        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2RGBA)
        if image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2RGBA)
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
        raise ValueError(f"Unsupported image shape {image.shape}")

    def _clear(self) -> None:
        for child in list(dpg.get_item_children(self._container_tag, 1) or []):
            if dpg.does_item_exist(child):
                dpg.delete_item(child)
        for tex in self._texture_tags:
            if dpg.does_item_exist(tex):
                dpg.delete_item(tex)
        self._texture_tags.clear()
