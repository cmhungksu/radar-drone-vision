"""Multi-frame storyboard — manage multiple formation frames and transitions.

Handles the core workflow:
1. Multiple images → multiple FormationFrames
2. Transition planning between consecutive frames (re-assignment)
3. Complete timeline generation with takeoff → frame1 → frame2 → ... → landing

PRIVATE CORE: Transition assignment and path optimization stay backend-only.
"""

from __future__ import annotations

import math
import uuid
from typing import List, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

from .led import TAKEOFF_BLUE_888, HOLD_BLUE_888, rgb888_to_rgb565
from .planning import generate_ground_grid, generate_bezier_path
from .schemas import FormationFrame, FormationPoint, TimelinePlan


def plan_transition(
    from_points: List[FormationPoint],
    to_points: List[FormationPoint],
    transition_duration: float = 5.0,
) -> List[dict]:
    """Plan optimal drone-to-point re-assignment for a frame transition.

    Uses Hungarian algorithm on distance cost matrix.
    Returns list of {drone_idx, from_point, to_point, path, led_timeline}.
    """
    n = len(from_points)
    m = len(to_points)

    if n != m:
        raise ValueError(f"Frame point count mismatch: {n} vs {m}")

    # Cost matrix: Euclidean distance + color change penalty
    cost = np.zeros((n, m), dtype=np.float64)
    for i, fp in enumerate(from_points):
        for j, tp in enumerate(to_points):
            dx = fp.xyz[0] - tp.xyz[0]
            dy = fp.xyz[1] - tp.xyz[1]
            dz = fp.xyz[2] - tp.xyz[2]
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)

            # Color change penalty (encourage color continuity)
            color_diff = sum(abs(a - b) for a, b in zip(fp.rgb888, tp.rgb888)) / 765.0
            cost[i, j] = dist + color_diff * 5.0  # weight color penalty

    row_ind, col_ind = linear_sum_assignment(cost)

    transitions = []
    for r, c in zip(row_ind, col_ind):
        fp = from_points[r]
        tp = to_points[c]
        path = generate_bezier_path(fp.xyz, tp.xyz, safe_altitude=max(fp.xyz[2], tp.xyz[2]) + 3)

        # LED: fade from source color to target color
        led_timeline = [
            {"t": 0.0, "rgb888": fp.rgb888, "rgb565": fp.rgb565},
            {"t": transition_duration * 0.4, "rgb888": fp.rgb888, "rgb565": fp.rgb565},
            {"t": transition_duration * 0.8, "rgb888": tp.rgb888, "rgb565": tp.rgb565},
            {"t": transition_duration, "rgb888": tp.rgb888, "rgb565": tp.rgb565},
        ]

        transitions.append({
            "from_idx": int(r),
            "to_idx": int(c),
            "from_point": fp,
            "to_point": tp,
            "control_points": path,
            "duration_sec": transition_duration,
            "led_timeline": led_timeline,
            "distance": float(cost[r, c]),
        })

    return transitions


