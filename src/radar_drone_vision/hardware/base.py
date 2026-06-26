"""Abstract base interface for radar hardware devices."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class RadarFrame:
    """A single radar frame captured from a device.

    Attributes
    ----------
    timestamp_ns : int
        Capture timestamp in nanoseconds.
    frame_id : int
        Sequential frame identifier.
    iq : np.ndarray or None
        Raw I/Q samples, shape depends on device configuration.
    adc : np.ndarray or None
        Raw ADC samples (before IQ demodulation).
    range_doppler : np.ndarray or None
        Pre-computed range-Doppler heatmap from the device.
    point_cloud : np.ndarray or None
        3-D point cloud, shape ``(n_points, 4+)`` with columns
        ``[x, y, z, doppler, ...]``.
    metadata : dict
        Arbitrary device-specific metadata.
    """

    timestamp_ns: int
    frame_id: int
    iq: Optional[np.ndarray] = None
    adc: Optional[np.ndarray] = None
    range_doppler: Optional[np.ndarray] = None
    point_cloud: Optional[np.ndarray] = None
    metadata: dict = field(default_factory=dict)

    @property
    def timestamp_s(self) -> float:
        """Timestamp in seconds."""
        return self.timestamp_ns / 1e9


class RadarDevice(ABC):
    """Abstract interface for radar hardware devices.

    All concrete device drivers must implement ``connect``, ``disconnect``,
    ``read_frame``, and ``get_metadata``.
    """

    _connected: bool = False

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the radar device."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the radar device."""
        ...

    @abstractmethod
    def read_frame(self) -> RadarFrame:
        """Read a single radar frame.

        Returns
        -------
        frame : RadarFrame

        Raises
        ------
        ConnectionError
            If the device is not connected.
        TimeoutError
            If the read times out.
        """
        ...

    @abstractmethod
    def get_metadata(self) -> dict:
        """Return device metadata (model, firmware, config, etc.)."""
        ...

    @property
    def is_connected(self) -> bool:
        """Whether the device connection is active."""
        return self._connected
