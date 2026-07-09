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


def _detect_background_color(bgr: np.ndarray) -> Tuple[np.ndarray, float]:
    """Detect the dominant background color by sampling corners and edges."""
    h, w = bgr.shape[:2]
    # Sample corners (10% from each edge)
    margin = max(2, min(h, w) // 10)
    samples = np.vstack([
        bgr[:margin, :margin].reshape(-1, 3),        # top-left
        bgr[:margin, -margin:].reshape(-1, 3),        # top-right
        bgr[-margin:, :margin].reshape(-1, 3),        # bottom-left
        bgr[-margin:, -margin:].reshape(-1, 3),        # bottom-right
        bgr[:margin, :].reshape(-1, 3),                # top edge
        bgr[-margin:, :].reshape(-1, 3),               # bottom edge
    ])
    # Median of corner samples = background color
    bg_color = np.median(samples, axis=0).astype(np.uint8)

    # Calculate how much of the image matches this color (within tolerance)
    diff = np.abs(bgr.astype(np.int16) - bg_color.astype(np.int16)).sum(axis=2)
    bg_ratio = float((diff < 60).sum()) / (h * w)

    return bg_color, bg_ratio


def load_and_preprocess(image_path: str | Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load image, remove background, return (color_image_bgr, gray)."""
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"Cannot load image: {image_path}")

    # Handle alpha channel (remove background)
    if len(img.shape) > 2 and img.shape[2] == 4:
        alpha = img[:, :, 3]
        bgr = img[:, :, :3].copy()
        mask = alpha < 128
        bgr[mask] = [0, 0, 0]
    else:
        bgr = img.copy()

    # Auto-detect and remove solid background color
    bg_color, bg_ratio = _detect_background_color(bgr)
    if bg_ratio > 0.15:  # background covers >15% of image
        # Mask out pixels similar to background color
        diff = np.abs(bgr.astype(np.int16) - bg_color.astype(np.int16)).sum(axis=2)
        bg_mask = diff < 60  # tolerance
        bgr[bg_mask] = [0, 0, 0]  # set background to black
        logger.info("Auto-removed background color BGR(%d,%d,%d), %.0f%% of image",
                     bg_color[0], bg_color[1], bg_color[2], bg_ratio * 100)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return bgr, gray


def extract_contour_points(gray: np.ndarray, bgr: Optional[np.ndarray] = None) -> np.ndarray:
    """Extract contour points, filtering out dark/background regions."""
    h, w = gray.shape

    # Threshold: only keep bright-enough areas
    _, binary = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)

    # If color image provided, also filter by color brightness
    if bgr is not None:
        brightness = bgr.astype(np.float32).sum(axis=2)
        bright_mask = (brightness > 60).astype(np.uint8) * 255
        binary = cv2.bitwise_and(binary, bright_mask)

    # Clean up: remove small noise blobs
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    # Edge detection on cleaned binary
    edges = cv2.Canny(binary, 50, 150)

    # Find contours — EXTERNAL only (skip internal dark-region borders)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    if not contours:
        # Fallback: use bright pixels directly
        pts = np.column_stack(np.where(binary > 0))
        if len(pts) == 0:
            pts = np.column_stack(np.where(gray > 30))
        return pts[:, ::-1] if len(pts) > 0 else np.array([[0, 0]])

    # Collect contour points, but skip any that land on dark pixels
    all_pts = []
    for contour in contours:
        if len(contour) < 3:
            continue
        pts = contour.reshape(-1, 2)
        # Filter: only keep points where the image is actually bright
        if bgr is not None:
            bright_pts = []
            for px, py in pts:
                px_c = int(np.clip(px, 0, w - 1))
                py_c = int(np.clip(py, 0, h - 1))
                b, g, r = bgr[py_c, px_c]
                if int(b) + int(g) + int(r) > 60:
                    bright_pts.append([px, py])
            if bright_pts:
                all_pts.append(np.array(bright_pts))
        else:
            all_pts.append(pts)

    if not all_pts:
        pts = np.column_stack(np.where(binary > 0))
        return pts[:, ::-1] if len(pts) > 0 else np.array([[0, 0]])

    return np.vstack(all_pts)


def extract_skeleton(gray: np.ndarray, threshold: int = 30) -> np.ndarray:
    """Extract skeleton (medial axis) of bright regions.

    Returns skeleton point coordinates as (N, 2) array [x, y].
    Skeleton captures the structural 'bones' of the image for thin features.
    """
    from skimage.morphology import skeletonize
    binary = (gray > threshold).astype(np.uint8)
    skeleton = skeletonize(binary).astype(np.uint8)
    pts = np.column_stack(np.where(skeleton > 0))[:, ::-1]  # yx → xy
    return pts if len(pts) > 0 else np.array([[0, 0]])


def score_saliency(gray: np.ndarray) -> np.ndarray:
    """Compute a saliency map highlighting visually important regions.

    Uses spectral residual approach: regions that differ from the
    average frequency content are more salient (eyes, text, edges).
    Returns float32 saliency map same size as input, values in [0, 1].
    """
    h, w = gray.shape
    # Spectral residual saliency
    scale = max(1, min(h, w) // 64)
    small = cv2.resize(gray, (w // scale, h // scale))
    dft = np.fft.fft2(small.astype(np.float32))
    magnitude = np.log(np.abs(dft) + 1e-8)
    phase = np.angle(dft)
    # Spectral residual = magnitude - averaged magnitude
    avg_mag = cv2.blur(magnitude, (3, 3))
    residual = magnitude - avg_mag
    # Reconstruct with residual magnitude and original phase
    saliency_small = np.abs(np.fft.ifft2(np.exp(residual + 1j * phase))) ** 2
    # Gaussian blur for smoothness
    saliency_small = cv2.GaussianBlur(saliency_small.astype(np.float32), (5, 5), 0)
    # Resize back
    saliency = cv2.resize(saliency_small, (w, h))
    # Normalize to [0, 1]
    smin, smax = saliency.min(), saliency.max()
    if smax > smin:
        saliency = (saliency - smin) / (smax - smin)
    return saliency.astype(np.float32)


def compute_importance(points: np.ndarray, gray: np.ndarray) -> np.ndarray:
    """Compute per-point importance based on curvature, gradient, and saliency."""
    n = len(points)
    importance = np.ones(n, dtype=np.float64) * 0.5
    h, w = gray.shape

    # Pre-compute saliency map
    saliency = score_saliency(gray)

    for i in range(n):
        x, y = int(points[i, 0]), int(points[i, 1])
        x = np.clip(x, 1, w - 2)
        y = np.clip(y, 1, h - 2)

        # Gradient magnitude
        gx = float(gray[y, x + 1]) - float(gray[y, x - 1])
        gy = float(gray[y + 1, x]) - float(gray[y - 1, x])
        grad = np.sqrt(gx**2 + gy**2) / 360.0

        # Curvature
        if i > 0 and i < n - 1:
            v1 = points[i] - points[i - 1]
            v2 = points[i + 1] - points[i]
            len1 = np.linalg.norm(v1) + 1e-8
            len2 = np.linalg.norm(v2) + 1e-8
            cos_angle = np.dot(v1, v2) / (len1 * len2)
            curvature = (1.0 - np.clip(cos_angle, -1, 1)) / 2.0
        else:
            curvature = 0.3

        # Saliency at this point
        sal = float(saliency[y, x])

        # Weighted combination: saliency 30% + curvature 40% + gradient 20% + base 10%
        importance[i] = np.clip(0.3 * sal + 0.4 * curvature + 0.2 * grad + 0.1, 0.0, 1.0)

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
    h, w = bgr_image.shape[:2]
    max_dim = max(h, w)
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

        # Skip near-black background pixels (invisible in dark sky)
        brightness = int(r) + int(g) + int(b)
        if brightness < 40:
            # Replace with a visible color from the palette (skip dark ones)
            bright_colors = [c for c in palette if sum(c) > 80]
            if bright_colors:
                color = bright_colors[i % len(bright_colors)]
            else:
                color = [0, 100, 255]  # fallback blue

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
    contour_pts = extract_contour_points(gray, bgr=bgr)
    # Also extract skeleton for thin structural features
    skeleton_pts = extract_skeleton(gray, threshold=30)
    # Merge contour + skeleton (skeleton fills thin areas contours miss)
    if len(skeleton_pts) > 1 and skeleton_pts[0][0] != 0:
        contour_pts = np.vstack([contour_pts, skeleton_pts])
        # Remove duplicates (within 2px)
        if len(contour_pts) > drone_count * 3:
            from scipy.spatial import KDTree
            tree = KDTree(contour_pts)
            keep = np.ones(len(contour_pts), dtype=bool)
            for i in range(len(contour_pts)):
                if not keep[i]:
                    continue
                neighbors = tree.query_ball_point(contour_pts[i], r=2.0)
                for j in neighbors:
                    if j > i:
                        keep[j] = False
            contour_pts = contour_pts[keep]
    logger.info("Extracted %d points (contour+skeleton) from %dx%d image", len(contour_pts), w, h)

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
