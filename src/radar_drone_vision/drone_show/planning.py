"""Formation planning — ground grid, assignment, Bezier paths, timeline.

PRIVATE CORE: This module must NOT be exposed to the frontend.
All output is SIMULATION_ONLY.
"""

from __future__ import annotations

import math
import uuid
from typing import List, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

from .led import TAKEOFF_BLUE_888, HOLD_BLUE_888, rgb888_to_rgb565
from .schemas import FormationFrame, FormationPoint, TimelinePlan


def generate_ground_grid(drone_count: int, spacing: float = 3.0) -> List[List[float]]:
    """Generate a grid of ground takeoff positions centered at origin."""
    cols = int(math.ceil(math.sqrt(drone_count)))
    rows = int(math.ceil(drone_count / cols))
    positions = []
    for r in range(rows):
        for c in range(cols):
            if len(positions) >= drone_count:
                break
            x = (c - (cols - 1) / 2) * spacing
            y = (r - (rows - 1) / 2) * spacing
            positions.append([round(x, 2), round(y, 2), 0.0])
    return positions[:drone_count]


def assign_drones_to_formation(
    ground_positions: List[List[float]],
    formation_points: List[FormationPoint],
) -> List[int]:
    """Drone-to-point assignment.

    Uses Hungarian (optimal) for ≤500 drones, greedy nearest-neighbor for larger.
    Returns assignment[i] = index into formation_points for drone i.
    """
    n = len(ground_positions)
    m = len(formation_points)
    assert n == m, f"Mismatch: {n} ground positions vs {m} formation points"

    if n <= 500:
        # Optimal O(n³) — feasible for small counts
        cost = np.zeros((n, m), dtype=np.float64)
        for i, gp in enumerate(ground_positions):
            for j, fp in enumerate(formation_points):
                dx = gp[0] - fp.xyz[0]
                dy = gp[1] - fp.xyz[1]
                dz = gp[2] - fp.xyz[2]
                cost[i, j] = math.sqrt(dx*dx + dy*dy + dz*dz)

        row_ind, col_ind = linear_sum_assignment(cost)
        assignment = [0] * n
        for r, c in zip(row_ind, col_ind):
            assignment[r] = c
        return assignment
    else:
        # Greedy nearest-neighbor O(n²) — fast for 500+ drones
        from scipy.spatial import KDTree
        fp_coords = np.array([fp.xyz for fp in formation_points])
        gp_coords = np.array(ground_positions)
        tree = KDTree(fp_coords)

        assignment = [0] * n
        used = set()
        # Sort ground positions by distance to center for better assignment
        center = gp_coords.mean(axis=0)
        order = np.argsort(np.linalg.norm(gp_coords - center, axis=1))

        for idx in order:
            _, candidates = tree.query(gp_coords[idx], k=min(20, m))
            if isinstance(candidates, (int, np.integer)):
                candidates = [candidates]
            for c in candidates:
                if c not in used:
                    assignment[idx] = int(c)
                    used.add(c)
                    break
            else:
                # Fallback: find any unused
                for j in range(m):
                    if j not in used:
                        assignment[idx] = j
                        used.add(j)
                        break

        return assignment


def generate_bezier_path(
    start: List[float],
    end: List[float],
    safe_altitude: float = 30.0,
) -> List[List[float]]:
    """Generate a simple Bezier path with altitude waypoint.

    For takeoff: go up first, then move horizontally to target.
    Returns 3-4 control points.
    """
    sx, sy, sz = start
    ex, ey, ez = end

    # Waypoint: rise to safe altitude directly above start
    mid_z = max(safe_altitude, ez + 5.0)
    mid_x = (sx + ex) / 2
    mid_y = (sy + ey) / 2

    if sz < 1.0:  # Starting from ground
        return [
            [round(sx, 2), round(sy, 2), round(sz, 2)],
            [round(sx, 2), round(sy, 2), round(mid_z, 2)],  # rise up
            [round(mid_x, 2), round(mid_y, 2), round(ez + 5, 2)],  # mid transit
            [round(ex, 2), round(ey, 2), round(ez, 2)],  # final position
        ]
    else:
        return [
            [round(sx, 2), round(sy, 2), round(sz, 2)],
            [round(mid_x, 2), round(mid_y, 2), round(max(sz, ez) + 3, 2)],
            [round(ex, 2), round(ey, 2), round(ez, 2)],
        ]


