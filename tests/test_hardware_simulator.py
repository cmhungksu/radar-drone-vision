"""Tests for the hardware simulator module.

Since the hardware modules (base.py, simulator.py, timestamp_sync.py) are
specified in the project plan but not yet fully implemented, this test file
defines the expected API contract using lightweight in-test stubs.  Once
the real modules are created, these tests can import directly from
radar_drone_vision.hardware.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Minimal in-test stubs matching the planned hardware API
# ---------------------------------------------------------------------------

@dataclass
class RadarFrame:
    """Single frame from a radar device."""
    timestamp_ns: int
    frame_id: int
    iq: Optional[np.ndarray] = None
    adc: Optional[np.ndarray] = None
    range_doppler: Optional[np.ndarray] = None
    point_cloud: Optional[np.ndarray] = None
    metadata: dict = field(default_factory=dict)


class TimestampSync:
    """Track timestamp drift and frame drops."""

    def __init__(self) -> None:
        self._timestamps: List[int] = []
        self._frame_ids: List[int] = []

    def record(self, frame: RadarFrame) -> None:
        self._timestamps.append(frame.timestamp_ns)
        self._frame_ids.append(frame.frame_id)

    @property
    def num_frames(self) -> int:
        return len(self._timestamps)

    @property
    def dropped_frames(self) -> int:
        if len(self._frame_ids) < 2:
            return 0
        expected = self._frame_ids[-1] - self._frame_ids[0] + 1
        return expected - len(self._frame_ids)

    @property
    def mean_interval_ms(self) -> float:
        if len(self._timestamps) < 2:
            return 0.0
        diffs = np.diff(self._timestamps) / 1e6  # ns -> ms
        return float(np.mean(diffs))


class SimulatorDevice:
    """Replay synthetic data as if it were a live radar device."""

    def __init__(self, signals: List[np.ndarray], frame_rate_hz: float = 10.0):
        self._signals = signals
        self._frame_rate_hz = frame_rate_hz
        self._connected = False
        self._cursor = 0

    def connect(self) -> None:
        self._connected = True
        self._cursor = 0

    def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def read_frame(self) -> Optional[RadarFrame]:
        if not self._connected:
            raise RuntimeError("Device not connected")
        if self._cursor >= len(self._signals):
            return None
        sig = self._signals[self._cursor]
        frame = RadarFrame(
            timestamp_ns=int(self._cursor * 1e9 / self._frame_rate_hz),
            frame_id=self._cursor,
            iq=sig,
        )
        self._cursor += 1
        return frame

    def get_metadata(self) -> dict:
        return {
            "device_type": "simulator",
            "frame_rate_hz": self._frame_rate_hz,
            "total_frames": len(self._signals),
        }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRadarFrame:
    def test_basic_construction(self):
        f = RadarFrame(timestamp_ns=1000000, frame_id=0)
        assert f.timestamp_ns == 1000000
        assert f.frame_id == 0
        assert f.iq is None

    def test_with_iq_data(self):
        iq = np.array([1 + 2j, 3 + 4j], dtype=np.complex64)
        f = RadarFrame(timestamp_ns=0, frame_id=1, iq=iq)
        assert f.iq is not None
        assert f.iq.shape == (2,)

    def test_metadata(self):
        f = RadarFrame(timestamp_ns=0, frame_id=0, metadata={"sensor": "test"})
        assert f.metadata["sensor"] == "test"


class TestTimestampSync:
    def test_empty_tracker(self):
        ts = TimestampSync()
        assert ts.num_frames == 0
        assert ts.dropped_frames == 0
        assert ts.mean_interval_ms == 0.0

    def test_record_frames(self):
        ts = TimestampSync()
        for i in range(5):
            f = RadarFrame(timestamp_ns=i * 100_000_000, frame_id=i)
            ts.record(f)
        assert ts.num_frames == 5
        assert ts.dropped_frames == 0
        assert ts.mean_interval_ms == pytest.approx(100.0, abs=0.1)

    def test_detect_dropped_frames(self):
        ts = TimestampSync()
        # Frames 0, 1, 3, 4 -> frame 2 is missing
        for fid in [0, 1, 3, 4]:
            f = RadarFrame(timestamp_ns=fid * 100_000_000, frame_id=fid)
            ts.record(f)
        assert ts.dropped_frames == 1


class TestSimulatorDevice:
    @pytest.fixture
    def signals(self):
        rng = np.random.default_rng(42)
        return [rng.standard_normal(256).astype(np.float32) for _ in range(20)]

    def test_connect_disconnect_lifecycle(self, signals):
        dev = SimulatorDevice(signals)
        assert not dev.is_connected
        dev.connect()
        assert dev.is_connected
        dev.disconnect()
        assert not dev.is_connected

    def test_read_frame_returns_radar_frame(self, signals):
        dev = SimulatorDevice(signals)
        dev.connect()
        frame = dev.read_frame()
        assert isinstance(frame, RadarFrame)
        assert frame.frame_id == 0
        assert frame.iq is not None
        assert frame.iq.shape == (256,)

    def test_sequential_reads(self, signals):
        dev = SimulatorDevice(signals)
        dev.connect()
        ids = []
        for _ in range(5):
            f = dev.read_frame()
            ids.append(f.frame_id)
        assert ids == [0, 1, 2, 3, 4]

    def test_exhausted_returns_none(self, signals):
        dev = SimulatorDevice(signals[:3])
        dev.connect()
        dev.read_frame()
        dev.read_frame()
        dev.read_frame()
        assert dev.read_frame() is None

    def test_read_without_connect_raises(self, signals):
        dev = SimulatorDevice(signals)
        with pytest.raises(RuntimeError, match="not connected"):
            dev.read_frame()

    def test_reconnect_resets_cursor(self, signals):
        dev = SimulatorDevice(signals)
        dev.connect()
        dev.read_frame()
        dev.read_frame()
        dev.disconnect()
        dev.connect()
        frame = dev.read_frame()
        assert frame.frame_id == 0

    def test_get_metadata(self, signals):
        dev = SimulatorDevice(signals, frame_rate_hz=20.0)
        meta = dev.get_metadata()
        assert meta["device_type"] == "simulator"
        assert meta["frame_rate_hz"] == 20.0
        assert meta["total_frames"] == len(signals)

    def test_timestamp_increases(self, signals):
        dev = SimulatorDevice(signals, frame_rate_hz=10.0)
        dev.connect()
        ts = []
        for _ in range(5):
            f = dev.read_frame()
            ts.append(f.timestamp_ns)
        assert all(ts[i] < ts[i + 1] for i in range(len(ts) - 1))
