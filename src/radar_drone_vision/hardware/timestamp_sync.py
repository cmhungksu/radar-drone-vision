"""Timestamp synchronisation and frame health monitoring.

Tracks clock drift between device timestamps and host timestamps,
detects dropped frames, and reports latency statistics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class _FrameRecord:
    """Internal record for a single frame."""

    frame_id: int
    device_ts: float  # device timestamp in seconds
    host_ts: float  # host timestamp in seconds


class TimestampSync:
    """Track timestamp drift, dropped frames, and latency.

    Usage::

        sync = TimestampSync()
        for frame in device.read_frames():
            sync.record_frame(frame.frame_id, frame.timestamp_ns / 1e9, time.time())
        print(sync.report())
    """

    def __init__(self) -> None:
        self._records: List[_FrameRecord] = []
        self._expected_next_id: Optional[int] = None
        self._dropped_ids: List[int] = []

    def record_frame(
        self,
        frame_id: int,
        device_ts: float,
        host_ts: float,
    ) -> None:
        """Record a frame's timestamps.

        Parameters
        ----------
        frame_id : int
            Sequential frame identifier from the device.
        device_ts : float
            Device-side timestamp in seconds.
        host_ts : float
            Host-side timestamp in seconds (e.g. ``time.time()``).
        """
        # Track dropped frames
        if self._expected_next_id is not None and frame_id > self._expected_next_id:
            for missing in range(self._expected_next_id, frame_id):
                self._dropped_ids.append(missing)
        self._expected_next_id = frame_id + 1

        self._records.append(
            _FrameRecord(frame_id=frame_id, device_ts=device_ts, host_ts=host_ts)
        )

    def get_drift(self) -> Optional[float]:
        """Estimate clock drift between device and host.

        Returns the slope of ``(device_ts - host_ts)`` over time (ppm-like).
        Positive means device clock is faster.

        Returns
        -------
        drift : float or None
            Drift in seconds per second, or None if insufficient data.
        """
        if len(self._records) < 2:
            return None

        offsets = np.array(
            [(r.device_ts - r.host_ts) for r in self._records], dtype=np.float64
        )
        host_times = np.array([r.host_ts for r in self._records], dtype=np.float64)

        # Linear fit: offset = drift * time + const
        if host_times[-1] - host_times[0] < 1e-9:
            return 0.0

        coeffs = np.polyfit(host_times - host_times[0], offsets, 1)
        return float(coeffs[0])

    def get_dropped_frames(self) -> List[int]:
        """Return list of dropped frame IDs."""
        return list(self._dropped_ids)

    def get_latency_stats(self) -> Dict[str, float]:
        """Compute latency statistics (device-to-host delay).

        Returns
        -------
        stats : dict
            Keys: ``mean``, ``std``, ``min``, ``max``, ``p50``, ``p95``, ``p99``
            (all in seconds).
        """
        if not self._records:
            return {}

        latencies = np.array(
            [abs(r.host_ts - r.device_ts) for r in self._records], dtype=np.float64
        )

        return {
            "mean": float(np.mean(latencies)),
            "std": float(np.std(latencies)),
            "min": float(np.min(latencies)),
            "max": float(np.max(latencies)),
            "p50": float(np.percentile(latencies, 50)),
            "p95": float(np.percentile(latencies, 95)),
            "p99": float(np.percentile(latencies, 99)),
        }

    def report(self) -> str:
        """Generate a human-readable synchronisation report.

        Returns
        -------
        text : str
        """
        lines = ["=== Timestamp Sync Report ==="]
        lines.append(f"Total frames recorded: {len(self._records)}")

        # Dropped frames
        n_dropped = len(self._dropped_ids)
        lines.append(f"Dropped frames: {n_dropped}")
        if n_dropped > 0:
            total = len(self._records) + n_dropped
            lines.append(f"  Drop rate: {n_dropped / total * 100:.2f}%")
            if n_dropped <= 20:
                lines.append(f"  Dropped IDs: {self._dropped_ids}")
            else:
                lines.append(f"  First 10 dropped: {self._dropped_ids[:10]}")

        # Drift
        drift = self.get_drift()
        if drift is not None:
            lines.append(f"Clock drift: {drift * 1e6:.2f} ppm ({drift:.9f} s/s)")

        # Latency
        stats = self.get_latency_stats()
        if stats:
            lines.append("Latency (device-to-host):")
            lines.append(f"  Mean:  {stats['mean'] * 1000:.3f} ms")
            lines.append(f"  Std:   {stats['std'] * 1000:.3f} ms")
            lines.append(f"  Min:   {stats['min'] * 1000:.3f} ms")
            lines.append(f"  Max:   {stats['max'] * 1000:.3f} ms")
            lines.append(f"  P50:   {stats['p50'] * 1000:.3f} ms")
            lines.append(f"  P95:   {stats['p95'] * 1000:.3f} ms")
            lines.append(f"  P99:   {stats['p99'] * 1000:.3f} ms")

        # Frame rate estimate
        if len(self._records) >= 2:
            durations = np.diff([r.host_ts for r in self._records])
            if len(durations) > 0 and np.mean(durations) > 0:
                avg_fps = 1.0 / np.mean(durations)
                lines.append(f"Estimated frame rate: {avg_fps:.1f} Hz")

        return "\n".join(lines)
