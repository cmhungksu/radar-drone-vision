"""Bay inventory and drone health management.

Manages the drone-in-a-box carrier: bay slots, battery status,
health checks, role assignment (primary/reserve).

SIMULATION_ONLY.
"""

from __future__ import annotations

import uuid
from typing import List, Optional


class DroneBay:
    """A single bay slot in the carrier."""

    def __init__(self, bay_id: str, drone_id: Optional[str] = None,
                 battery_percent: int = 100, health: str = "ready",
                 role: str = "primary", charging: bool = False):
        self.bay_id = bay_id
        self.drone_id = drone_id
        self.battery_percent = battery_percent
        self.health = health  # ready, launched, charging, fault, empty
        self.led_health = "ready"
        self.gps_health = "sim_ready"
        self.imu_health = "sim_ready"
        self.role = role  # primary, reserve
        self.charging = charging
        self.launch_count = 0

    def to_dict(self) -> dict:
        return {
            "bay_id": self.bay_id,
            "drone_id": self.drone_id,
            "battery_percent": self.battery_percent,
            "health": self.health,
            "led_health": self.led_health,
            "gps_health": self.gps_health,
            "imu_health": self.imu_health,
            "role": self.role,
            "charging": self.charging,
            "launch_count": self.launch_count,
        }


class CarrierConfig:
    """Vehicle carrier configuration."""

    def __init__(
        self,
        name: str = "EV Drone Carrier A",
        carrier_type: str = "parked_vehicle_dock",
        vehicle_dims: tuple = (6.2, 2.1, 2.4),
        position: List[float] = [0, 0, 0],
        max_launch_slots: int = 4,
        max_recovery_slots: int = 2,
        bay_count: int = 60,
        reserve_count: int = 10,
    ):
        self.name = name
        self.carrier_type = carrier_type
        self.length, self.width, self.height = vehicle_dims
        self.position = position
        self.max_launch_slots = max_launch_slots
        self.max_recovery_slots = max_recovery_slots
        self.bay_count = bay_count
        self.reserve_count = reserve_count

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.carrier_type,
            "vehicle_length_m": self.length,
            "vehicle_width_m": self.width,
            "vehicle_height_m": self.height,
            "dock_position_world": self.position,
            "max_simultaneous_launch_slots": self.max_launch_slots,
            "max_simultaneous_recovery_slots": self.max_recovery_slots,
            "bay_count": self.bay_count,
            "reserve_count": self.reserve_count,
            "safety": {
                "parked_only": True,
                "real_flight_export_enabled": False,
                "minimum_operator_count_required": 2,
                "require_manual_review": True,
            },
        }


class BayManager:
    """Manages all bay slots and drone inventory in a carrier."""

    def __init__(self, config: Optional[CarrierConfig] = None):
        self.config = config or CarrierConfig()
        self.bays: List[DroneBay] = []
        self._initialize_bays()

    def _initialize_bays(self):
        """Create bay slots with drones pre-loaded."""
        total = self.config.bay_count
        reserve = self.config.reserve_count
        primary = total - reserve

        self.bays = []
        for i in range(total):
            role = "primary" if i < primary else "reserve"
            bay = DroneBay(
                bay_id=f"BAY-{i+1:02d}",
                drone_id=f"D{i+1:04d}",
                battery_percent=95 + (i % 6),  # 95-100%
                health="ready",
                role=role,
            )
            self.bays.append(bay)

    def get_ready_drones(self, role: Optional[str] = None) -> List[DroneBay]:
        """Get all drones that are ready for launch."""
        return [b for b in self.bays
                if b.health == "ready"
                and b.drone_id is not None
                and b.battery_percent >= 30
                and (role is None or b.role == role)]

    def get_reserves(self) -> List[DroneBay]:
        return self.get_ready_drones(role="reserve")

    def launch_drone(self, bay_id: str) -> Optional[str]:
        """Mark a drone as launched. Returns drone_id."""
        for bay in self.bays:
            if bay.bay_id == bay_id and bay.health == "ready":
                bay.health = "launched"
                bay.launch_count += 1
                return bay.drone_id
        return None

    def recover_drone(self, drone_id: str) -> Optional[str]:
        """Mark a drone as recovered and start charging."""
        for bay in self.bays:
            if bay.drone_id == drone_id and bay.health == "launched":
                bay.health = "charging"
                bay.charging = True
                bay.battery_percent = max(10, bay.battery_percent - 20)  # depleted
                return bay.bay_id
        return None

    def simulate_charging(self, minutes: float = 30.0, rate_per_min: float = 2.0):
        """Simulate charging for all docked drones."""
        for bay in self.bays:
            if bay.charging:
                bay.battery_percent = min(100, bay.battery_percent + int(minutes * rate_per_min))
                if bay.battery_percent >= 95:
                    bay.health = "ready"
                    bay.charging = False

    def get_inventory(self) -> dict:
        return {
            "schema": "drone_bay_inventory.v1",
            "mode": "SIMULATION_ONLY",
            "carrier": self.config.to_dict(),
            "total_bays": len(self.bays),
            "ready": len(self.get_ready_drones()),
            "launched": len([b for b in self.bays if b.health == "launched"]),
            "charging": len([b for b in self.bays if b.charging]),
            "reserves": len(self.get_reserves()),
            "drones": [b.to_dict() for b in self.bays],
        }
