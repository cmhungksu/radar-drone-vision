"""Dataset replay simulator device.

Replays a processed radar dataset as if it were a live radar, enabling
end-to-end pipeline testing without physical hardware.

Usage::

    python scripts/live_capture.py --device simulator --dataset zenodo77 --speed 1.0
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from .base import RadarDevice, RadarFrame

logger = logging.getLogger(__name__)


class SimulatorDevice(RadarDevice):
    """Replay a radar dataset as a simulated live device.

    Parameters
    ----------
    dataset_path : str or Path
        Path to the dataset directory or ``.npy`` / ``.npz`` file.
    speed : float
        Playback speed multiplier (1.0 = real-time, 2.0 = double speed,
        0.0 = as fast as possible).
    loop : bool
        If True, loop the dataset when all samples are exhausted.
    frame_interval_s : float
        Simulated interval between frames in seconds (default 0.01 = 100 Hz).
        Only used if the dataset does not contain timing information.
    """

    def __init__(
        self,
        dataset_path: Union[str, Path],
        speed: float = 1.0,
        loop: bool = True,
        frame_interval_s: float = 0.01,
    ) -> None:
        self._dataset_path = Path(dataset_path)
        self._speed = speed
        self._loop = loop
        self._frame_interval_s = frame_interval_s

        self._samples: List[np.ndarray] = []
        self._labels: List[int] = []
        self._timestamps: Optional[np.ndarray] = None
        self._frame_counter: int = 0
        self._last_read_time: float = 0.0

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Load the dataset into memory."""
        if self._connected:
            logger.warning("Simulator already connected")
            return

        self._load_dataset()
        if not self._samples:
            raise FileNotFoundError(
                f"No samples loaded from {self._dataset_path}"
            )

        self._connected = True
        self._frame_counter = 0
        self._last_read_time = time.monotonic()
        logger.info(
            "Simulator connected: %d samples from %s (speed=%.1fx)",
            len(self._samples),
            self._dataset_path,
            self._speed,
        )

    def disconnect(self) -> None:
        """Release dataset from memory."""
        self._samples.clear()
        self._labels.clear()
        self._timestamps = None
        self._connected = False
        logger.info("Simulator disconnected")

    # ------------------------------------------------------------------
    # Frame reading
    # ------------------------------------------------------------------

    def read_frame(self) -> RadarFrame:
        """Return the next sample as a RadarFrame, pacing by speed factor."""
        if not self._connected:
            raise ConnectionError("Simulator not connected. Call connect() first.")

        if not self._samples:
            raise RuntimeError("No samples available")

        idx = self._frame_counter % len(self._samples)
        if not self._loop and self._frame_counter >= len(self._samples):
            raise StopIteration("All samples replayed (loop=False)")

        # Pacing
        if self._speed > 0:
            interval = self._frame_interval_s / self._speed
            elapsed = time.monotonic() - self._last_read_time
            if elapsed < interval:
                time.sleep(interval - elapsed)

        signal = self._samples[idx]
        label = self._labels[idx] if idx < len(self._labels) else -1

        ts_ns = time.time_ns()
        if self._timestamps is not None and idx < len(self._timestamps):
            # Use dataset timestamp if available
            ts_ns = int(self._timestamps[idx] * 1e9)

        frame = RadarFrame(
            timestamp_ns=ts_ns,
            frame_id=self._frame_counter,
            iq=signal if np.iscomplexobj(signal) else None,
            adc=signal if not np.iscomplexobj(signal) else None,
            metadata={
                "device": "simulator",
                "dataset_idx": idx,
                "label": label,
                "source": str(self._dataset_path),
            },
        )

        self._last_read_time = time.monotonic()
        self._frame_counter += 1
        return frame

    def get_metadata(self) -> dict:
        return {
            "device": "SimulatorDevice",
            "dataset_path": str(self._dataset_path),
            "n_samples": len(self._samples),
            "speed": self._speed,
            "loop": self._loop,
            "is_connected": self._connected,
        }

    # ------------------------------------------------------------------
    # Dataset loading
    # ------------------------------------------------------------------

    def _load_dataset(self) -> None:
        """Load dataset samples from file or directory."""
        path = self._dataset_path

        if path.is_file():
            self._load_file(path)
        elif path.is_dir():
            self._load_directory(path)
        else:
            raise FileNotFoundError(f"Dataset not found: {path}")

    def _load_file(self, path: Path) -> None:
        """Load a single .npy or .npz file."""
        if path.suffix == ".npy":
            raw = np.load(str(path), allow_pickle=True)
            if raw.ndim == 1 and isinstance(raw[0], (list, np.ndarray, tuple)):
                # Object array of (signal, label) pairs
                self._samples = [np.asarray(r[0], dtype=np.float32) for r in raw]
                self._labels = [int(r[-1]) for r in raw]
            elif raw.ndim == 2:
                # 2-D array: last column is label
                self._samples = [row.astype(np.float32) for row in raw[:, :-1]]
                self._labels = raw[:, -1].astype(int).tolist()
            else:
                self._samples = [raw.astype(np.float32)]
                self._labels = [-1]

        elif path.suffix == ".npz":
            data = np.load(str(path), allow_pickle=True)
            if "signals" in data:
                self._samples = [s.astype(np.float32) for s in data["signals"]]
            elif "signal" in data:
                self._samples = [data["signal"].astype(np.float32)]
            else:
                # Try first array key
                key = list(data.keys())[0]
                self._samples = [data[key].astype(np.float32)]

            if "labels" in data:
                self._labels = data["labels"].astype(int).tolist()
            elif "label" in data:
                self._labels = [int(data["label"])]

            if "timestamps" in data:
                self._timestamps = data["timestamps"].astype(np.float64)

        else:
            # Binary file — treat as raw float32
            raw = np.fromfile(str(path), dtype=np.float32)
            # Split into fixed-size chunks
            chunk_size = 256
            n_chunks = len(raw) // chunk_size
            if n_chunks == 0:
                self._samples = [raw]
            else:
                self._samples = [
                    raw[i * chunk_size : (i + 1) * chunk_size] for i in range(n_chunks)
                ]
            self._labels = [-1] * len(self._samples)

        logger.info("Loaded %d samples from %s", len(self._samples), path)

    def _load_directory(self, path: Path) -> None:
        """Load all .npy/.npz files in a directory."""
        files = sorted(path.glob("*.npy")) + sorted(path.glob("*.npz"))
        if not files:
            raise FileNotFoundError(f"No .npy/.npz files found in {path}")
        for f in files:
            n_before = len(self._samples)
            self._load_file(f)
            logger.debug("Loaded %d samples from %s", len(self._samples) - n_before, f.name)
