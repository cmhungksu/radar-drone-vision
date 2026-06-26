"""TI mmWave radar device skeleton.

This module provides a structural skeleton for integrating Texas Instruments
mmWave radar sensors (e.g. IWR1443, IWR6843, AWR2944).  It does not depend on
the TI mmWave SDK but defines the frame parsing logic for common TLV
(Type-Length-Value) packet formats.
"""

from __future__ import annotations

import logging
import struct
import time
from typing import Any, Dict, List, Optional

import numpy as np

from .base import RadarDevice, RadarFrame

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# TLV type constants (TI mmWave SDK demo output)
# ------------------------------------------------------------------
TLV_DETECTED_POINTS = 1
TLV_RANGE_PROFILE = 2
TLV_NOISE_PROFILE = 3
TLV_AZIMUTH_STATIC_HEATMAP = 4
TLV_RANGE_DOPPLER_HEATMAP = 5
TLV_STATS = 6
TLV_DETECTED_POINTS_SIDE_INFO = 7
TLV_AZIMUTH_ELEVATION_STATIC_HEATMAP = 8

MAGIC_WORD = b"\x02\x01\x04\x03\x06\x05\x08\x07"


class TImmWaveDevice(RadarDevice):
    """Skeleton driver for TI mmWave radar sensors.

    This class provides:
    - TLV packet parsing for raw ADC, range profile, range-Doppler heatmap,
      and point cloud data
    - Serial port communication structure
    - Configuration file (chirp profile) loading placeholder

    Parameters
    ----------
    config : dict
        Configuration dictionary.  Keys:

        - ``data_port`` : str -- serial port for data (e.g. ``'/dev/ttyACM1'``)
        - ``cli_port`` : str -- serial port for CLI commands (e.g. ``'/dev/ttyACM0'``)
        - ``cli_baudrate`` : int (default 115200)
        - ``data_baudrate`` : int (default 921600)
        - ``config_file`` : str, optional -- path to ``.cfg`` chirp file
        - ``timeout_s`` : float (default 5.0)
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = dict(config)
        self._data_port_name: str = config.get("data_port", "")
        self._cli_port_name: str = config.get("cli_port", "")
        self._cli_baudrate: int = config.get("cli_baudrate", 115200)
        self._data_baudrate: int = config.get("data_baudrate", 921600)
        self._config_file: Optional[str] = config.get("config_file")
        self._timeout_s: float = config.get("timeout_s", 5.0)

        self._data_serial: Any = None
        self._cli_serial: Any = None
        self._frame_counter: int = 0

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open serial ports and send chirp configuration."""
        if self._connected:
            logger.warning("Already connected")
            return

        try:
            import serial as pyserial
        except ImportError:
            raise ImportError(
                "pyserial is required for TI mmWave: pip install pyserial"
            )

        if not self._data_port_name or not self._cli_port_name:
            raise ValueError(
                "Both 'data_port' and 'cli_port' must be specified in config"
            )

        self._cli_serial = pyserial.Serial(
            self._cli_port_name,
            baudrate=self._cli_baudrate,
            timeout=self._timeout_s,
        )
        self._data_serial = pyserial.Serial(
            self._data_port_name,
            baudrate=self._data_baudrate,
            timeout=self._timeout_s,
        )

        # Send configuration if a .cfg file was provided
        if self._config_file:
            self._send_config(self._config_file)

        self._connected = True
        self._frame_counter = 0
        logger.info(
            "TI mmWave connected: CLI=%s, DATA=%s",
            self._cli_port_name,
            self._data_port_name,
        )

    def disconnect(self) -> None:
        """Close serial ports."""
        # Send sensorStop command before closing
        if self._cli_serial is not None:
            try:
                self._cli_serial.write(b"sensorStop\n")
                time.sleep(0.1)
            except Exception:
                pass
            self._cli_serial.close()
            self._cli_serial = None
        if self._data_serial is not None:
            self._data_serial.close()
            self._data_serial = None
        self._connected = False
        logger.info("TI mmWave disconnected")

    # ------------------------------------------------------------------
    # Frame reading
    # ------------------------------------------------------------------

    def read_frame(self) -> RadarFrame:
        """Read and parse one TLV frame from the data port."""
        if not self._connected:
            raise ConnectionError("Device not connected. Call connect() first.")

        raw_packet = self._read_raw_packet()
        parsed = self._parse_tlv_packet(raw_packet)

        frame = RadarFrame(
            timestamp_ns=time.time_ns(),
            frame_id=self._frame_counter,
            iq=parsed.get("adc_raw"),
            range_doppler=parsed.get("range_doppler"),
            point_cloud=parsed.get("point_cloud"),
            metadata={
                "device": "ti_mmwave",
                "range_profile": parsed.get("range_profile"),
                "stats": parsed.get("stats"),
            },
        )
        self._frame_counter += 1
        return frame

    def get_metadata(self) -> dict:
        return {
            "device": "TImmWaveDevice",
            "data_port": self._data_port_name,
            "cli_port": self._cli_port_name,
            "config_file": self._config_file,
            "is_connected": self._connected,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_config(self, cfg_path: str) -> None:
        """Send chirp configuration commands from a ``.cfg`` file."""
        assert self._cli_serial is not None
        from pathlib import Path

        lines = Path(cfg_path).read_text().splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            self._cli_serial.write((line + "\n").encode())
            time.sleep(0.05)
            # Read back response (best-effort)
            if self._cli_serial.in_waiting:
                self._cli_serial.read(self._cli_serial.in_waiting)
        logger.info("Sent %d config lines from %s", len(lines), cfg_path)

    def _read_raw_packet(self) -> bytes:
        """Read bytes until a complete TLV packet is found."""
        assert self._data_serial is not None
        # Sync to magic word
        buf = bytearray()
        while True:
            byte = self._data_serial.read(1)
            if not byte:
                raise TimeoutError("Timeout waiting for TI mmWave packet")
            buf.append(byte[0])
            if len(buf) >= 8 and bytes(buf[-8:]) == MAGIC_WORD:
                break

        # Read header (40 bytes total including magic)
        header_rest = self._data_serial.read(32)
        if len(header_rest) < 32:
            raise TimeoutError("Timeout reading TI mmWave header")
        header = bytes(buf[-8:]) + header_rest
        # Total packet length is at offset 12 (uint32)
        total_len = struct.unpack("<I", header[12:16])[0]
        # Read remaining payload
        remaining = total_len - 40
        if remaining > 0:
            payload = self._data_serial.read(remaining)
            if len(payload) < remaining:
                raise TimeoutError("Timeout reading TI mmWave payload")
            return header + payload
        return header

    def _parse_tlv_packet(self, packet: bytes) -> Dict[str, Any]:
        """Parse a TLV frame packet into its components."""
        result: Dict[str, Any] = {}

        if len(packet) < 40:
            return result

        # Header fields
        total_len = struct.unpack("<I", packet[12:16])[0]
        num_tlvs = struct.unpack("<I", packet[24:28])[0]

        offset = 40  # Start of TLV section
        for _ in range(num_tlvs):
            if offset + 8 > len(packet):
                break
            tlv_type = struct.unpack("<I", packet[offset : offset + 4])[0]
            tlv_len = struct.unpack("<I", packet[offset + 4 : offset + 8])[0]
            tlv_data = packet[offset + 8 : offset + 8 + tlv_len]

            if tlv_type == TLV_DETECTED_POINTS and len(tlv_data) >= 4:
                result["point_cloud"] = self._parse_detected_points(tlv_data)
            elif tlv_type == TLV_RANGE_PROFILE:
                result["range_profile"] = np.frombuffer(tlv_data, dtype=np.uint16).copy()
            elif tlv_type == TLV_RANGE_DOPPLER_HEATMAP:
                result["range_doppler"] = np.frombuffer(tlv_data, dtype=np.uint16).copy()
            elif tlv_type == TLV_STATS:
                result["stats"] = tlv_data

            offset += 8 + tlv_len

        return result

    @staticmethod
    def _parse_detected_points(data: bytes) -> np.ndarray:
        """Parse detected-points TLV into (N, 4) array [x, y, z, doppler]."""
        # First 4 bytes: number of detected objects (uint16) + xyzQFormat (uint16)
        if len(data) < 4:
            return np.empty((0, 4), dtype=np.float32)
        n_obj = struct.unpack("<H", data[0:2])[0]
        xyz_q = struct.unpack("<H", data[2:4])[0]
        if xyz_q == 0:
            xyz_q = 1

        point_size = 16  # 4 x int16 = x, y, z, doppler (but packed as float or int)
        points = []
        off = 4
        for _ in range(n_obj):
            if off + point_size > len(data):
                break
            vals = struct.unpack("<4f", data[off : off + point_size])
            points.append(vals)
            off += point_size

        if not points:
            return np.empty((0, 4), dtype=np.float32)
        return np.array(points, dtype=np.float32)
