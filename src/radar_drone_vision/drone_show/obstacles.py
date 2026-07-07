"""Obstacle volume system — Canvas 2D shapes → 3D obstacle volumes.

Converts frontend Canvas drawings (rectangles, circles, polygons) into
3D obstacle volumes with safety buffers for path avoidance.

PRIVATE CORE: Avoidance logic stays backend-only.
"""

from __future__ import annotations

import math
import uuid
from typing import List, Optional

import numpy as np

from .schemas import FormationPoint


class ObstacleVolume:
    """A 3D obstacle volume with safety buffer."""

    def __init__(
        self,
        obstacle_id: str = "",
        name: str = "",
        obs_type: str = "box_volume",
        center: List[float] = [0, 0, 50],
        size: List[float] = [10, 10, 20],
        z_min: float = 0.0,
        z_max: float = 100.0,
        safety_buffer: float = 5.0,
        enabled: bool = True,
    ):
        self.obstacle_id = obstacle_id or f"obs_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.obs_type = obs_type
        self.center = center
        self.size = size
        self.z_min = z_min
        self.z_max = z_max
        self.safety_buffer = safety_buffer
        self.enabled = enabled

    def contains_point(self, x: float, y: float, z: float) -> bool:
        """Check if a 3D point is inside this obstacle (including buffer)."""
        if not self.enabled:
            return False

        buf = self.safety_buffer
        cx, cy, cz = self.center
        sx, sy, sz = self.size

        if z < self.z_min - buf or z > self.z_max + buf:
            return False

        if self.obs_type in ("box_volume", "polygon_prism"):
            half_x = sx / 2 + buf
            half_y = sy / 2 + buf
            return (abs(x - cx) <= half_x and abs(y - cy) <= half_y)

        elif self.obs_type in ("sphere_volume", "balloon"):
            r = max(sx, sy, sz) / 2 + buf
            dist = math.sqrt((x - cx)**2 + (y - cy)**2 + (z - cz)**2)
            return dist <= r

        elif self.obs_type == "cylinder_volume":
            r = max(sx, sy) / 2 + buf
            dist_2d = math.sqrt((x - cx)**2 + (y - cy)**2)
            return dist_2d <= r

        return False

    def distance_to_point(self, x: float, y: float, z: float) -> float:
        """Approximate signed distance (negative = inside)."""
        if not self.enabled:
            return float('inf')

        cx, cy, cz = self.center
        sx, sy, sz = self.size

        if self.obs_type in ("sphere_volume", "balloon"):
            r = max(sx, sy, sz) / 2 + self.safety_buffer
            dist = math.sqrt((x - cx)**2 + (y - cy)**2 + (z - cz)**2)
            return dist - r

        elif self.obs_type == "cylinder_volume":
            r = max(sx, sy) / 2 + self.safety_buffer
            dist_2d = math.sqrt((x - cx)**2 + (y - cy)**2)
            # Also check vertical bounds
            z_dist = min(abs(z - self.z_min), abs(z - self.z_max))
            if z < self.z_min or z > self.z_max:
                return min(dist_2d - r, z_dist)
            return dist_2d - r

        else:  # box
            half_x = sx / 2 + self.safety_buffer
            half_y = sy / 2 + self.safety_buffer
            dx = abs(x - cx) - half_x
            dy = abs(y - cy) - half_y
            dz = max(self.z_min - z, z - self.z_max, 0)
            return max(dx, dy, -dz) if dz == 0 else math.sqrt(max(dx, 0)**2 + max(dy, 0)**2 + dz**2)

    def to_dict(self) -> dict:
        return {
            "obstacle_id": self.obstacle_id,
            "name": self.name,
            "type": self.obs_type,
            "center": self.center,
            "size": self.size,
            "z_min": self.z_min,
            "z_max": self.z_max,
            "safety_buffer": self.safety_buffer,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ObstacleVolume":
        return cls(
            obstacle_id=d.get("obstacle_id", ""),
            name=d.get("name", ""),
            obs_type=d.get("type", "box_volume"),
            center=d.get("center", [0, 0, 50]),
            size=d.get("size", [10, 10, 20]),
            z_min=d.get("z_min", 0),
            z_max=d.get("z_max", 100),
            safety_buffer=d.get("safety_buffer", 5),
            enabled=d.get("enabled", True),
        )


class ObstacleRegistry:
    """Manages all obstacles for a project/scene."""

    def __init__(self):
        self.obstacles: List[ObstacleVolume] = []

    def add(self, obs: ObstacleVolume) -> str:
        self.obstacles.append(obs)
        return obs.obstacle_id

    def remove(self, obstacle_id: str) -> bool:
        before = len(self.obstacles)
        self.obstacles = [o for o in self.obstacles if o.obstacle_id != obstacle_id]
        return len(self.obstacles) < before

    def check_point(self, x: float, y: float, z: float) -> List[str]:
        """Return list of obstacle IDs that contain this point."""
        return [o.obstacle_id for o in self.obstacles if o.contains_point(x, y, z)]

    def min_distance(self, x: float, y: float, z: float) -> float:
        """Min distance to any obstacle (negative = inside)."""
        if not self.obstacles:
            return float('inf')
        return min(o.distance_to_point(x, y, z) for o in self.obstacles)

    def check_formation(self, points: List[FormationPoint]) -> dict:
        """Check all formation points against all obstacles."""
        violations = []
        min_dist = float('inf')
        for p in points:
            x, y, z = p.xyz
            d = self.min_distance(x, y, z)
            if d < min_dist:
                min_dist = d
            if d < 0:
                hits = self.check_point(x, y, z)
                violations.append({
                    "point_id": p.point_id,
                    "xyz": p.xyz,
                    "inside_obstacles": hits,
                    "distance": round(d, 2),
                })
        return {
            "min_obstacle_distance": round(min_dist, 2),
            "violations": violations,
            "safe": len(violations) == 0,
        }

    def to_list(self) -> List[dict]:
        return [o.to_dict() for o in self.obstacles]

    def from_list(self, data: List[dict]) -> None:
        self.obstacles = [ObstacleVolume.from_dict(d) for d in data]


def canvas_to_obstacle(canvas_data: dict, world_scale: float = 100.0) -> ObstacleVolume:
    """Convert a frontend Canvas shape to a 3D obstacle volume.

    canvas_data: {
        name, type (balloon/building/no_fly/stage),
        shape (rect/circle/polygon),
        canvas_x, canvas_y, canvas_w, canvas_h (normalized 0-1),
        z_min, z_max, safety_buffer
    }
    """
    shape = canvas_data.get("shape", "rect")
    obs_type_map = {
        "balloon": "sphere_volume",
        "building": "box_volume",
        "no_fly": "cylinder_volume",
        "stage": "box_volume",
    }
    obs_type = obs_type_map.get(canvas_data.get("type", "building"), "box_volume")

    # Canvas coords (0-1) → world coords (-scale/2 to +scale/2)
    cx = (canvas_data.get("canvas_x", 0.5) - 0.5) * world_scale
    cy = -(canvas_data.get("canvas_y", 0.5) - 0.5) * world_scale  # flip Y
    cw = canvas_data.get("canvas_w", 0.1) * world_scale
    ch = canvas_data.get("canvas_h", 0.1) * world_scale

    z_min = canvas_data.get("z_min", 0.0)
    z_max = canvas_data.get("z_max", 100.0)
    cz = (z_min + z_max) / 2

    return ObstacleVolume(
        name=canvas_data.get("name", "Obstacle"),
        obs_type=obs_type,
        center=[round(cx, 2), round(cy, 2), round(cz, 2)],
        size=[round(cw, 2), round(ch, 2), round(z_max - z_min, 2)],
        z_min=z_min,
        z_max=z_max,
        safety_buffer=canvas_data.get("safety_buffer", 5.0),
    )
