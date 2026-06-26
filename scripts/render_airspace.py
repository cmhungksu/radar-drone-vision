#!/usr/bin/env python3
"""Generate airspace visualisation from synthetic or spatial radar data.

Usage:
    python scripts/render_airspace.py \
        --dataset synthetic_airspace \
        --out reports/airspace_demo
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("render_airspace")


# ------------------------------------------------------------------ #
# Data generation / loading
# ------------------------------------------------------------------ #

def generate_synthetic_targets(
    n_uav: int = 15,
    n_bird: int = 20,
    seed: int = 42,
) -> list:
    """Generate synthetic target metadata for airspace visualisation."""
    from radar_drone_vision.datasets.synthetic import SyntheticGenerator

    gen = SyntheticGenerator(seed=seed)
    uav_samples = gen.generate_uav_samples(n=n_uav)
    bird_samples = gen.generate_bird_samples(n=n_bird)
    return uav_samples + bird_samples


def load_spatial_dataset(dataset_name: str) -> list:
    """Try to load a dataset with spatial info; fall back to synthetic."""
    if dataset_name in ("synthetic_airspace", "synthetic"):
        return generate_synthetic_targets()

    if dataset_name in ("zenodo77", "zenodo_77ghz_fmcw"):
        # Zenodo dataset has no spatial info — generate synthetic spatial metadata
        logger.info(
            "Dataset '%s' lacks spatial metadata. Generating synthetic targets instead.",
            dataset_name,
        )
        return generate_synthetic_targets()

    logger.warning("Unknown dataset '%s'. Falling back to synthetic.", dataset_name)
    return generate_synthetic_targets()


# ------------------------------------------------------------------ #
# Plotting
# ------------------------------------------------------------------ #

def plot_radar_sector(
    samples: list,
    title: str = "Radar Sector View",
    save_path: Optional[str] = None,
):
    """Plot 2-D polar radar sector with targets.

    X-axis: range (m), Y-axis: azimuth (deg).
    Colour-coded by class: red = UAV, blue = bird/non-UAV.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge

    fig, ax = plt.subplots(figsize=(10, 8), subplot_kw={"projection": "polar"})

    uav_ranges = []
    uav_azimuths = []
    bird_ranges = []
    bird_azimuths = []

    for s in samples:
        rng = s.range_m if s.range_m is not None else 500.0
        az = s.azimuth_deg if s.azimuth_deg is not None else 0.0
        az_rad = np.radians(az)

        if s.label_binary == 1:
            uav_ranges.append(rng)
            uav_azimuths.append(az_rad)
        else:
            bird_ranges.append(rng)
            bird_azimuths.append(az_rad)

    ax.scatter(bird_azimuths, bird_ranges, c="dodgerblue", marker="o", s=40,
               alpha=0.7, label="Bird / non-UAV", zorder=3)
    ax.scatter(uav_azimuths, uav_ranges, c="red", marker="^", s=60,
               alpha=0.8, label="UAV", zorder=4)

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetamin(-60)
    ax.set_thetamax(60)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylabel("Range (m)", labelpad=30)
    fig.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info("Sector plot saved: %s", save_path)

    plt.close(fig)
    return fig


