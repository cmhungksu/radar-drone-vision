"""Flight log parser — read-only extraction of state data.

Parses CSV/JSON flight logs into the safe intermediate format
(flight_state_series.sim.json). All GPS coordinates are converted
to local stage coordinates. No write-back capability.

SIMULATION_ONLY — read-only parser, no mission upload.
"""

from __future__ import annotations

import csv
import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Safety: explicitly deny any write-related fields
_FORBIDDEN_FIELDS = {
    "mission_upload", "arm_command", "takeoff_command", "land_command",
    "set_position_target", "command_long", "guided_mode", "auto_mode",
    "offboard_command", "mavlink_write", "serial_write", "udp_write",
}


def parse_csv_log(csv_path: str | Path) -> dict:
    """Parse a CSV flight log into flight_state_series format.

    Expected columns: time,drone_id,x,y,z,led_r,led_g,led_b,
                      battery_percent,gps_quality,imu_quality,link_quality,status

    Returns flight_state_series.sim.json structure.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {csv_path}")

    drones: dict[str, list[dict]] = {}

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Safety check: reject if contains forbidden fields
        if reader.fieldnames:
            for field in reader.fieldnames:
                if field.lower().strip() in _FORBIDDEN_FIELDS:
                    raise ValueError(
                        f"SAFETY VIOLATION: log contains forbidden field '{field}'. "
                        "This parser is read-only and cannot process control commands."
                    )

        for row in reader:
            drone_id = row.get("drone_id", "UNKNOWN")
            if drone_id not in drones:
                drones[drone_id] = []

            frame = {
                "t": float(row.get("time", 0)),
                "x": float(row.get("x", 0)),
                "y": float(row.get("y", 0)),
                "z": float(row.get("z", 0)),
                "led": {
                    "r": int(row.get("led_r", 0)),
                    "g": int(row.get("led_g", 0)),
                    "b": int(row.get("led_b", 0)),
                    "on": int(row.get("led_r", 0)) + int(row.get("led_g", 0)) + int(row.get("led_b", 0)) > 0,
                },
                "status": row.get("status", "UNKNOWN"),
                "health": {
                    "battery_percent": int(row.get("battery_percent", 100)),
                    "gps_quality_label": row.get("gps_quality", "GOOD"),
                    "imu_quality_label": row.get("imu_quality", "GOOD"),
                    "link_quality_label": row.get("link_quality", "GOOD"),
                },
            }
            drones[drone_id].append(frame)

    # Sort each drone's frames by time
    for did in drones:
        drones[did].sort(key=lambda f: f["t"])

    result = {
        "schema": "flight_state_series.sim.v1",
        "safety": "SIMULATION_ONLY",
        "project_id": f"log_{uuid.uuid4().hex[:8]}",
        "coordinate_frame": "LOCAL_STAGE_XYZ_ONLY",
        "source_file": path.name,
        "drone_count": len(drones),
        "drones": [
            {"drone_id": did, "frames": frames}
            for did, frames in sorted(drones.items())
        ],
    }

    logger.info("Parsed %s: %d drones, %d total frames",
                path.name, len(drones), sum(len(d["frames"]) for d in result["drones"]))
    return result


def parse_json_plan(json_path: str | Path) -> dict:
    """Parse a high-level show plan JSON into flight_state_series format."""
    with open(json_path, "r") as f:
        data = json.load(f)

    # Safety check
    if any(k in str(data).lower() for k in ["mission_upload", "arm_command", "mavlink_write"]):
        raise ValueError("SAFETY VIOLATION: JSON contains potential control commands")

    # If it's already a timeline plan from our system, convert
    if "drones" in data and "plan_id" in data:
        from radar_drone_vision.drone_show.simulation import sample_drone_path
        drones = []
        for d in data["drones"]:
            samples = sample_drone_path(d.get("segments", []), sample_rate=5)
            frames = []
            for s in samples:
                frames.append({
                    "t": s["t"],
                    "x": s["xyz"][0],
                    "y": s["xyz"][1],
                    "z": s["xyz"][2],
                    "led": {"r": s["rgb888"][0], "g": s["rgb888"][1], "b": s["rgb888"][2], "on": True},
                    "status": "SIMULATED",
                    "health": {"battery_percent": 100, "gps_quality_label": "SIMULATED",
                               "imu_quality_label": "SIMULATED", "link_quality_label": "SIMULATED"},
                })
            drones.append({"drone_id": d["drone_id"], "frames": frames})

        return {
            "schema": "flight_state_series.sim.v1",
            "safety": "SIMULATION_ONLY",
            "project_id": data.get("plan_id", "unknown"),
            "coordinate_frame": "LOCAL_STAGE_XYZ_ONLY",
            "drone_count": len(drones),
            "drones": drones,
        }

    raise ValueError("Unrecognized JSON format")


def detect_anomalies(flight_state: dict) -> List[dict]:
    """Detect anomalies in a flight state series.

    Returns list of {drone_id, time, type, severity, description}.
    """
    anomalies = []

    for drone in flight_state.get("drones", []):
        did = drone["drone_id"]
        frames = drone["frames"]

        for i in range(1, len(frames)):
            prev = frames[i - 1]
            curr = frames[i]
            dt = curr["t"] - prev["t"]
            if dt <= 0:
                continue

            # GPS jump detection
            dx = curr["x"] - prev["x"]
            dy = curr["y"] - prev["y"]
            dz = curr["z"] - prev["z"]
            speed = (dx**2 + dy**2 + dz**2)**0.5 / dt
            if speed > 25.0:
                anomalies.append({
                    "drone_id": did, "time": curr["t"],
                    "type": "GPS_DRIFT", "severity": "high",
                    "description": f"Speed jump: {speed:.1f} m/s",
                })

            # Battery drop
            batt_prev = prev["health"]["battery_percent"]
            batt_curr = curr["health"]["battery_percent"]
            if batt_prev - batt_curr > 5:
                anomalies.append({
                    "drone_id": did, "time": curr["t"],
                    "type": "BATTERY_DROP", "severity": "medium",
                    "description": f"Battery: {batt_prev}% → {batt_curr}%",
                })
            if batt_curr < 20:
                anomalies.append({
                    "drone_id": did, "time": curr["t"],
                    "type": "LOW_BATTERY", "severity": "high",
                    "description": f"Battery at {batt_curr}%",
                })

            # LED blackout during show
            if curr["status"] in ("FORMATION_HOLD", "FORMATION_TRANSITION") and not curr["led"].get("on", True):
                anomalies.append({
                    "drone_id": did, "time": curr["t"],
                    "type": "LED_BLACKOUT", "severity": "medium",
                    "description": "LED off during formation phase",
                })

            # IMU/GPS quality
            if curr["health"]["gps_quality_label"] in ("BAD", "LOST"):
                anomalies.append({
                    "drone_id": did, "time": curr["t"],
                    "type": "GPS_QUALITY_LOW", "severity": "high",
                    "description": f"GPS: {curr['health']['gps_quality_label']}",
                })
            if curr["health"]["imu_quality_label"] in ("BAD", "DEGRADED"):
                anomalies.append({
                    "drone_id": did, "time": curr["t"],
                    "type": "IMU_ANOMALY", "severity": "high",
                    "description": f"IMU: {curr['health']['imu_quality_label']}",
                })

    anomalies.sort(key=lambda a: a["time"])
    logger.info("Detected %d anomalies", len(anomalies))
    return anomalies
