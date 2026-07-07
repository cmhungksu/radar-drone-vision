"""Failure simulation & replacement planning.

Simulates drone failures (GPS drift, low battery, LED blackout, etc.)
and plans visual replacements using backup drones.

SIMULATION_ONLY — all outputs are animation data, never real commands.
"""

from __future__ import annotations

import math
import uuid
from typing import List, Optional

import numpy as np


# Visual effects for different failure types
FAILURE_VISUAL = {
    "GPS_DRIFT": {"color": [255, 200, 0], "effect": "yellow_ring", "blink": False},
    "IMU_ANOMALY": {"color": [255, 140, 0], "effect": "orange_blink", "blink": True},
    "LOW_BATTERY": {"color": [128, 128, 128], "effect": "gray_ghost", "blink": False},
    "LED_BLACKOUT": {"color": [30, 30, 80], "effect": "dim_blue", "blink": False},
    "COMM_LOST": {"color": [255, 0, 0], "effect": "red_ghost", "blink": True},
    "DRONE_MISSING": {"color": [100, 0, 0], "effect": "red_fade", "blink": False},
}


def create_failure_scenario(
    drone_id: str,
    failure_type: str,
    start_time: float,
    duration: float = 10.0,
    candidate_pool: Optional[List[str]] = None,
) -> dict:
    """Create a failure scenario definition.

    SIMULATION_ONLY — for animation replay, not real flight control.
    """
    visual = FAILURE_VISUAL.get(failure_type, FAILURE_VISUAL["DRONE_MISSING"])

    return {
        "scenario_id": f"fail_{uuid.uuid4().hex[:8]}",
        "safety": "SIMULATION_ONLY",
        "target_drone": drone_id,
        "start_time": start_time,
        "duration": duration,
        "failure_type": failure_type,
        "visual_effect": {
            "drone_color": visual["effect"],
            "color_rgb": visual["color"],
            "trail": True,
            "blink": visual["blink"],
        },
        "replacement_policy": {
            "mode": "ANIMATION_ONLY_REBALANCE",
            "allow_real_command_export": False,
            "candidate_pool": candidate_pool or [],
            "objective": "minimize_visual_gap",
        },
    }


def apply_failure_to_state(
    flight_state: dict,
    scenario: dict,
) -> dict:
    """Apply a failure scenario to a flight state series.

    Modifies the target drone's state after start_time:
    - Marks status as failed
    - Changes LED to failure visualization color
    - Simulates position drift/freeze based on failure type

    Returns modified flight_state (copy).
    """
    import copy
    modified = copy.deepcopy(flight_state)

    target_id = scenario["target_drone"]
    start_t = scenario["start_time"]
    end_t = start_t + scenario["duration"]
    fail_type = scenario["failure_type"]

    for drone in modified.get("drones", []):
        if drone["drone_id"] != target_id:
            continue

        for frame in drone["frames"]:
            if frame["t"] < start_t:
                continue
            if frame["t"] > end_t:
                # After failure period: mark as recovered or removed
                frame["status"] = "RECOVERED" if fail_type != "DRONE_MISSING" else "REMOVED"
                continue

            # Apply failure effects
            frame["status"] = f"FAILURE_{fail_type}"
            vis = scenario["visual_effect"]
            frame["led"] = {
                "r": vis["color_rgb"][0],
                "g": vis["color_rgb"][1],
                "b": vis["color_rgb"][2],
                "on": True,
                "effect": vis["drone_color"],
            }

            # Position effects
            if fail_type == "GPS_DRIFT":
                # Gradual drift
                dt = frame["t"] - start_t
                frame["x"] += np.random.normal(0, dt * 0.3)
                frame["y"] += np.random.normal(0, dt * 0.3)
                frame["z"] += np.random.normal(0, dt * 0.1)
            elif fail_type == "DRONE_MISSING":
                # Freeze at last known position then fade
                pass  # position stays, visual fades
            elif fail_type == "LOW_BATTERY":
                # Slow descent
                dt = frame["t"] - start_t
                frame["z"] = max(0, frame["z"] - dt * 0.5)

            frame["health"]["battery_percent"] = max(0, frame["health"].get("battery_percent", 100) - int((frame["t"] - start_t) * 2))

    return modified


def plan_replacement(
    flight_state: dict,
    scenario: dict,
) -> dict:
    """Plan a visual replacement for a failed drone.

    Finds the best candidate from the pool to replace the failed drone's
    position in the formation. Returns animation data only.

    SIMULATION_ONLY — no real flight commands.
    """
    target_id = scenario["target_drone"]
    candidates = scenario["replacement_policy"].get("candidate_pool", [])
    start_t = scenario["start_time"]

    if not candidates:
        return {
            "replacement_planned": False,
            "reason": "No candidates in pool",
            "safety": "SIMULATION_ONLY",
        }

    # Find target's position at failure time
    target_pos = None
    target_led = [0, 100, 255]
    for drone in flight_state.get("drones", []):
        if drone["drone_id"] != target_id:
            continue
        for frame in drone["frames"]:
            if frame["t"] >= start_t:
                target_pos = [frame["x"], frame["y"], frame["z"]]
                target_led = [frame["led"]["r"], frame["led"]["g"], frame["led"]["b"]]
                break

    if target_pos is None:
        return {"replacement_planned": False, "reason": "Target position not found"}

    # Find closest candidate
    best_candidate = None
    best_dist = float('inf')

    for drone in flight_state.get("drones", []):
        if drone["drone_id"] not in candidates:
            continue
        for frame in drone["frames"]:
            if frame["t"] >= start_t:
                d = math.sqrt(
                    (frame["x"] - target_pos[0])**2 +
                    (frame["y"] - target_pos[1])**2 +
                    (frame["z"] - target_pos[2])**2
                )
                if d < best_dist:
                    best_dist = d
                    best_candidate = {
                        "drone_id": drone["drone_id"],
                        "position": [frame["x"], frame["y"], frame["z"]],
                        "distance": round(d, 2),
                    }
                break

    if best_candidate is None:
        return {"replacement_planned": False, "reason": "No reachable candidates"}

    return {
        "replacement_planned": True,
        "safety": "SIMULATION_ONLY",
        "failed_drone": target_id,
        "replacement_drone": best_candidate["drone_id"],
        "target_position": target_pos,
        "candidate_start_position": best_candidate["position"],
        "transit_distance": best_candidate["distance"],
        "estimated_transit_time": round(best_candidate["distance"] / 8.0, 1),
        "led_sequence": [
            {"t": 0.0, "rgb": [0, 255, 0], "note": "green marker (replacement identified)"},
            {"t": 1.0, "rgb": [0, 200, 100], "note": "transitioning"},
            {"t": best_candidate["distance"] / 8.0, "rgb": target_led, "note": "match target LED"},
        ],
    }