def plot_range_azimuth_cartesian(
    samples: list,
    title: str = "Range–Azimuth Map",
    save_path: Optional[str] = None,
):
    """Cartesian range vs azimuth scatter."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))

    for s in samples:
        rng = s.range_m if s.range_m is not None else 500.0
        az = s.azimuth_deg if s.azimuth_deg is not None else 0.0
        color = "red" if s.label_binary == 1 else "dodgerblue"
        marker = "^" if s.label_binary == 1 else "o"
        ax.scatter(az, rng, c=color, marker=marker, s=40, alpha=0.7)

    # Legend proxies
    ax.scatter([], [], c="red", marker="^", s=60, label="UAV")
    ax.scatter([], [], c="dodgerblue", marker="o", s=40, label="Bird / non-UAV")
    ax.set_xlabel("Azimuth (deg)")
    ax.set_ylabel("Range (m)")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info("Range-azimuth plot saved: %s", save_path)

    plt.close(fig)
    return fig


def plot_tracks(
    samples: list,
    title: str = "Target Tracks",
    save_path: Optional[str] = None,
):
    """Plot target tracks grouped by track_id (range vs time / index)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from collections import defaultdict

    tracks: dict = defaultdict(list)
    for s in samples:
        tid = s.track_id or s.sample_id
        tracks[tid].append(s)

    fig, ax = plt.subplots(figsize=(12, 6))
    cmap_uav = plt.cm.Reds  # type: ignore[attr-defined]
    cmap_bird = plt.cm.Blues  # type: ignore[attr-defined]

    uav_tracks = {k: v for k, v in tracks.items() if v[0].label_binary == 1}
    bird_tracks = {k: v for k, v in tracks.items() if v[0].label_binary == 0}

    for i, (tid, slist) in enumerate(uav_tracks.items()):
        slist.sort(key=lambda s: s.timestamp or 0)
        times = [s.timestamp or j for j, s in enumerate(slist)]
        ranges = [s.range_m or 0 for s in slist]
        color = cmap_uav(0.3 + 0.5 * i / max(len(uav_tracks), 1))
        ax.plot(times, ranges, "^-", color=color, markersize=4, alpha=0.7, linewidth=1)

    for i, (tid, slist) in enumerate(bird_tracks.items()):
        slist.sort(key=lambda s: s.timestamp or 0)
        times = [s.timestamp or j for j, s in enumerate(slist)]
        ranges = [s.range_m or 0 for s in slist]
        color = cmap_bird(0.3 + 0.5 * i / max(len(bird_tracks), 1))
        ax.plot(times, ranges, "o-", color=color, markersize=3, alpha=0.7, linewidth=1)

    ax.scatter([], [], c="red", marker="^", s=40, label=f"UAV tracks ({len(uav_tracks)})")
    ax.scatter([], [], c="dodgerblue", marker="o", s=30, label=f"Bird tracks ({len(bird_tracks)})")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Range (m)")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info("Track plot saved: %s", save_path)

    plt.close(fig)
    return fig


def plot_elevation_profile(
    samples: list,
    title: str = "Elevation Profile",
    save_path: Optional[str] = None,
):
    """Scatter of range vs elevation, coloured by class."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5))

    for s in samples:
        rng = s.range_m if s.range_m is not None else 500.0
        el = s.elevation_deg if s.elevation_deg is not None else 0.0
        c = "red" if s.label_binary == 1 else "dodgerblue"
        m = "^" if s.label_binary == 1 else "o"
        ax.scatter(rng, el, c=c, marker=m, s=40, alpha=0.7)

    ax.scatter([], [], c="red", marker="^", s=60, label="UAV")
    ax.scatter([], [], c="dodgerblue", marker="o", s=40, label="Bird / non-UAV")
    ax.set_xlabel("Range (m)")
    ax.set_ylabel("Elevation (deg)")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info("Elevation profile saved: %s", save_path)

    plt.close(fig)
    return fig


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def run_render(args: argparse.Namespace) -> None:
    np.random.seed(args.seed)

    samples = load_spatial_dataset(args.dataset)
    logger.info("Loaded %d samples for visualisation.", len(samples))

    out_dir = Path(args.out) if args.out else _PROJECT_ROOT / "reports" / "airspace_demo"
    out_dir.mkdir(parents=True, exist_ok=True)

    n_uav = sum(1 for s in samples if s.label_binary == 1)
    n_bird = len(samples) - n_uav
    print(f"\n  Targets: {n_uav} UAV, {n_bird} non-UAV ({len(samples)} total)")

    # Generate plots
    plot_radar_sector(
        samples,
        title="Radar Sector — UAV vs Bird",
        save_path=str(out_dir / "radar_sector.png"),
    )
    plot_range_azimuth_cartesian(
        samples,
        title="Range-Azimuth Map",
        save_path=str(out_dir / "range_azimuth.png"),
    )
    plot_tracks(
        samples,
        title="Target Tracks Over Time",
        save_path=str(out_dir / "tracks.png"),
    )
    plot_elevation_profile(
        samples,
        title="Range-Elevation Profile",
        save_path=str(out_dir / "elevation_profile.png"),
    )

    print(f"\n  All plots saved to: {out_dir}")
    print("  Files:")
    for f in sorted(out_dir.glob("*.png")):
        print(f"    - {f.name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate airspace visualisation from radar data."
    )
    parser.add_argument(
        "--dataset", type=str, default="synthetic_airspace",
        help="Dataset name (default: synthetic_airspace)",
    )
    parser.add_argument("--out", type=str, default=None, help="Output directory")
    parser.add_argument("--n-uav", type=int, default=15, help="Number of synthetic UAV targets")
    parser.add_argument("--n-bird", type=int, default=20, help="Number of synthetic bird targets")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser.parse_args()


if __name__ == "__main__":
    run_render(parse_args())
