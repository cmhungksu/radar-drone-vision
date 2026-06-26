"""Base data structures for radar datasets."""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class RadarSample:
    """A single radar measurement sample.

    Attributes:
        sample_id: Unique identifier for this sample.
        signal: Raw or processed signal array (1-D IQ, 2-D spectrogram, etc.).
        label: Human-readable class name (e.g. 'drone_DJI_M600', 'bird').
        label_binary: Binary label: 1 = UAV, 0 = non-UAV.
        radar_type: Radar waveform type (e.g. 'fmcw', 'cw').
        carrier_frequency_hz: Carrier frequency in Hz.
        raw_shape: Original shape of the signal before any reshaping.
        metadata: Arbitrary extra fields (split, source file, etc.).
    """

    sample_id: str
    signal: np.ndarray
    label: str
    label_binary: int  # 1 = UAV, 0 = non-UAV
    radar_type: str
    carrier_frequency_hz: float
    raw_shape: tuple
    metadata: dict = field(default_factory=dict)

    # Optional spatial / kinematic fields (populated for processed datasets)
    range_m: Optional[float] = None
    velocity_mps: Optional[float] = None
    azimuth_deg: Optional[float] = None
    elevation_deg: Optional[float] = None
    track_id: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self) -> None:
        if not isinstance(self.signal, np.ndarray):
            self.signal = np.asarray(self.signal)
        if not isinstance(self.raw_shape, tuple):
            self.raw_shape = tuple(self.raw_shape)

    @property
    def is_uav(self) -> bool:
        return self.label_binary == 1

    def to_npz_dict(self) -> dict:
        """Return a dict suitable for ``np.savez``."""
        d: dict = {
            "signal": self.signal,
            "label": np.array(self.label_binary, dtype=np.int8),
            "label_name": np.array(self.label),
        }
        if self.timestamp is not None:
            d["timestamp"] = np.array(self.timestamp, dtype=np.float64)
        if self.range_m is not None:
            d["range_m"] = np.array(self.range_m, dtype=np.float32)
        if self.azimuth_deg is not None:
            d["azimuth_deg"] = np.array(self.azimuth_deg, dtype=np.float32)
        if self.elevation_deg is not None:
            d["elevation_deg"] = np.array(self.elevation_deg, dtype=np.float32)
        if self.velocity_mps is not None:
            d["velocity_mps"] = np.array(self.velocity_mps, dtype=np.float32)
        if self.track_id is not None:
            d["track_id"] = np.array(self.track_id)
        return d
