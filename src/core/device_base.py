from __future__ import annotations

from abc import ABC, abstractmethod


class DeviceBase(ABC):
    """Abstract base for devices. """
    
    def __init__(self, display_name: str, section: str | None = None) -> None:
        self.display_name = display_name
        self.section = section


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