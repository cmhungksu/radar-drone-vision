"""LED color system — RGB565/RGB888 conversion, gamma, takeoff-blue rules."""

from __future__ import annotations

import numpy as np


def rgb888_to_rgb565(r: int, g: int, b: int) -> int:
    """Convert 24-bit RGB to 16-bit RGB565."""
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def rgb565_to_rgb888(val: int) -> tuple[int, int, int]:
    """Convert 16-bit RGB565 to 24-bit RGB."""
    r5 = (val >> 11) & 0x1F
    g6 = (val >> 5) & 0x3F
    b5 = val & 0x1F
    return (r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2)


def apply_gamma(rgb: tuple[int, int, int], gamma: float = 2.2) -> tuple[int, int, int]:
    """Apply gamma correction."""
    return tuple(int(255 * (c / 255.0) ** (1.0 / gamma)) for c in rgb)  # type: ignore


# Takeoff blue (low brightness)
TAKEOFF_BLUE_888 = (0, 60, 200)
TAKEOFF_BLUE_565 = rgb888_to_rgb565(*TAKEOFF_BLUE_888)

# Hold blue (mid brightness)
HOLD_BLUE_888 = (0, 100, 255)
HOLD_BLUE_565 = rgb888_to_rgb565(*HOLD_BLUE_888)


def cluster_colors(image: np.ndarray, n_colors: int = 8) -> list[list[int]]:
    """Extract dominant color palette from an image using k-means."""
    pixels = image.reshape(-1, 3).astype(np.float32)
    # Remove near-black and near-white
    mask = (pixels.sum(axis=1) > 30) & (pixels.sum(axis=1) < 720)
    pixels = pixels[mask]
    if len(pixels) < n_colors:
        return [[0, 0, 255]]  # fallback blue

    import cv2
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(pixels, n_colors, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    palette = centers.astype(int).tolist()
    # Sort by frequency
    counts = np.bincount(labels.flatten(), minlength=n_colors)
    order = np.argsort(-counts)
    return [palette[i] for i in order]


def nearest_palette_color(r: int, g: int, b: int,
                          palette: list[list[int]]) -> list[int]:
    """Find nearest color in palette by Euclidean distance."""
    best = palette[0]
    best_dist = float('inf')
    for c in palette:
        d = (r - c[0])**2 + (g - c[1])**2 + (b - c[2])**2
        if d < best_dist:
            best_dist = d
            best = c
    return best
