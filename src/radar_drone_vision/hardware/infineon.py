"""Infineon radar device skeleton.

Placeholder for future integration with Infineon radar sensors
(e.g. BGT60TR13C, BGT60UTR11AIP) via the Infineon Radar SDK (ifxRadar).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import numpy as np

from .base import RadarDevice, RadarFrame

logger = logging.getLogger(__name__)


class InfineonDevice(RadarDevice):
    """Skeleton driver for Infineon radar sensors.

    This class defines the integration structure for Infineon FMCW radar
    sensors.  Full implementation requires the ``ifxRadarSDK`` Python
    wrapper (``ifxRadar``).

    Parameters
    ----------
    config : dict
        Configuration dictionary.  Expected keys:

        - ``device_type`` : str (default ``'BGT60TR13C'``)
        - ``num_samples_per_chirp`` : int (default 128)
        - ``num_chirps_per_frame`` : int (default 32)
        - ``num_rx_antennas`` : int (default 3)
        - ``lower_frequency_hz`` : float (default 58e9)
        - ``upper_frequency_hz`` : float (default 63e9)
        - ``sample_rate_hz`` : float (default 2e6)
        - ``frame_rate_hz`` : float (default 10.0)
        - ``tx_power_level`` : int (default 31)
        - ``if_gain_db`` : float (default 33.0)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = dict(config) if config else {}
        self._device_type: str = self._config.get("device_type", "BGT60TR13C")
        self._num_samples: int = self._config.get("num_samples_per_chirp", 128)
        self._num_chirps: int = self._config.get("num_chirps_per_frame", 32)
        self._num_rx: int = self._config.get("num_rx_antennas", 3)
        self._frame_rate: float = self._config.get("frame_rate_hz", 10.0)

        self._device_handle: Any = None  # ifxRadar.Device
        self._frame_counter: int = 0

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to an Infineon radar device.

        Requires ``ifxRadar`` SDK to be installed.  This skeleton will raise
        ``NotImplementedError`` until the SDK is available.
        """
        if self._connected:
            logger.warning("Already connected")
            return

        try:
            import ifxRadar  # type: ignore[import-not-found]

            self._device_handle = ifxRadar.Device()
            # Configure device
            cfg = self._device_handle.create_simple_config()
            cfg.num_samples_per_chirp = self._num_samples
            cfg.num_chirps_per_frame = self._num_chirps
            cfg.frame_rate_Hz = self._frame_rate
            self._device_handle.set_config(cfg)
            self._connected = True
            self._frame_counter = 0
            logger.info("Infineon %s connected", self._device_type)

        except ImportError:
            raise NotImplementedError(
                "Infineon radar SDK (ifxRadar) is not installed. "
                "This is a skeleton for future integration. "
                "Install the SDK from https://www.infineon.com/radar-sdk"
            )

    def disconnect(self) -> None:
        """Disconnect from the Infineon radar device."""
        if self._device_handle is not None:
            try:
                self._device_handle.stop_acquisition()
            except Exception:
                pass
            self._device_handle = None
        self._connected = False
        logger.info("Infineon device disconnected")

    # ------------------------------------------------------------------
    # Frame reading
    # ------------------------------------------------------------------

    def read_frame(self) -> RadarFrame:
        """Read one frame of I/Q data from the Infineon radar.

        Returns
        -------
        frame : RadarFrame
            Frame with ``iq`` populated as shape
            ``(num_rx, num_chirps, num_samples)`` complex array.
        """
        if not self._connected:
            raise ConnectionError("Device not connected. Call connect() first.")

        if self._device_handle is None:
            raise RuntimeError("No device handle available")

        # Read raw frame from SDK
        raw = self._device_handle.get_next_frame()
        # raw is typically (num_rx, num_chirps, num_samples) complex
        iq = np.asarray(raw, dtype=np.complex64)

        frame = RadarFrame(
            timestamp_ns=time.time_ns(),
            frame_id=self._frame_counter,
            iq=iq,
            metadata={
                "device": "infineon",
                "device_type": self._device_type,
                "num_rx": self._num_rx,
                "num_chirps": self._num_chirps,
                "num_samples": self._num_samples,
            },
        )
        self._frame_counter += 1
        return frame

    def get_metadata(self) -> dict:
        return {
            "device": "InfineonDevice",
            "device_type": self._device_type,
            "num_samples_per_chirp": self._num_samples,
            "num_chirps_per_frame": self._num_chirps,
            "num_rx_antennas": self._num_rx,
            "frame_rate_hz": self._frame_rate,
            "is_connected": self._connected,
        }
