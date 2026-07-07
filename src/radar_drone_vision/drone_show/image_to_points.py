"""Image-to-formation-points engine.

Converts images (PNG/JPG/SVG) into drone formation point clouds,
with importance-weighted sampling, color extraction, and detail scoring.

PRIVATE CORE: This module must NOT be exposed to the frontend.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .led import cluster_colors, nearest_palette_color, rgb888_to_rgb565
from .schemas import FormationFrame, FormationPoint

logger = logging.getLogger(__name__)


def load_and_preprocess(image_path: str | Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load image, remove background, return (color_image_bgr, gray)."""
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"Cannot load image: {image_path}")

    # Handle alpha channel (remove background)
    if img.shape[2] == 4:
        alpha = img[:, :, 3]
        bgr = img[:, :, :3]
        # Set transparent pixels to black
        mask = alpha < 128
        bgr[mask] = [0, 0, 0]
    else:
        bgr = img

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return bgr, gray


def extract_contour_points(gray: np.ndarray) -> np.ndarray:
    """Extract contour points with importance based on curvature."""
    # Adaptive threshold for varied images
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Edge detection
    edges = cv2.Canny(gray, 50, 150)

    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

    if not contours:
        # Fallback: use binary image non-zero points
        pts = np.column_stack(np.where(binary > 0))
        if len(pts) == 0:
            pts = np.column_stack(np.where(gray > 30))
        return pts[:, ::-1] if len(pts) > 0 else np.array([[0, 0]])  # yx → xy

    # Collect all contour points
    all_pts = []
    for contour in contours:
        if len(contour) < 3:
            continue
        pts = contour.reshape(-1, 2)
        all_pts.append(pts)

    if not all_pts:
        return np.array([[0, 0]])

    return np.vstack(all_pts)


def compute_importance(points: np.ndarray, gray: np.ndarray) -> np.ndarray:
    """Compute per-point importance based on local curvature and gradient."""
    n = len(points)
    importance = np.ones(n, dtype=np.float64) * 0.5

    h, w = gray.shape

    for i in range(n):
        x, y = int(points[i, 0]), int(points[i, 1])
        x = np.clip(x, 1, w - 2)
        y = np.clip(y, 1, h - 2)

        # Gradient magnitude as importance
        gx = float(gray[y, x + 1]) - float(gray[y, x - 1])
        gy = float(gray[y + 1, x]) - float(gray[y - 1, x])
        grad = np.sqrt(gx**2 + gy**2) / 360.0  # normalize to ~[0, 1]

        # Curvature: compare with neighbors in the point list
        if i > 0 and i < n - 1:
            v1 = points[i] - points[i - 1]
            v2 = points[i + 1] - points[i]
            len1 = np.linalg.norm(v1) + 1e-8
            len2 = np.linalg.norm(v2) + 1e-8
            cos_angle = np.dot(v1, v2) / (len1 * len2)
            curvature = 1.0 - np.clip(cos_angle, -1, 1)  # 0=straight, 2=U-turn
            curvature = curvature / 2.0  # normalize to [0, 1]
        else:
            curvature = 0.3

        importance[i] = np.clip(0.3 * grad + 0.7 * curvature + 0.1, 0.0, 1.0)

    return importance


