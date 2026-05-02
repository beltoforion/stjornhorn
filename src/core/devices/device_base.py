from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class DeviceParamType(Enum):
    """Enumeration of parameter types for device parameters."""
    INT = 2,
    FLOAT = 3,
    STRING = 4,
    BOOL = 5


class DeviceParam:

    def __init__(
        self,
        name: str,
        param_type: DeviceParamType,
        default: object = None,
        metadata: dict | None = None
    ) -> None:
        self.name: str = name

        # Stash the full metadata bundle the widgets read, with
        # ``param_type`` and ``default`` mirrored into it so the
        # widget builder's ``port.metadata.get("param_type")``
        # dispatch path keeps working unchanged.
        meta = dict(metadata) if metadata else {}
        meta.setdefault("param_type", param_type)
        meta.setdefault("default", default)

        self.metadata: dict = meta
        self.default_value: object = default



class DeviceBase(ABC):
    """Abstract base for devices. """
    
    def __init__(self, display_name: str, section: str | None = None) -> None:
        self.display_name = display_name
        self.section = section
        self._params: list[DeviceParam] = []

    def _add_param(self, param: DeviceParam) -> None:
        self._params.append(param)

   # ── Public accessors ───────────────────────────────────────────────────────

    @property
    def params(self) -> list[DeviceParam]:
        return list(self._params)

   # ── Abstract Methods ───────────────────────────────────────────────────────

    @abstractmethod
    def initialize(self) -> None:
        """ Initialize the device. Should perform any necessary setup and resource
            allocation.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """ Shutdown the device. Should perform any necessary cleanup and resource
            deallocation. Default implementation does nothing.
        """


class SourceMeasureUnitBase(DeviceBase):
    """Abstract base for source measure units. """

    def __init__(self, display_name: str) -> None:
        super().__init__(display_name, "Source Measure Units")


class CameraDeviceBase(DeviceBase):
    """Abstract base for camera devices. """

    def __init__(self, display_name: str) -> None:
        super().__init__(display_name, "Cameras") 

    @abstractmethod
    def capture_frame(self) -> bytes:
        """Capture a single frame and return it as raw bytes. The format
        of the bytes (e.g. RGB, RGBA, YUV) is device-specific and not
        specified by this interface.
        """


class OpenCvCamera(CameraDeviceBase):
    """Camera device that captures frames using OpenCV. """

    def __init__(self, device_index: int) -> None:
        super().__init__("OpenCvCamera")
        self.device_index = device_index