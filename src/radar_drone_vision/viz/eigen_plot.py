"""Eigenspectrum and subspace visualisation for SRA / PCA analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np


def plot_eigenspectrum(
    eigenvalues_uav: np.ndarray,
    eigenvalues_non_uav: np.ndarray,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot eigenvalue spectra for UAV vs non-UAV classes.

    Parameters
    ----------
    eigenvalues_uav : np.ndarray
        Sorted eigenvalues (descending) for the UAV class.
    eigenvalues_non_uav : np.ndarray
        Sorted eigenvalues (descending) for the non-UAV class.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    eigenvalues_uav = np.asarray(eigenvalues_uav)
    eigenvalues_non_uav = np.asarray(eigenvalues_non_uav)

    fig, (ax_side, ax_overlay) = plt.subplots(1, 2, figsize=(14, 5))

    # Side-by-side
    ax_side.semilogy(eigenvalues_uav, "r-o", markersize=3, label="UAV", alpha=0.8)
    ax_side.semilogy(eigenvalues_non_uav, "b-s", markersize=3, label="Non-UAV", alpha=0.8)
    ax_side.set_xlabel("Eigenvalue index")
    ax_side.set_ylabel("Eigenvalue (log scale)")
    ax_side.set_title("Eigenspectrum Comparison")
    ax_side.legend()
    ax_side.grid(True, alpha=0.3)

    # Normalised overlay (cumulative explained variance)
    cum_uav = np.cumsum(eigenvalues_uav) / (np.sum(eigenvalues_uav) + 1e-12)
    cum_non = np.cumsum(eigenvalues_non_uav) / (np.sum(eigenvalues_non_uav) + 1e-12)
    ax_overlay.plot(cum_uav, "r-", linewidth=2, label="UAV (cumulative)")
    ax_overlay.plot(cum_non, "b-", linewidth=2, label="Non-UAV (cumulative)")
    ax_overlay.axhline(0.95, color="gray", linestyle="--", linewidth=1, label="95% variance")
    ax_overlay.set_xlabel("Number of components")
    ax_overlay.set_ylabel("Cumulative explained variance")
    ax_overlay.set_title("Cumulative Eigenspectrum")
    ax_overlay.legend()
    ax_overlay.grid(True, alpha=0.3)

    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_feature_dim_vs_error(
    dims: Sequence[int],
    error_rates: Sequence[float],
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot classification error rate vs feature dimensionality.

    Parameters
    ----------
    dims : sequence of int
        Feature dimensions tested.
    error_rates : sequence of float
        Corresponding error rates (0-1).
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    dims = list(dims)
    error_rates = list(error_rates)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(dims, error_rates, "g-o", markersize=6, linewidth=2)

    # Highlight best
    best_idx = int(np.argmin(error_rates))
    ax.scatter(
        [dims[best_idx]],
        [error_rates[best_idx]],
        color="red",
        s=120,
        zorder=5,
        label=f"Best: dim={dims[best_idx]}, err={error_rates[best_idx]:.4f}",
    )

    ax.set_xlabel("Feature dimensionality")
    ax.set_ylabel("Error rate")
    ax.set_title("Feature Dimension Sweep")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_subspace_comparison(
    sra_model: object,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Visualise two subspaces from an SRA model.

    Expects ``sra_model`` to have attributes:
    - ``U_uav`` : np.ndarray of shape (d, k) -- UAV subspace basis
    - ``U_non_uav`` : np.ndarray of shape (d, k) -- non-UAV subspace basis

    If the model does not have these attributes, the function logs a warning
    and returns an empty figure.

    Parameters
    ----------
    sra_model : object
        A fitted SRA model with subspace bases.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    U_uav = getattr(sra_model, "U_uav", None)
    U_non_uav = getattr(sra_model, "U_non_uav", None)

    if U_uav is None or U_non_uav is None:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(
            0.5,
            0.5,
            "SRA model does not expose subspace bases\n(U_uav / U_non_uav not found)",
            ha="center",
            va="center",
            fontsize=12,
            color="gray",
        )
        ax.set_axis_off()
        return fig

    U_uav = np.asarray(U_uav)
    U_non_uav = np.asarray(U_non_uav)

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5))

    # UAV subspace basis vectors (heatmap of first few)
    n_show = min(U_uav.shape[1], 8)
    ax1.imshow(U_uav[:, :n_show].T, aspect="auto", cmap="RdBu_r", interpolation="nearest")
    ax1.set_title("UAV Subspace Basis")
    ax1.set_xlabel("Feature dimension")
    ax1.set_ylabel("Basis vector index")

    # Non-UAV subspace
    n_show = min(U_non_uav.shape[1], 8)
    ax2.imshow(U_non_uav[:, :n_show].T, aspect="auto", cmap="RdBu_r", interpolation="nearest")
    ax2.set_title("Non-UAV Subspace Basis")
    ax2.set_xlabel("Feature dimension")
    ax2.set_ylabel("Basis vector index")

    # Principal angle between subspaces
    # cos(theta_i) = sigma_i(U_uav^T @ U_non_uav)
    _, sigmas, _ = np.linalg.svd(U_uav.T @ U_non_uav, full_matrices=False)
    sigmas = np.clip(sigmas, 0.0, 1.0)
    angles_deg = np.degrees(np.arccos(sigmas))
    ax3.bar(range(len(angles_deg)), angles_deg, color="teal", alpha=0.8)
    ax3.set_xlabel("Index")
    ax3.set_ylabel("Principal angle (degrees)")
    ax3.set_title("Principal Angles Between Subspaces")
    ax3.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig
