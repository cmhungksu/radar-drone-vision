"""Airspace visualisation: 2-D radar sector, track plots, and 3-D airspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np


# ------------------------------------------------------------------
# Data containers
# ------------------------------------------------------------------

@dataclass
class Target:
    """A detected target for airspace plotting."""

    x: float
    y: float
    z: float = 0.0
    classification: str = "unknown"  # "uav", "bird", "unknown"
    confidence: float = 0.5
    track_id: Optional[str] = None
    label: str = ""


@dataclass
class TrackPoint:
    """A single point in a target track."""

    timestamp: float
    x: float
    y: float
    z: float = 0.0
    classification: str = "unknown"
    confidence: float = 0.5


@dataclass
class Track:
    """A target track over time."""

    track_id: str
    points: List[TrackPoint] = field(default_factory=list)
    predicted_label: str = "unknown"


# ------------------------------------------------------------------
# Colour helpers
# ------------------------------------------------------------------

_CLASS_COLORS: Dict[str, str] = {
    "uav": "#e74c3c",
    "drone": "#e74c3c",
    "bird": "#3498db",
    "unknown": "#95a5a6",
    "human": "#2ecc71",
}


def _color_for(classification: str) -> str:
    return _CLASS_COLORS.get(classification.lower(), _CLASS_COLORS["unknown"])


# ------------------------------------------------------------------
# 2-D radar sector
# ------------------------------------------------------------------

def plot_2d_radar_sector(
    targets: Sequence[Target],
    radar_pos: Tuple[float, float] = (0.0, 0.0),
    max_range: float = 1000.0,
    azimuth_range: Tuple[float, float] = (-60.0, 60.0),
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a top-view 2-D radar sector with targets.

    Features:
    - Radar at origin
    - Range rings every ``max_range / 4`` metres
    - Azimuth fan lines at the sector edges
    - Target dots coloured by classification (UAV=red, bird=blue, unknown=gray)
    - Dot size proportional to confidence

    Parameters
    ----------
    targets : sequence of Target
        Detected targets with x, y, classification, confidence.
    radar_pos : tuple
        (x, y) position of the radar in metres.
    max_range : float
        Maximum display range in metres.
    azimuth_range : tuple
        (min_deg, max_deg) azimuth sector.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})

    # Convert azimuth range to radians (0 deg = north / up)
    az_min_rad = np.radians(azimuth_range[0])
    az_max_rad = np.radians(azimuth_range[1])

    # Set sector limits
    ax.set_thetamin(azimuth_range[0])
    ax.set_thetamax(azimuth_range[1])
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    # Range rings
    n_rings = 4
    ring_step = max_range / n_rings
    ax.set_rlim(0, max_range)
    ax.set_rticks([ring_step * i for i in range(1, n_rings + 1)])
    ax.set_rlabel_position(azimuth_range[0] + 5)

    # Plot targets
    for tgt in targets:
        dx = tgt.x - radar_pos[0]
        dy = tgt.y - radar_pos[1]
        r = np.sqrt(dx ** 2 + dy ** 2)
        theta = np.arctan2(dx, dy)  # azimuth from north

        color = _color_for(tgt.classification)
        size = 30 + 200 * tgt.confidence  # scale dot by confidence

        ax.scatter(
            theta,
            r,
            c=color,
            s=size,
            alpha=0.8,
            edgecolors="white",
            linewidths=0.5,
            zorder=5,
        )
        if tgt.label:
            ax.annotate(
                tgt.label,
                (theta, r),
                fontsize=7,
                ha="center",
                va="bottom",
                color=color,
            )

    # Legend
    from matplotlib.lines import Line2D

    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c", markersize=8, label="UAV"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3498db", markersize=8, label="Bird"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#95a5a6", markersize=8, label="Unknown"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)
    ax.set_title("Radar Sector View", va="bottom", fontsize=12)
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


# ------------------------------------------------------------------
# Track plot
# ------------------------------------------------------------------

def plot_track(
    tracks: Sequence[Track],
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot tracks with track_id, predicted label, and confidence over time.

    Upper panel: x-y trajectory.  Lower panel: confidence over time.

    Parameters
    ----------
    tracks : sequence of Track
        Tracks to plot.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    fig, (ax_xy, ax_conf) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [2, 1]})

    for trk in tracks:
        if not trk.points:
            continue
        color = _color_for(trk.predicted_label)
        xs = [p.x for p in trk.points]
        ys = [p.y for p in trk.points]
        ts = [p.timestamp for p in trk.points]
        confs = [p.confidence for p in trk.points]

        label = f"{trk.track_id} ({trk.predicted_label})"
        ax_xy.plot(xs, ys, "-o", color=color, markersize=3, label=label, alpha=0.8)
        ax_xy.annotate(trk.track_id, (xs[-1], ys[-1]), fontsize=7, color=color)

        ax_conf.plot(ts, confs, "-", color=color, label=label, alpha=0.8)

    ax_xy.set_xlabel("X (m)")
    ax_xy.set_ylabel("Y (m)")
    ax_xy.set_title("Target Tracks (X-Y)")
    ax_xy.legend(fontsize=7, loc="upper left")
    ax_xy.set_aspect("equal", adjustable="datalim")
    ax_xy.grid(True, alpha=0.3)

    ax_conf.set_xlabel("Time (s)")
    ax_conf.set_ylabel("Confidence")
    ax_conf.set_ylim(-0.05, 1.05)
    ax_conf.set_title("Classification Confidence over Time")
    ax_conf.grid(True, alpha=0.3)

    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


# ------------------------------------------------------------------
# 3-D airspace
# ------------------------------------------------------------------

def plot_3d_airspace(
    targets: Sequence[Target],
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a 3-D airspace view if range / azimuth / elevation are available.

    If all targets have ``z == 0``, a note is added indicating that the
    dataset does not provide full spatial coordinates.

    Parameters
    ----------
    targets : sequence of Target
        Detected targets with x, y, z, classification.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    all_z_zero = all(abs(t.z) < 1e-6 for t in targets)

    for tgt in targets:
        color = _color_for(tgt.classification)
        size = 30 + 200 * tgt.confidence
        ax.scatter(tgt.x, tgt.y, tgt.z, c=color, s=size, alpha=0.8, edgecolors="white", linewidths=0.5)
        if tgt.label:
            ax.text(tgt.x, tgt.y, tgt.z, f"  {tgt.label}", fontsize=7, color=color)

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title("3-D Airspace View")

    if all_z_zero:
        ax.text2D(
            0.5,
            0.02,
            "Note: dataset does not provide full spatial coordinates (z=0 for all targets)",
            transform=ax.transAxes,
            ha="center",
            fontsize=9,
            style="italic",
            color="gray",
        )

    # Legend
    from matplotlib.lines import Line2D

    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c", markersize=8, label="UAV"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3498db", markersize=8, label="Bird"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#95a5a6", markersize=8, label="Unknown"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=8)

    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig
