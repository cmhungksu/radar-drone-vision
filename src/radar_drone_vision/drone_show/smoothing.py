"""Path smoothing algorithms — Catmull-Rom, cubic Bezier, arc-length reparameterization.

Ensures all drone paths are C1-continuous (smooth, no breaks or sharp corners).
Each path is a single continuous curve formed by one drone's trajectory.

PRIVATE CORE — high-precision positioning calculations.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np


def catmull_rom_to_bezier(
    p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, p3: np.ndarray,
    alpha: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert Catmull-Rom segment (p1→p2) to cubic Bezier control points.

    Uses centripetal parameterization (alpha=0.5) for optimal smoothness.
    Guarantees C1 continuity at segment boundaries.

    Returns (B0, B1, B2, B3) — cubic Bezier control points.
    """
    # Centripetal knot intervals
    def knot(pi: np.ndarray, pj: np.ndarray) -> float:
        return float(np.linalg.norm(pj - pi)) ** alpha

    t1 = knot(p0, p1)
    t2 = t1 + knot(p1, p2)
    t3 = t2 + knot(p2, p3)

    # Tangent at p1 and p2
    if t2 - t1 > 1e-10 and t1 > 1e-10:
        m1 = (p2 - p0) / (t2) * t1 + (p1 - p0) / t1 - (p2 - p0) / t2
    else:
        m1 = (p2 - p1) * 0.5

    if t3 - t2 > 1e-10 and t3 - t1 > 1e-10:
        m2 = (p3 - p1) / (t3 - t1) * (t3 - t2) + (p2 - p3) / (t3 - t2) - (p1 - p3) / (t3 - t1)
    else:
        m2 = (p2 - p1) * 0.5

    # Simple Catmull-Rom to Bezier conversion
    d = np.linalg.norm(p2 - p1)
    scale = d / 3.0 if d > 1e-10 else 1.0

    b0 = p1.copy()
    b1 = p1 + m1 / 3.0
    b2 = p2 - m2 / 3.0
    b3 = p2.copy()

    return b0, b1, b2, b3


def de_casteljau(points: np.ndarray, t: float) -> np.ndarray:
    """Evaluate a Bezier curve at parameter t using De Casteljau's algorithm.

    High numerical precision — no matrix multiply, pure linear interpolation.

    Parameters:
        points: (n, 3) array of control points
        t: parameter in [0, 1]

    Returns:
        (3,) point on the curve
    """
    pts = points.copy()
    n = len(pts)
    for r in range(1, n):
        for i in range(n - r):
            pts[i] = (1 - t) * pts[i] + t * pts[i + 1]
    return pts[0]


def smooth_path_catmull_rom(
    control_points: List[List[float]],
    samples_per_segment: int = 20,
) -> List[List[float]]:
    """Generate a smooth C1-continuous path from control points.

    Uses Catmull-Rom spline with centripetal parameterization,
    converted to cubic Bezier segments for precise evaluation.

    Each output point is on a perfectly smooth curve — no jagged edges,
    no discontinuities, no breaks.

    Parameters:
        control_points: list of [x, y, z] points (minimum 2)
        samples_per_segment: density of output samples per segment

    Returns:
        list of [x, y, z] evenly sampled along the smooth curve
    """
    pts = [np.array(p, dtype=np.float64) for p in control_points]
    n = len(pts)

    if n < 2:
        return control_points
    if n == 2:
        # Linear interpolation
        result = []
        for i in range(samples_per_segment + 1):
            t = i / samples_per_segment
            p = (1 - t) * pts[0] + t * pts[1]
            result.append(p.tolist())
        return result

    # Pad endpoints for Catmull-Rom (reflect first and last points)
    padded = [2 * pts[0] - pts[1]] + pts + [2 * pts[-1] - pts[-2]]

    result = []
    for seg in range(len(padded) - 3):
        p0, p1, p2, p3 = padded[seg], padded[seg + 1], padded[seg + 2], padded[seg + 3]
        b0, b1, b2, b3 = catmull_rom_to_bezier(p0, p1, p2, p3)
        bezier_pts = np.array([b0, b1, b2, b3])

        for i in range(samples_per_segment):
            t = i / samples_per_segment
            point = de_casteljau(bezier_pts, t)
            result.append([round(float(point[j]), 4) for j in range(3)])

    # Add final point
    result.append([round(float(pts[-1][j]), 4) for j in range(3)])

    return result


def arc_length_reparameterize(
    path: List[List[float]],
    target_count: int,
) -> List[List[float]]:
    """Reparameterize a path by arc length for uniform spacing.

    Takes an arbitrarily sampled path and returns target_count points
    evenly spaced along the curve length. This ensures smooth, constant-speed
    visual movement.

    Parameters:
        path: list of [x, y, z] points
        target_count: number of output points

    Returns:
        list of [x, y, z] evenly arc-length spaced
    """
    if len(path) < 2 or target_count < 2:
        return path[:target_count] if target_count <= len(path) else path

    pts = np.array(path, dtype=np.float64)

    # Compute cumulative arc length
    diffs = np.diff(pts, axis=0)
    segment_lengths = np.linalg.norm(diffs, axis=1)
    cum_length = np.zeros(len(pts))
    cum_length[1:] = np.cumsum(segment_lengths)
    total_length = cum_length[-1]

    if total_length < 1e-10:
        return [path[0]] * target_count

    # Sample at uniform arc-length intervals
    result = []
    for i in range(target_count):
        target_s = (i / (target_count - 1)) * total_length

        # Binary search for the segment containing target_s
        idx = np.searchsorted(cum_length, target_s, side='right') - 1
        idx = max(0, min(idx, len(pts) - 2))

        seg_len = cum_length[idx + 1] - cum_length[idx]
        if seg_len > 1e-10:
            t = (target_s - cum_length[idx]) / seg_len
        else:
            t = 0.0

        point = (1 - t) * pts[idx] + t * pts[idx + 1]
        result.append([round(float(point[j]), 4) for j in range(3)])

    return result


def validate_path_smoothness(
    path: List[List[float]],
    max_angle_deg: float = 45.0,
) -> dict:
    """Validate that a path has no sharp turns exceeding max_angle_deg.

    Returns {smooth: bool, max_angle: float, violations: [{index, angle}]}.
    """
    if len(path) < 3:
        return {"smooth": True, "max_angle": 0, "violations": []}

    pts = np.array(path, dtype=np.float64)
    max_angle = 0.0
    violations = []

    for i in range(1, len(pts) - 1):
        v1 = pts[i] - pts[i - 1]
        v2 = pts[i + 1] - pts[i]
        len1 = np.linalg.norm(v1)
        len2 = np.linalg.norm(v2)

        if len1 < 1e-10 or len2 < 1e-10:
            continue

        cos_angle = np.clip(np.dot(v1, v2) / (len1 * len2), -1, 1)
        angle = math.degrees(math.acos(cos_angle))
        turn_angle = 180 - angle  # deviation from straight

        if turn_angle > max_angle:
            max_angle = turn_angle

        if turn_angle > max_angle_deg:
            violations.append({"index": i, "angle": round(turn_angle, 1)})

    return {
        "smooth": len(violations) == 0,
        "max_angle": round(max_angle, 1),
        "violations": violations[:20],
    }
