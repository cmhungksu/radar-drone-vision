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


def compute_color_loss_report(
    original_colors: list[list[int]],
    quantized_colors: list[list[int]],
    palette: list[list[int]],
) -> dict:
    """Compute color degradation report after palette quantization.

    Returns:
        color_loss_score: 0.0 (perfect) to 1.0 (total loss)
        avg_delta_e: average perceptual color difference
        max_delta_e: worst case color difference
        palette_coverage: how many palette colors are actually used
        warnings: list of color-related warnings
    """
    import numpy as np

    if not original_colors or not quantized_colors:
        return {"color_loss_score": 0.0, "avg_delta_e": 0.0, "max_delta_e": 0.0,
                "palette_coverage": 0, "warnings": []}

    n = min(len(original_colors), len(quantized_colors))
    deltas = []
    for i in range(n):
        o = original_colors[i]
        q = quantized_colors[i]
        # Simplified Delta E (Euclidean in RGB, not perceptually accurate but fast)
        de = ((o[0]-q[0])**2 + (o[1]-q[1])**2 + (o[2]-q[2])**2) ** 0.5
        deltas.append(de)

    avg_de = float(np.mean(deltas)) if deltas else 0.0
    max_de = float(np.max(deltas)) if deltas else 0.0
    # Normalize: max possible delta_e in RGB = sqrt(3*255^2) ≈ 441
    color_loss_score = min(1.0, avg_de / 100.0)  # 100 = significant loss threshold

    # Palette coverage
    used_colors = set()
    for q in quantized_colors:
        for i, p in enumerate(palette):
            if q == p:
                used_colors.add(i)
                break
    coverage = len(used_colors)

    warnings = []
    if color_loss_score > 0.3:
        warnings.append(f"COLOR_PALETTE_LOSS: avg color difference {avg_de:.1f}, "
                        f"loss score {color_loss_score:.2f}")
    if max_de > 150:
        warnings.append(f"COLOR_MAX_DEVIATION: worst case {max_de:.1f} "
                        f"(some colors severely distorted)")
    if coverage < len(palette) * 0.5:
        warnings.append(f"PALETTE_UNDERUSED: only {coverage}/{len(palette)} "
                        f"palette colors used")

    return {
        "color_loss_score": round(color_loss_score, 3),
        "avg_delta_e": round(avg_de, 1),
        "max_delta_e": round(max_de, 1),
        "palette_coverage": coverage,
        "palette_size": len(palette),
        "warnings": warnings,
    }