def compute_risk_metrics(
    ground_positions: List[List[float]],
    formation_points: List[FormationPoint],
    assignment: List[int],
) -> dict:
    """Compute basic feasibility metrics."""
    # Min distance between formation points
    n = len(formation_points)
    min_dist = float('inf')
    for i in range(n):
        for j in range(i + 1, n):
            d = math.sqrt(sum((a - b)**2 for a, b in zip(
                formation_points[i].xyz, formation_points[j].xyz)))
            if d < min_dist:
                min_dist = d

    # Max travel distance
    max_travel = 0.0
    total_travel = 0.0
    for i, ai in enumerate(assignment):
        fp = formation_points[ai]
        d = math.sqrt(sum((a - b)**2 for a, b in zip(ground_positions[i], fp.xyz)))
        max_travel = max(max_travel, d)
        total_travel += d

    warnings = []
    if min_dist < 1.5:
        warnings.append(f"FORMATION_TOO_DENSE: min distance {min_dist:.2f}m < 1.5m")
    if min_dist < 3.0:
        warnings.append(f"FORMATION_TIGHT: min distance {min_dist:.2f}m, recommend > 3.0m")
    if max_travel > 100.0:
        warnings.append(f"LONG_TRANSIT: max travel {max_travel:.1f}m, may need longer transition")

    return {
        "min_drone_distance": round(min_dist, 3),
        "max_travel_distance": round(max_travel, 2),
        "avg_travel_distance": round(total_travel / max(n, 1), 2),
        "max_speed_index": round(max_travel / 8.0, 2),  # assuming 8s transition
        "path_crossing_count": 0,  # TODO: implement crossing detection
        "warnings": warnings,
    }


def create_timeline_plan(
    formation_frame: FormationFrame,
    takeoff_duration: float = 8.0,
    hold_duration: float = 6.0,
    landing_duration: float = 8.0,
) -> Tuple[TimelinePlan, dict]:
    """Create a complete timeline plan for a single-image show.

    Returns (TimelinePlan, risk_metrics).
    """
    drone_count = formation_frame.drone_count
    points = formation_frame.points

    # 1. Ground grid
    ground = generate_ground_grid(drone_count)

    # 2. Assignment
    assignment = assign_drones_to_formation(ground, points)

    # 3. Risk metrics
    risk = compute_risk_metrics(ground, points, assignment)

    # 4. Build drone paths
    plan_id = f"plan_{uuid.uuid4().hex[:8]}"
    drones = []

    for drone_idx in range(drone_count):
        fp_idx = assignment[drone_idx]
        fp = points[fp_idx]
        gp = ground[drone_idx]

        # Takeoff segment: ground → formation point
        takeoff_path = generate_bezier_path(gp, fp.xyz, safe_altitude=30.0)

        # Landing segment: formation point → ground (reverse)
        landing_path = generate_bezier_path(fp.xyz, gp, safe_altitude=30.0)

        drone_id = f"D{drone_idx:04d}"
        segments = [
            {
                "drone_id": drone_id,
                "segment_id": f"S{drone_idx:04d}_takeoff",
                "from_frame": "ground",
                "to_frame": formation_frame.frame_id,
                "control_points": takeoff_path,
                "duration_sec": takeoff_duration,
                "led_timeline": [
                    {"t": 0.0, "rgb888": list(TAKEOFF_BLUE_888), "rgb565": rgb888_to_rgb565(*TAKEOFF_BLUE_888)},
                    {"t": takeoff_duration * 0.8, "rgb888": list(HOLD_BLUE_888), "rgb565": rgb888_to_rgb565(*HOLD_BLUE_888)},
                    {"t": takeoff_duration, "rgb888": fp.rgb888, "rgb565": fp.rgb565},
                ],
            },
            {
                "drone_id": drone_id,
                "segment_id": f"S{drone_idx:04d}_hold",
                "from_frame": formation_frame.frame_id,
                "to_frame": formation_frame.frame_id,
                "control_points": [fp.xyz, fp.xyz],
                "duration_sec": hold_duration,
                "led_timeline": [
                    {"t": 0.0, "rgb888": fp.rgb888, "rgb565": fp.rgb565},
                ],
            },
            {
                "drone_id": drone_id,
                "segment_id": f"S{drone_idx:04d}_landing",
                "from_frame": formation_frame.frame_id,
                "to_frame": "ground",
                "control_points": landing_path,
                "duration_sec": landing_duration,
                "led_timeline": [
                    {"t": 0.0, "rgb888": fp.rgb888, "rgb565": fp.rgb565},
                    {"t": landing_duration * 0.2, "rgb888": list(HOLD_BLUE_888), "rgb565": rgb888_to_rgb565(*HOLD_BLUE_888)},
                    {"t": landing_duration, "rgb888": list(TAKEOFF_BLUE_888), "rgb565": rgb888_to_rgb565(*TAKEOFF_BLUE_888)},
                ],
            },
        ]

        drones.append({
            "drone_id": drone_id,
            "ground_position": gp,
            "formation_point": fp.model_dump(),
            "segments": segments,
        })

    total_duration = takeoff_duration + hold_duration + landing_duration

    plan = TimelinePlan(
        plan_id=plan_id,
        drone_count=drone_count,
        total_duration_sec=total_duration,
        frames=["ground", formation_frame.frame_id, "ground"],
        drones=drones,
        metadata={
            "algorithm_version": "v1.0-mvp",
            "safety_profile": "simulation_only",
            "formation_frame_id": formation_frame.frame_id,
            "detail_score": formation_frame.detail_score,
            **risk,
        },
    )

    return plan, risk
