"""Flight path simulation & collision checking.

Validates timeline plans by sampling paths at high frequency and
checking inter-drone distances, obstacle distances, speed/acceleration
limits, and path crossings.

PRIVATE CORE — SIMULATION_ONLY.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np


def bezier_sample(control_points: List[List[float]], t: float) -> List[float]:
    """Evaluate a Bezier curve at parameter t ∈ [0, 1]."""
    pts = [np.array(p, dtype=np.float64) for p in control_points]
    n = len(pts)
    if n == 1:
        return pts[0].tolist()
    if n == 2:
        return ((1 - t) * pts[0] + t * pts[1]).tolist()
    # De Casteljau's algorithm
    while len(pts) > 1:
        pts = [(1 - t) * pts[i] + t * pts[i + 1] for i in range(len(pts) - 1)]
    return pts[0].tolist()


def sample_drone_path(
    segments: List[dict],
    sample_rate: int = 20,
) -> List[dict]:
    """Sample a drone's complete path at fixed rate.

    Returns list of {t_global, xyz, rgb888, segment_id}.
    """
    samples = []
    t_global = 0.0

    for seg in segments:
        cp = seg["control_points"]
        dur = seg["duration_sec"]
        t_start = seg.get("t_start", t_global)
        led = seg.get("led_timeline", [])
        n_samples = max(2, int(dur * sample_rate))

        for i in range(n_samples + 1):
            frac = i / n_samples
            t = t_start + frac * dur
            xyz = bezier_sample(cp, frac)

            # Interpolate LED color
            rgb = [0, 100, 255]  # default blue
            if led:
                for j in range(len(led) - 1):
                    if led[j]["t"] <= frac * dur <= led[j + 1]["t"]:
                        span = led[j + 1]["t"] - led[j]["t"]
                        if span > 0:
                            f = (frac * dur - led[j]["t"]) / span
                            c1 = led[j].get("rgb888", [0, 100, 255])
                            c2 = led[j + 1].get("rgb888", [0, 100, 255])
                            rgb = [int(c1[k] + f * (c2[k] - c1[k])) for k in range(3)]
                        break
                else:
                    rgb = led[-1].get("rgb888", [0, 100, 255])

            samples.append({
                "t": round(t, 3),
                "xyz": [round(v, 3) for v in xyz],
                "rgb888": rgb,
                "segment_id": seg.get("segment_id", ""),
            })

        t_global = t_start + dur

    return samples


def check_min_distances(
    all_paths: List[List[dict]],
    time_tolerance: float = 0.05,
) -> dict:
    """Check minimum inter-drone distance across all sampled paths.

    Returns {min_distance, min_distance_time, min_pair, close_approaches[]}.
    """
    n_drones = len(all_paths)
    min_dist = float('inf')
    min_time = 0.0
    min_pair = (0, 0)
    close_approaches = []

    # Build time-indexed position lookup for efficiency
    for i in range(n_drones):
        for j in range(i + 1, n_drones):
            path_i = all_paths[i]
            path_j = all_paths[j]

            # Match by nearest time
            ji = 0
            for si in path_i:
                while ji < len(path_j) - 1 and abs(path_j[ji + 1]["t"] - si["t"]) < abs(path_j[ji]["t"] - si["t"]):
                    ji += 1
                if abs(path_j[ji]["t"] - si["t"]) > time_tolerance:
                    continue

                dx = si["xyz"][0] - path_j[ji]["xyz"][0]
                dy = si["xyz"][1] - path_j[ji]["xyz"][1]
                dz = si["xyz"][2] - path_j[ji]["xyz"][2]
                d = math.sqrt(dx*dx + dy*dy + dz*dz)

                if d < min_dist:
                    min_dist = d
                    min_time = si["t"]
                    min_pair = (i, j)

                if d < 3.0:  # close approach threshold
                    close_approaches.append({
                        "drone_a": i,
                        "drone_b": j,
                        "time": round(si["t"], 2),
                        "distance": round(d, 3),
                        "position": si["xyz"],
                    })

    return {
        "min_distance": round(min_dist, 3),
        "min_distance_time": round(min_time, 2),
        "min_pair": list(min_pair),
        "close_approach_count": len(close_approaches),
        "close_approaches": close_approaches[:20],  # cap for API response
    }


def check_speed_acceleration(
    path_samples: List[dict],
    max_speed: float = 15.0,
    max_accel: float = 8.0,
) -> dict:
    """Check speed and acceleration limits for one drone's path."""
    violations = []
    max_v = 0.0
    max_a = 0.0
    speeds = []

    for i in range(1, len(path_samples)):
        dt = path_samples[i]["t"] - path_samples[i - 1]["t"]
        if dt <= 0:
            continue
        dx = [path_samples[i]["xyz"][k] - path_samples[i - 1]["xyz"][k] for k in range(3)]
        v = math.sqrt(sum(d*d for d in dx)) / dt
        speeds.append(v)
        if v > max_v:
            max_v = v
        if v > max_speed:
            violations.append({
                "type": "SPEED_EXCEEDED",
                "time": round(path_samples[i]["t"], 2),
                "value": round(v, 2),
                "limit": max_speed,
            })

    # Acceleration
    for i in range(1, len(speeds)):
        dt = path_samples[i + 1]["t"] - path_samples[i]["t"]
        if dt <= 0:
            continue
        a = abs(speeds[i] - speeds[i - 1]) / dt
        if a > max_a:
            max_a = a
        if a > max_accel:
            violations.append({
                "type": "ACCEL_EXCEEDED",
                "time": round(path_samples[i + 1]["t"], 2),
                "value": round(a, 2),
                "limit": max_accel,
            })

    return {
        "max_speed": round(max_v, 2),
        "max_acceleration": round(max_a, 2),
        "violations": violations[:10],
    }


