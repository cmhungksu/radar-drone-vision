"""Launch & recovery scheduling for carrier-based drone shows.

Plans sequential launch waves, air waiting zones, formation arrival
timing, and recovery sequencing.

SIMULATION_ONLY — no real flight control output.
"""

from __future__ import annotations

import math
import uuid
from typing import List, Optional, Tuple

from .bay_manager import BayManager, CarrierConfig


class WaitZone:
    """An air waiting zone for drones between launch and formation entry."""

    def __init__(self, zone_id: str, center: List[float],
                 radius: float = 15.0, altitude_layer: int = 0):
        self.zone_id = zone_id
        self.center = center
        self.radius = radius
        self.altitude_layer = altitude_layer
        self.assigned_drones: List[str] = []

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "center": self.center,
            "radius": self.radius,
            "altitude_layer": self.altitude_layer,
            "assigned_count": len(self.assigned_drones),
        }


def create_wait_zones(
    carrier_pos: List[float],
    n_zones: int = 4,
    base_altitude: float = 25.0,
    altitude_step: float = 10.0,
    offset_distance: float = 30.0,
) -> List[WaitZone]:
    """Create wait zones around the carrier, at different altitude layers."""
    zones = []
    for i in range(n_zones):
        angle = (i / n_zones) * 2 * math.pi
        cx = carrier_pos[0] + offset_distance * math.sin(angle)
        cy = carrier_pos[1] + offset_distance * math.cos(angle)
        cz = base_altitude + i * altitude_step
        zones.append(WaitZone(
            zone_id=f"WZ-{chr(65 + i)}-{i+1:02d}",
            center=[round(cx, 2), round(cy, 2), round(cz, 2)],
            altitude_layer=i,
        ))
    return zones


def plan_launch_schedule(
    bay_manager: BayManager,
    formation_points: List[dict],
    wait_zones: Optional[List[WaitZone]] = None,
    launch_interval_sec: float = 3.0,
    ascent_time_sec: float = 5.0,
    wait_to_formation_sec: float = 4.0,
) -> dict:
    """Plan a complete launch schedule for carrier-based show.

    Returns launch_schedule with waves, timing, wait zone assignments,
    and energy estimates.

    SIMULATION_ONLY.
    """
    config = bay_manager.config
    ready = bay_manager.get_ready_drones(role="primary")
    n_drones = min(len(ready), len(formation_points))
    max_slots = config.max_launch_slots

    if wait_zones is None:
        wait_zones = create_wait_zones(config.position)

    # Calculate waves
    n_waves = math.ceil(n_drones / max_slots)
    wave_duration = launch_interval_sec + ascent_time_sec

    launch_plan = []
    wave_num = 0

    for i in range(n_drones):
        slot_in_wave = i % max_slots
        if slot_in_wave == 0 and i > 0:
            wave_num += 1

        bay = ready[i]
        wz = wait_zones[i % len(wait_zones)]
        wz.assigned_drones.append(bay.drone_id)

        time_offset = wave_num * wave_duration + slot_in_wave * (launch_interval_sec / max_slots)

        # Formation point assignment (simple sequential for now)
        fp = formation_points[i] if i < len(formation_points) else {}

        entry = {
            "wave": wave_num + 1,
            "slot_index": slot_in_wave,
            "time_offset_sec": round(time_offset, 1),
            "drone_id": bay.drone_id,
            "bay_id": bay.bay_id,
            "battery_at_launch": bay.battery_percent,
            "led_state_during_ascent": "off",
            "target_wait_zone": wz.zone_id,
            "wait_zone_position": wz.center,
            "wait_arrival_time": round(time_offset + ascent_time_sec, 1),
            "formation_entry_time": round(time_offset + ascent_time_sec + wait_to_formation_sec, 1),
            "first_formation_point": fp.get("point_id", f"P{i+1:04d}"),
            "estimated_battery_at_formation": bay.battery_percent - 3,  # ~3% for ascent+wait
        }
        launch_plan.append(entry)

    # Total timing
    last_entry = launch_plan[-1] if launch_plan else {"formation_entry_time": 0}
    all_in_formation_time = last_entry["formation_entry_time"] + 2.0  # buffer

    # Energy budget
    avg_battery = sum(e["estimated_battery_at_formation"] for e in launch_plan) / max(len(launch_plan), 1)
    min_battery = min((e["estimated_battery_at_formation"] for e in launch_plan), default=100)

    return {
        "schema": "launch_schedule.v1",
        "mode": "SIMULATION_ONLY",
        "show_id": f"carrier-show-{uuid.uuid4().hex[:6]}",
        "carrier": config.name,
        "total_drones": n_drones,
        "total_waves": n_waves,
        "drones_per_wave": max_slots,
        "wave_interval_sec": round(wave_duration, 1),
        "all_in_formation_time_sec": round(all_in_formation_time, 1),
        "wait_zones": [wz.to_dict() for wz in wait_zones],
        "energy_budget": {
            "avg_battery_at_formation": round(avg_battery, 1),
            "min_battery_at_formation": min_battery,
            "estimated_show_drain_percent": 15,
            "estimated_recovery_drain_percent": 5,
        },
        "launch_plan": launch_plan,
    }


def plan_recovery_schedule(
    bay_manager: BayManager,
    launch_schedule: dict,
    recovery_interval_sec: float = 4.0,
) -> dict:
    """Plan recovery (landing back into carrier) after show completion.

    Reverse order of launch, staggered by recovery slots.
    SIMULATION_ONLY.
    """
    config = bay_manager.config
    max_recovery = config.max_recovery_slots
    launch_plan = launch_schedule.get("launch_plan", [])

    # Reverse order for recovery
    recovery_plan = []
    for i, entry in enumerate(reversed(launch_plan)):
        wave = i // max_recovery
        slot = i % max_recovery
        time_offset = wave * recovery_interval_sec + slot * (recovery_interval_sec / max_recovery)

        recovery_plan.append({
            "recovery_wave": wave + 1,
            "slot_index": slot,
            "time_offset_sec": round(time_offset, 1),
            "drone_id": entry["drone_id"],
            "target_bay_id": entry["bay_id"],
            "estimated_battery_at_landing": entry["estimated_battery_at_formation"] - 20,
            "charging_needed": True,
            "estimated_charge_time_min": 25,
        })

    total_recovery_time = (len(launch_plan) / max_recovery) * recovery_interval_sec

    return {
        "schema": "recovery_schedule.v1",
        "mode": "SIMULATION_ONLY",
        "total_drones": len(recovery_plan),
        "total_recovery_waves": math.ceil(len(recovery_plan) / max_recovery),
        "total_recovery_time_sec": round(total_recovery_time, 1),
        "recovery_plan": recovery_plan,
    }
