"""Simple formation renderer using matplotlib (Blender-free fallback).

Generates PNG previews of formations and animated GIF of the show.
SIMULATION_ONLY — all outputs are watermarked.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import numpy as np

logger = logging.getLogger(__name__)


def render_formation_preview(plan_data: dict, output_dir: Path) -> None:
    """Render formation preview images from a timeline plan."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    output_dir.mkdir(parents=True, exist_ok=True)
    drones = plan_data.get("drones", [])
    if not drones:
        logger.warning("No drones in plan, skipping render")
        return

    drone_count = len(drones)

    # ── 1. Ground layout ──
    fig, ax = plt.subplots(figsize=(8, 8), facecolor="#0b0f19")
    ax.set_facecolor("#0b0f19")
    ax.set_aspect("equal")

    for d in drones:
        gx, gy, _ = d["ground_position"]
        ax.plot(gx, gy, "o", color="#1e40af", markersize=4, alpha=0.8)

    ax.set_title(f"Ground Layout — {drone_count} Drones",
                 color="white", fontsize=12, fontweight="bold")
    ax.tick_params(colors="#64748b", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.set_xlabel("X (m)", color="#94a3b8", fontsize=9)
    ax.set_ylabel("Y (m)", color="#94a3b8", fontsize=9)

    # Watermark
    ax.text(0.5, 0.02, "SIMULATION ONLY", transform=ax.transAxes,
            ha="center", va="bottom", fontsize=8, color="#475569", alpha=0.5)

    fig.tight_layout()
    fig.savefig(output_dir / "ground_layout.png", dpi=120, facecolor="#0b0f19")
    plt.close(fig)

    # ── 2. Formation view (target positions with LED colors) ──
    fig, ax = plt.subplots(figsize=(8, 8), facecolor="#0b0f19")
    ax.set_facecolor("#0b0f19")
    ax.set_aspect("equal")

    for d in drones:
        fp = d["formation_point"]
        x, y, z = fp["xyz"]
        r, g, b = fp.get("rgb888", [0, 100, 255])
        color = (r / 255, g / 255, b / 255)
        # Glow effect
        ax.plot(x, y, "o", color=color, markersize=6, alpha=0.9)
        circle = Circle((x, y), radius=1.5, color=color, alpha=0.15)
        ax.add_patch(circle)

    ax.set_title(f"Formation — {drone_count} Drones (z={drones[0]['formation_point']['xyz'][2]:.0f}m)",
                 color="white", fontsize=12, fontweight="bold")
    ax.tick_params(colors="#64748b", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.set_xlabel("X (m)", color="#94a3b8", fontsize=9)
    ax.set_ylabel("Y (m)", color="#94a3b8", fontsize=9)

    ax.text(0.5, 0.02, "SIMULATION ONLY", transform=ax.transAxes,
            ha="center", va="bottom", fontsize=8, color="#475569", alpha=0.5)

    fig.tight_layout()
    fig.savefig(output_dir / "formation_view.png", dpi=120, facecolor="#0b0f19")
    plt.close(fig)

    # ── 3. Path preview (ground → formation with lines) ──
    fig, ax = plt.subplots(figsize=(8, 8), facecolor="#0b0f19")
    ax.set_facecolor("#0b0f19")
    ax.set_aspect("equal")

    for d in drones:
        gx, gy, _ = d["ground_position"]
        fp = d["formation_point"]
        fx, fy, _ = fp["xyz"]
        r, g, b = fp.get("rgb888", [0, 100, 255])
        color = (r / 255, g / 255, b / 255)

        ax.plot([gx, fx], [gy, fy], "-", color=color, alpha=0.3, linewidth=0.5)
        ax.plot(gx, gy, "s", color="#1e40af", markersize=2, alpha=0.6)
        ax.plot(fx, fy, "o", color=color, markersize=4, alpha=0.8)

    ax.set_title(f"Flight Paths — Ground to Formation",
                 color="white", fontsize=12, fontweight="bold")
    ax.tick_params(colors="#64748b", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.set_xlabel("X (m)", color="#94a3b8", fontsize=9)
    ax.set_ylabel("Y (m)", color="#94a3b8", fontsize=9)

    ax.text(0.5, 0.02, "SIMULATION ONLY", transform=ax.transAxes,
            ha="center", va="bottom", fontsize=8, color="#475569", alpha=0.5)

    fig.tight_layout()
    fig.savefig(output_dir / "path_preview.png", dpi=120, facecolor="#0b0f19")
    plt.close(fig)

    logger.info("Rendered 3 preview images to %s", output_dir)