def sample_points_by_count(
    contour_points: np.ndarray,
    importance: np.ndarray,
    drone_count: int,
    bgr_image: np.ndarray,
    palette: list[list[int]],
    z_height: float = 50.0,
    scale: float = 1.0,
) -> List[FormationPoint]:
    """Sample exactly drone_count points, weighted by importance."""
    n_available = len(contour_points)

    if n_available <= drone_count:
        # Use all points
        selected_idx = np.arange(n_available)
        # Pad with random interior points if needed
        if n_available < drone_count:
            h, w = bgr_image.shape[:2]
            gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
            interior = np.column_stack(np.where(gray > 30))[:, ::-1]
            if len(interior) > 0:
                extra_idx = np.random.choice(len(interior), size=drone_count - n_available, replace=True)
                extra_pts = interior[extra_idx]
                contour_points = np.vstack([contour_points, extra_pts])
                importance = np.concatenate([importance, np.full(len(extra_pts), 0.3)])
                selected_idx = np.arange(len(contour_points))
    else:
        # Importance-weighted sampling without replacement
        probs = importance / importance.sum()
        selected_idx = np.random.choice(n_available, size=drone_count, replace=False, p=probs)

    # Enforce minimum spacing between selected points (at least 2 pixels)
    selected_pts = contour_points[selected_idx[:drone_count]].copy()
    min_pixel_dist = max(2.0, max_dim / (drone_count * 0.8))
    for i in range(1, len(selected_pts)):
        for j in range(i):
            d = np.linalg.norm(selected_pts[i] - selected_pts[j])
            if d < min_pixel_dist:
                # Jitter the point outward
                direction = selected_pts[i] - selected_pts[j]
                if np.linalg.norm(direction) < 0.01:
                    direction = np.array([np.random.randn(), np.random.randn()])
                direction = direction / (np.linalg.norm(direction) + 1e-8)
                selected_pts[i] = selected_pts[j] + direction * min_pixel_dist
                selected_pts[i] = np.clip(selected_pts[i], 0, [w - 1, h - 1])
    # Write back jittered positions
    for i in range(min(len(selected_idx), drone_count)):
        contour_points[selected_idx[i]] = selected_pts[i]

    h, w = bgr_image.shape[:2]
    max_dim = max(h, w)
    half_span = 50.0 * scale  # ±50m default

    points = []
    for i, idx in enumerate(selected_idx[:drone_count]):
        px, py = contour_points[idx]
        # Normalize to world coords: center at (0, 0, z_height)
        wx = (px / max_dim - 0.5) * 2 * half_span
        wy = -(py / max_dim - 0.5) * 2 * half_span  # flip Y
        wz = z_height

        # Get color from image
        cx = int(np.clip(px, 0, w - 1))
        cy = int(np.clip(py, 0, h - 1))
        b, g, r = bgr_image[cy, cx]
        color = nearest_palette_color(int(r), int(g), int(b), palette)

        imp = float(importance[idx]) if idx < len(importance) else 0.5
        points.append(FormationPoint(
            point_id=f"P{i:04d}",
            xyz=[round(wx, 2), round(wy, 2), round(wz, 2)],
            rgb565=rgb888_to_rgb565(color[0], color[1], color[2]),
            rgb888=color,
            importance=round(imp, 3),
            source_feature="contour",
            group_id="main",
        ))

    return points


def generate_formation_from_image(
    image_path: str | Path,
    drone_count: int = 50,
    z_height: float = 50.0,
    scale: float = 1.0,
    n_palette_colors: int = 8,
) -> Tuple[FormationFrame, list[list[int]]]:
    """Full pipeline: image → formation frame.

    Returns (FormationFrame, palette).
    """
    bgr, gray = load_and_preprocess(image_path)
    h, w = gray.shape

    # Extract palette
    rgb_img = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    palette = cluster_colors(rgb_img, n_colors=min(n_palette_colors, 8))

    # Extract contour points
    contour_pts = extract_contour_points(gray)
    logger.info("Extracted %d contour points from %dx%d image", len(contour_pts), w, h)

    # Compute importance
    imp = compute_importance(contour_pts, gray)

    # Sample points
    formation_points = sample_points_by_count(
        contour_pts, imp, drone_count, bgr, palette, z_height, scale
    )

    # Detail score: ratio of available detail vs requested
    detail_score = min(1.0, len(contour_pts) / max(drone_count * 2, 1))

    # Warnings
    warnings = []
    if len(contour_pts) < drone_count:
        warnings.append(f"POINT_DENSITY_TOO_LOW: only {len(contour_pts)} contour points for {drone_count} drones")
    if drone_count < 20:
        warnings.append("LOW_DRONE_COUNT: fewer than 20 drones, only simple shapes recommended")
    if detail_score < 0.3:
        warnings.append("DETAIL_LOSS_HIGH: consider using fewer drones or simpler image")

    frame_id = f"frame_{uuid.uuid4().hex[:8]}"
    frame = FormationFrame(
        frame_id=frame_id,
        points=formation_points,
        drone_count=drone_count,
        detail_score=round(detail_score, 3),
        warnings=warnings,
        image_width=w,
        image_height=h,
    )

    logger.info("Generated formation: %d points, detail=%.3f, warnings=%d",
                len(formation_points), detail_score, len(warnings))
    return frame, palette
