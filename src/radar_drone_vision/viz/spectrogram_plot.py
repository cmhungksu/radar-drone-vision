"""Spectrogram and feature visualisation plots."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np


def plot_spectrogram(
    spec: np.ndarray,
    title: str = "Spectrogram",
    save_path: Optional[str] = None,
    cmap: str = "viridis",
) -> plt.Figure:
    """Plot a 2-D spectrogram (time x frequency).

    Parameters
    ----------
    spec : np.ndarray
        2-D array of shape ``(n_frames, n_freq)``.
    title : str
        Plot title.
    save_path : str, optional
        If given, save figure to this path.
    cmap : str
        Matplotlib colourmap name.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    spec = np.asarray(spec)
    if spec.ndim != 2:
        raise ValueError(f"Expected 2-D array, got shape {spec.shape}")

    fig, ax = plt.subplots(figsize=(10, 4))
    im = ax.imshow(
        spec.T,
        aspect="auto",
        origin="lower",
        cmap=cmap,
        interpolation="nearest",
    )
    ax.set_xlabel("Frame")
    ax.set_ylabel("Frequency bin")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label="Magnitude")
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_proposed_feature(
    feature_2d: np.ndarray,
    mode: str = "real",
    title: Optional[str] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot the proposed complex-log feature.

    Parameters
    ----------
    feature_2d : np.ndarray
        2-D complex or real array.
    mode : str
        ``'real'``, ``'imag'``, or ``'magnitude'``.
    title : str, optional
        Plot title.  Defaults to ``"Proposed feature ({mode})"``.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    feature_2d = np.asarray(feature_2d)
    if title is None:
        title = f"Proposed feature ({mode})"

    mode_lower = mode.lower()
    if mode_lower == "real":
        data = feature_2d.real
    elif mode_lower == "imag":
        data = feature_2d.imag
    elif mode_lower in ("magnitude", "mag", "abs"):
        data = np.abs(feature_2d)
    else:
        raise ValueError(f"Unknown mode '{mode}'. Use 'real', 'imag', or 'magnitude'.")

    fig, ax = plt.subplots(figsize=(10, 4))
    im = ax.imshow(data.T, aspect="auto", origin="lower", cmap="inferno", interpolation="nearest")
    ax.set_xlabel("Frame")
    ax.set_ylabel("Feature bin")
    ax.set_title(title)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_sample_overview(
    sample_id: str,
    spectrogram: np.ndarray,
    proposed_real: np.ndarray,
    proposed_imag: np.ndarray,
    regularized_log: np.ndarray,
    save_dir: Optional[str] = None,
) -> plt.Figure:
    """Generate a 4-panel overview for a single sample.

    Panels: spectrogram, proposed-real, proposed-imag, regularised-log.

    Parameters
    ----------
    sample_id : str
        Identifier used in the figure title and filename.
    spectrogram, proposed_real, proposed_imag, regularized_log : np.ndarray
        2-D feature arrays.
    save_dir : str, optional
        Directory to save the figure.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    panels = [
        (spectrogram, "Spectrogram", "viridis"),
        (proposed_real, "Proposed (real)", "inferno"),
        (proposed_imag, "Proposed (imag)", "inferno"),
        (regularized_log, "Regularised log-FFT", "magma"),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(20, 4))
    fig.suptitle(f"Sample: {sample_id}", fontsize=14, fontweight="bold")

    for ax, (data, label, cmap) in zip(axes, panels):
        data = np.asarray(data)
        if data.ndim == 1:
            ax.plot(data)
        else:
            im = ax.imshow(data.T, aspect="auto", origin="lower", cmap=cmap, interpolation="nearest")
            fig.colorbar(im, ax=ax, shrink=0.8)
        ax.set_title(label, fontsize=10)
        ax.set_xlabel("Frame")
        ax.set_ylabel("Bin")

    fig.tight_layout()

    if save_dir is not None:
        out = Path(save_dir)
        out.mkdir(parents=True, exist_ok=True)
        fig.savefig(out / f"{sample_id}_overview.png", dpi=150, bbox_inches="tight")

    return fig