def create_multi_frame_timeline(
    frames: List[FormationFrame],
    takeoff_duration: float = 8.0,
    hold_duration: float = 6.0,
    transition_duration: float = 5.0,
    landing_duration: float = 8.0,
) -> Tuple[TimelinePlan, dict]:
    """Create a complete timeline plan for a multi-image show.

    Sequence: ground → takeoff → frame[0] hold → transition → frame[1] hold → ... → landing → ground
    """
    if not frames:
        raise ValueError("No frames provided")

    drone_count = frames[0].drone_count
    for f in frames:
        if f.drone_count != drone_count:
            raise ValueError(f"All frames must have same drone_count ({drone_count} vs {f.drone_count})")

    plan_id = f"plan_{uuid.uuid4().hex[:8]}"
    ground = generate_ground_grid(drone_count)

    # Initial assignment: ground → first frame
    from .planning import assign_drones_to_formation
    first_assignment = assign_drones_to_formation(ground, frames[0].points)

    # Build per-drone segment lists
    drones = []
    for drone_idx in range(drone_count):
        drones.append({
            "drone_id": f"D{drone_idx:04d}",
            "ground_position": ground[drone_idx],
            "segments": [],
        })

    # Current position tracking (which point each drone is at)
    current_points = [None] * drone_count  # FormationPoint for each drone

    # ── Segment 1: Takeoff (ground → first frame) ──
    t_offset = 0.0
    for drone_idx in range(drone_count):
        fp_idx = first_assignment[drone_idx]
        fp = frames[0].points[fp_idx]
        gp = ground[drone_idx]

        path = generate_bezier_path(gp, fp.xyz, safe_altitude=30.0)
        segment = {
            "segment_id": f"S{drone_idx:04d}_takeoff",
            "from_frame": "ground",
            "to_frame": frames[0].frame_id,
            "control_points": path,
            "duration_sec": takeoff_duration,
            "t_start": t_offset,
            "led_timeline": [
                {"t": 0.0, "rgb888": list(TAKEOFF_BLUE_888), "rgb565": rgb888_to_rgb565(*TAKEOFF_BLUE_888)},
                {"t": takeoff_duration * 0.8, "rgb888": list(HOLD_BLUE_888), "rgb565": rgb888_to_rgb565(*HOLD_BLUE_888)},
                {"t": takeoff_duration, "rgb888": fp.rgb888, "rgb565": fp.rgb565},
            ],
        }
        drones[drone_idx]["segments"].append(segment)
        current_points[drone_idx] = fp

    t_offset += takeoff_duration

    # ── For each frame: hold + transition to next ──
    frame_ids = [frames[0].frame_id]

    for frame_idx in range(len(frames)):
        # Hold at current frame
        for drone_idx in range(drone_count):
            cp = current_points[drone_idx]
            segment = {
                "segment_id": f"S{drone_idx:04d}_hold_{frame_idx}",
                "from_frame": frames[frame_idx].frame_id,
                "to_frame": frames[frame_idx].frame_id,
                "control_points": [cp.xyz, cp.xyz],
                "duration_sec": hold_duration,
                "t_start": t_offset,
                "led_timeline": [{"t": 0.0, "rgb888": cp.rgb888, "rgb565": cp.rgb565}],
            }
            drones[drone_idx]["segments"].append(segment)

        t_offset += hold_duration

        # Transition to next frame (if not last)
        if frame_idx < len(frames) - 1:
            next_frame = frames[frame_idx + 1]
            frame_ids.append(next_frame.frame_id)

            # Re-assign drones for transition
            from_pts = [current_points[i] for i in range(drone_count)]
            to_pts = next_frame.points
            transitions = plan_transition(from_pts, to_pts, transition_duration)

            # Build drone index mapping
            for trans in transitions:
                from_drone_idx = trans["from_idx"]
                to_fp = trans["to_point"]

                segment = {
                    "segment_id": f"S{from_drone_idx:04d}_trans_{frame_idx}to{frame_idx+1}",
                    "from_frame": frames[frame_idx].frame_id,
                    "to_frame": next_frame.frame_id,
                    "control_points": trans["control_points"],
                    "duration_sec": transition_duration,
                    "t_start": t_offset,
                    "led_timeline": trans["led_timeline"],
                }
                drones[from_drone_idx]["segments"].append(segment)
                current_points[from_drone_idx] = to_fp

            t_offset += transition_duration

    # ── Final: Landing ──
    for drone_idx in range(drone_count):
        cp = current_points[drone_idx]
        gp = ground[drone_idx]
        path = generate_bezier_path(cp.xyz, gp, safe_altitude=30.0)

        segment = {
            "segment_id": f"S{drone_idx:04d}_landing",
            "from_frame": frames[-1].frame_id,
            "to_frame": "ground",
            "control_points": path,
            "duration_sec": landing_duration,
            "t_start": t_offset,
            "led_timeline": [
                {"t": 0.0, "rgb888": cp.rgb888, "rgb565": cp.rgb565},
                {"t": landing_duration * 0.2, "rgb888": list(HOLD_BLUE_888), "rgb565": rgb888_to_rgb565(*HOLD_BLUE_888)},
                {"t": landing_duration, "rgb888": list(TAKEOFF_BLUE_888), "rgb565": rgb888_to_rgb565(*TAKEOFF_BLUE_888)},
            ],
        }
        drones[drone_idx]["segments"].append(segment)

    t_offset += landing_duration
    total_duration = t_offset

    # Add formation_point to each drone (last position for preview)
    for drone_idx in range(drone_count):
        cp = current_points[drone_idx]
        drones[drone_idx]["formation_point"] = cp.model_dump() if cp else {}

    # Risk metrics
    min_dist = float('inf')
    for f in frames:
        for i in range(len(f.points)):
            for j in range(i + 1, len(f.points)):
                d = math.sqrt(sum((a - b)**2 for a, b in zip(f.points[i].xyz, f.points[j].xyz)))
                if d < min_dist:
                    min_dist = d

    risk = {
        "min_drone_distance": round(min_dist, 3),
        "max_speed_index": round(max(
            math.sqrt(sum((a - b)**2 for a, b in zip(
                drones[i]["segments"][0]["control_points"][0],
                drones[i]["segments"][0]["control_points"][-1]
            ))) / takeoff_duration
            for i in range(drone_count)
        ), 2),
        "path_crossing_count": 0,
        "frame_count": len(frames),
        "transition_count": len(frames) - 1,
        "warnings": [],
    }
    if min_dist < 1.5:
        risk["warnings"].append(f"FORMATION_TOO_DENSE: min {min_dist:.2f}m")
    if min_dist < 3.0:
        risk["warnings"].append(f"FORMATION_TIGHT: min {min_dist:.2f}m, recommend > 3.0m")

    plan = TimelinePlan(
        plan_id=plan_id,
        drone_count=drone_count,
        total_duration_sec=total_duration,
        frames=["ground"] + frame_ids + ["ground"],
        drones=drones,
        metadata={
            "algorithm_version": "v1.1-multi-frame",
            "safety_profile": "simulation_only",
            "frame_count": len(frames),
            **risk,
        },
    )

    return plan, risk