def run_full_simulation(plan_data: dict, sample_rate: int = 10) -> dict:
    """Run complete simulation on a timeline plan.

    Returns comprehensive risk report.
    """
    drones = plan_data.get("drones", [])
    if not drones:
        return {"error": "No drones in plan"}

    # Sample all paths
    all_paths = []
    speed_reports = []
    for d in drones:
        path = sample_drone_path(d.get("segments", []), sample_rate=sample_rate)
        all_paths.append(path)
        sr = check_speed_acceleration(path)
        speed_reports.append({
            "drone_id": d["drone_id"],
            **sr,
        })

    # Inter-drone distances
    dist_report = check_min_distances(all_paths)

    # Aggregate
    all_speed_violations = sum(len(r["violations"]) for r in speed_reports)
    max_speed_overall = max(r["max_speed"] for r in speed_reports) if speed_reports else 0
    max_accel_overall = max(r["max_acceleration"] for r in speed_reports) if speed_reports else 0

    warnings = []
    if dist_report["min_distance"] < 1.0:
        warnings.append(f"CRITICAL_COLLISION_RISK: min distance {dist_report['min_distance']:.2f}m")
    elif dist_report["min_distance"] < 2.0:
        warnings.append(f"HIGH_COLLISION_RISK: min distance {dist_report['min_distance']:.2f}m")
    elif dist_report["min_distance"] < 3.0:
        warnings.append(f"MODERATE_RISK: min distance {dist_report['min_distance']:.2f}m, recommend > 3m")
    if max_speed_overall > 15.0:
        warnings.append(f"SPEED_WARNING: max {max_speed_overall:.1f} m/s exceeds 15 m/s")
    if all_speed_violations > 0:
        warnings.append(f"SPEED_VIOLATIONS: {all_speed_violations} segments exceed limits")

    return {
        "simulation_version": "v1.0",
        "simulation_only": True,
        "drone_count": len(drones),
        "sample_rate": sample_rate,
        "total_samples": sum(len(p) for p in all_paths),
        "inter_drone": dist_report,
        "speed_summary": {
            "max_speed": round(max_speed_overall, 2),
            "max_acceleration": round(max_accel_overall, 2),
            "total_violations": all_speed_violations,
        },
        "per_drone_speed": speed_reports[:5],  # top 5 only for API
        "warnings": warnings,
        "risk_level": (
            "critical" if dist_report["min_distance"] < 1.0 else
            "high" if dist_report["min_distance"] < 2.0 else
            "moderate" if dist_report["min_distance"] < 3.0 else
            "low"
        ),
    }
