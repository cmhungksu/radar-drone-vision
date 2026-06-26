"""Generic I/Q stream device supporting UDP, TCP, serial, and file replay."""

from __future__ import annotations

import logging
import socket
import struct
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from .base import RadarDevice, RadarFrame

logger = logging.getLogger(__name__)


class GenericIQDevice(RadarDevice):
    """Generic I/Q data source.

    Supports four transport modes:

    - ``udp``  -- receive I/Q packets over UDP
    - ``tcp``  -- receive I/Q over a TCP stream
    - ``serial`` -- read from a serial port (requires ``pyserial``)
    - ``file_replay`` -- replay a binary or ``.npy`` file

    Parameters
    ----------
    config : dict
        Configuration dictionary.  Required keys:

        - ``transport`` : str -- one of ``'udp'``, ``'tcp'``, ``'serial'``, ``'file_replay'``

        Transport-specific keys:

        - UDP/TCP: ``host`` (str), ``port`` (int)
        - Serial: ``port`` (str, e.g. ``'/dev/ttyUSB0'``), ``baudrate`` (int, default 921600)
        - File replay: ``file_path`` (str), ``sample_rate_hz`` (float, optional)

        Common optional keys:

        - ``samples_per_frame`` : int (default 256) -- number of I/Q samples per frame
        - ``dtype`` : str (default ``'complex64'``) -- numpy dtype for I/Q data
        - ``timeout_s`` : float (default 5.0) -- read timeout
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = dict(config)
        self._transport: str = config["transport"].lower()
        if self._transport not in ("udp", "tcp", "serial", "file_replay"):
            raise ValueError(f"Unknown transport '{self._transport}'")

        self._samples_per_frame: int = config.get("samples_per_frame", 256)
        self._dtype = np.dtype(config.get("dtype", "complex64"))
        self._timeout_s: float = config.get("timeout_s", 5.0)
        self._frame_counter: int = 0

        # Transport-specific handles
        self._socket: Optional[socket.socket] = None
        self._serial_port: Any = None  # serial.Serial
        self._file_data: Optional[np.ndarray] = None
        self._file_offset: int = 0
        self._replay_interval_s: float = 0.0

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        if self._connected:
            logger.warning("Already connected")
            return

        if self._transport == "udp":
            host = self._config.get("host", "0.0.0.0")
            port = self._config["port"]
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.settimeout(self._timeout_s)
            self._socket.bind((host, port))
            logger.info("UDP socket bound to %s:%d", host, port)

        elif self._transport == "tcp":
            host = self._config.get("host", "0.0.0.0")
            port = self._config["port"]
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self._timeout_s)
            self._socket.connect((host, port))
            logger.info("TCP connected to %s:%d", host, port)

        elif self._transport == "serial":
            try:
                import serial as pyserial
            except ImportError:
                raise ImportError("pyserial is required for serial transport: pip install pyserial")
            port_name = self._config["port"]
            baudrate = self._config.get("baudrate", 921600)
            self._serial_port = pyserial.Serial(
                port_name, baudrate=baudrate, timeout=self._timeout_s
            )
            logger.info("Serial port %s opened at %d baud", port_name, baudrate)

        elif self._transport == "file_replay":
            file_path = Path(self._config["file_path"])
            if not file_path.exists():
                raise FileNotFoundError(f"Replay file not found: {file_path}")
            if file_path.suffix == ".npy":
                self._file_data = np.load(str(file_path)).astype(self._dtype)
            else:
                self._file_data = np.fromfile(str(file_path), dtype=self._dtype)
            self._file_offset = 0
            sample_rate = self._config.get("sample_rate_hz", 1e6)
            self._replay_interval_s = self._samples_per_frame / sample_rate
            logger.info("File replay loaded %d samples from %s", len(self._file_data), file_path)

        self._connected = True
        self._frame_counter = 0

    def disconnect(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._serial_port is not None:
            self._serial_port.close()
            self._serial_port = None
        self._file_data = None
        self._file_offset = 0
        self._connected = False
        logger.info("Disconnected (%s)", self._transport)

    # ------------------------------------------------------------------
    # Frame reading
    # ------------------------------------------------------------------

    def read_frame(self) -> RadarFrame:
        if not self._connected:
            raise ConnectionError("Device not connected. Call connect() first.")

        ts_ns = time.time_ns()

        if self._transport in ("udp", "tcp"):
            iq = self._read_socket_frame()
        elif self._transport == "serial":
            iq = self._read_serial_frame()
        elif self._transport == "file_replay":
            iq = self._read_file_frame()
        else:
            raise RuntimeError(f"Unexpected transport: {self._transport}")

        frame = RadarFrame(
            timestamp_ns=ts_ns,
            frame_id=self._frame_counter,
            iq=iq,
            metadata={"transport": self._transport},
        )
        self._frame_counter += 1
        return frame

    def get_metadata(self) -> dict:
        return {
            "device": "GenericIQDevice",
            "transport": self._transport,
            "samples_per_frame": self._samples_per_frame,
            "dtype": str(self._dtype),
            "is_connected": self._connected,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_socket_frame(self) -> np.ndarray:
        """Read one frame worth of I/Q data from a socket."""
        assert self._socket is not None
        nbytes = self._samples_per_frame * self._dtype.itemsize
        buf = bytearray()
        while len(buf) < nbytes:
            chunk = self._socket.recv(nbytes - len(buf))
            if not chunk:
                raise ConnectionError("Socket closed by remote end")
            buf.extend(chunk)
        return np.frombuffer(bytes(buf[:nbytes]), dtype=self._dtype).copy()

    def _read_serial_frame(self) -> np.ndarray:
        """Read one frame worth of I/Q data from serial."""
        assert self._serial_port is not None
        nbytes = self._samples_per_frame * self._dtype.itemsize
        raw = self._serial_port.read(nbytes)
        if len(raw) < nbytes:
            raise TimeoutError(
                f"Serial read timeout: got {len(raw)} bytes, expected {nbytes}"
            )
        return np.frombuffer(raw, dtype=self._dtype).copy()

    def _read_file_frame(self) -> np.ndarray:
        """Read the next frame from the replay file."""
        assert self._file_data is not None
        end = self._file_offset + self._samples_per_frame
        if end > len(self._file_data):
            # Wrap around to beginning
            self._file_offset = 0
            end = self._samples_per_frame
        iq = self._file_data[self._file_offset:end].copy()
        self._file_offset = end

        # Simulate real-time pacing
        if self._replay_interval_s > 0:
            time.sleep(self._replay_interval_s)

        return iq
