"""ROC, DET, and threshold sweep plots for classification evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np


def plot_roc_curve(
    fpr: np.ndarray,
    tpr: np.ndarray,
    auc_val: Optional[float] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a Receiver Operating Characteristic (ROC) curve.

    Parameters
    ----------
    fpr : np.ndarray
        False positive rates.
    tpr : np.ndarray
        True positive rates.
    auc_val : float, optional
        Area Under Curve value to display in legend.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    fpr = np.asarray(fpr)
    tpr = np.asarray(tpr)

    fig, ax = plt.subplots(figsize=(7, 7))
    label = "ROC"
    if auc_val is not None:
        label = f"ROC (AUC = {auc_val:.4f})"
    ax.plot(fpr, tpr, "b-", linewidth=2, label=label)
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, alpha=0.5, label="Random")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curve")
    ax.legend(loc="lower right")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_det_curve(
    far: np.ndarray,
    frr: np.ndarray,
    eer: Optional[float] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a Detection Error Trade-off (DET) curve with log scale.

    Parameters
    ----------
    far : np.ndarray
        False Acceptance Rate (= FPR).
    frr : np.ndarray
        False Rejection Rate (= FNR = 1 - TPR).
    eer : float, optional
        Equal Error Rate.  If given, marked on the curve.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    far = np.asarray(far)
    frr = np.asarray(frr)

    # Filter out zeros for log scale
    mask = (far > 0) & (frr > 0)
    far_plot = far[mask]
    frr_plot = frr[mask]

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.loglog(far_plot, frr_plot, "r-", linewidth=2, label="DET")

    # Diagonal (EER line)
    diag = np.logspace(-4, 0, 100)
    ax.loglog(diag, diag, "k--", linewidth=1, alpha=0.4, label="EER line")

    if eer is not None:
        ax.scatter([eer], [eer], color="green", s=100, zorder=5, label=f"EER = {eer:.4f}")

    ax.set_xlabel("False Acceptance Rate (FAR)")
    ax.set_ylabel("False Rejection Rate (FRR)")
    ax.set_title("DET Curve")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3, which="both")
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_threshold_sweep(
    thresholds: np.ndarray,
    far: np.ndarray,
    frr: np.ndarray,
    eer_thresh: Optional[float] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot FAR and FRR as a function of decision threshold.

    Parameters
    ----------
    thresholds : np.ndarray
        Decision thresholds.
    far : np.ndarray
        False Acceptance Rate at each threshold.
    frr : np.ndarray
        False Rejection Rate at each threshold.
    eer_thresh : float, optional
        Threshold at Equal Error Rate.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    thresholds = np.asarray(thresholds)
    far = np.asarray(far)
    frr = np.asarray(frr)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(thresholds, far, "r-", linewidth=2, label="FAR")
    ax.plot(thresholds, frr, "b-", linewidth=2, label="FRR")

    if eer_thresh is not None:
        ax.axvline(eer_thresh, color="green", linestyle="--", linewidth=1.5, label=f"EER threshold = {eer_thresh:.4f}")

    ax.set_xlabel("Decision Threshold")
    ax.set_ylabel("Error Rate")
    ax.set_title("Threshold Sweep (FAR vs FRR)")
    ax.legend()
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_multi_method_comparison(
    results_dict: Dict[str, Tuple[np.ndarray, np.ndarray]],
    metric: str = "det",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Overlay multiple methods on the same ROC or DET plot.

    Parameters
    ----------
    results_dict : dict
        ``{method_name: (x_values, y_values)}``.
        For ``metric='roc'``: ``(fpr, tpr)``.
        For ``metric='det'``: ``(far, frr)``.
    metric : str
        ``'roc'`` or ``'det'``.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=(8, 8))
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(results_dict), 1)))

    for (name, (xs, ys)), color in zip(results_dict.items(), colors):
        xs = np.asarray(xs)
        ys = np.asarray(ys)

        if metric.lower() == "det":
            mask = (xs > 0) & (ys > 0)
            ax.loglog(xs[mask], ys[mask], linewidth=2, label=name, color=color)
        else:
            ax.plot(xs, ys, linewidth=2, label=name, color=color)

    if metric.lower() == "det":
        diag = np.logspace(-4, 0, 100)
        ax.loglog(diag, diag, "k--", linewidth=1, alpha=0.4)
        ax.set_xlabel("FAR")
        ax.set_ylabel("FRR")
        ax.set_title("DET Curve Comparison")
    else:
        ax.plot([0, 1], [0, 1], "k--", linewidth=1, alpha=0.4)
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.set_title("ROC Curve Comparison")
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.set_aspect("equal")

    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3, which="both")
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig
