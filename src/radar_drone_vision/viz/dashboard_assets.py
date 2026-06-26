"""Dashboard summary asset generation.

Generates all summary plots for the web dashboard from evaluation metrics.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import matplotlib.pyplot as plt
import numpy as np

from .roc_det_plot import plot_roc_curve, plot_det_curve
from .eigen_plot import plot_eigenspectrum

logger = logging.getLogger(__name__)


def generate_dashboard_summary(
    metrics: Dict[str, Any],
    dataset_info: Dict[str, Any],
    save_dir: Optional[str] = None,
) -> Dict[str, plt.Figure]:
    """Generate all summary plots for the web dashboard.

    Parameters
    ----------
    metrics : dict
        Evaluation metrics.  Expected keys (all optional):

        - ``accuracy`` : float
        - ``precision`` : float
        - ``recall`` : float
        - ``f1`` : float
        - ``eer`` : float
        - ``auc`` : float
        - ``fpr`` : array-like
        - ``tpr`` : array-like
        - ``far`` : array-like
        - ``frr`` : array-like
        - ``eigenvalues_uav`` : array-like
        - ``eigenvalues_non_uav`` : array-like
        - ``confusion_matrix`` : 2-D array-like

    dataset_info : dict
        Dataset metadata.  Expected keys (all optional):

        - ``name`` : str
        - ``n_samples`` : int
        - ``n_uav`` : int
        - ``n_non_uav`` : int
        - ``class_distribution`` : dict

    save_dir : str, optional
        Directory to save all generated assets.

    Returns
    -------
    figures : dict
        ``{figure_name: matplotlib.figure.Figure}``.
    """
    figures: Dict[str, plt.Figure] = {}
    out = Path(save_dir) if save_dir is not None else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    # 1. Metrics summary card
    fig_summary = _plot_metrics_card(metrics, dataset_info)
    figures["metrics_summary"] = fig_summary
    if out is not None:
        fig_summary.savefig(out / "metrics_summary.png", dpi=150, bbox_inches="tight")

    # 2. ROC curve (if data available)
    fpr = metrics.get("fpr")
    tpr = metrics.get("tpr")
    if fpr is not None and tpr is not None:
        auc_val = metrics.get("auc")
        fig_roc = plot_roc_curve(np.asarray(fpr), np.asarray(tpr), auc_val=auc_val)
        figures["roc_curve"] = fig_roc
        if out is not None:
            fig_roc.savefig(out / "roc_curve.png", dpi=150, bbox_inches="tight")

    # 3. DET curve (if data available)
    far = metrics.get("far")
    frr = metrics.get("frr")
    if far is not None and frr is not None:
        eer = metrics.get("eer")
        fig_det = plot_det_curve(np.asarray(far), np.asarray(frr), eer=eer)
        figures["det_curve"] = fig_det
        if out is not None:
            fig_det.savefig(out / "det_curve.png", dpi=150, bbox_inches="tight")

    # 4. Eigenspectrum (if data available)
    eig_uav = metrics.get("eigenvalues_uav")
    eig_non = metrics.get("eigenvalues_non_uav")
    if eig_uav is not None and eig_non is not None:
        fig_eig = plot_eigenspectrum(np.asarray(eig_uav), np.asarray(eig_non))
        figures["eigenspectrum"] = fig_eig
        if out is not None:
            fig_eig.savefig(out / "eigenspectrum.png", dpi=150, bbox_inches="tight")

    # 5. Confusion matrix (if available)
    cm = metrics.get("confusion_matrix")
    if cm is not None:
        fig_cm = _plot_confusion_matrix(np.asarray(cm))
        figures["confusion_matrix"] = fig_cm
        if out is not None:
            fig_cm.savefig(out / "confusion_matrix.png", dpi=150, bbox_inches="tight")

    # 6. Class distribution bar chart
    class_dist = dataset_info.get("class_distribution")
    if class_dist is not None:
        fig_dist = _plot_class_distribution(class_dist)
        figures["class_distribution"] = fig_dist
        if out is not None:
            fig_dist.savefig(out / "class_distribution.png", dpi=150, bbox_inches="tight")

    # 7. Save metrics JSON
    if out is not None:
        json_metrics = {k: v for k, v in metrics.items() if not isinstance(v, np.ndarray)}
        try:
            with open(out / "metrics.json", "w") as f:
                json.dump(json_metrics, f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Could not save metrics JSON: %s", exc)

    logger.info("Generated %d dashboard figures", len(figures))
    return figures


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _plot_metrics_card(
    metrics: Dict[str, Any],
    dataset_info: Dict[str, Any],
) -> plt.Figure:
    """Render a summary metrics card as a figure."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.set_axis_off()

    lines = []
    ds_name = dataset_info.get("name", "Unknown dataset")
    n_samples = dataset_info.get("n_samples", "?")
    lines.append(f"Dataset: {ds_name}  |  Samples: {n_samples}")
    lines.append("")

    metric_keys = ["accuracy", "precision", "recall", "f1", "eer", "auc"]
    for key in metric_keys:
        val = metrics.get(key)
        if val is not None:
            lines.append(f"  {key.upper():>12s}:  {val:.4f}")

    text = "\n".join(lines)
    ax.text(
        0.05,
        0.95,
        text,
        transform=ax.transAxes,
        fontsize=12,
        fontfamily="monospace",
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f0f0f0", edgecolor="#cccccc"),
    )
    ax.set_title("Evaluation Summary", fontsize=14, fontweight="bold")
    fig.tight_layout()
    return fig


def _plot_confusion_matrix(cm: np.ndarray) -> plt.Figure:
    """Plot a confusion matrix heatmap."""
    import seaborn as sns

    fig, ax = plt.subplots(figsize=(6, 5))
    labels = ["Non-UAV", "UAV"]
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=labels[:cm.shape[1]],
        yticklabels=labels[:cm.shape[0]],
        ax=ax,
    )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Confusion Matrix")
    fig.tight_layout()
    return fig


def _plot_class_distribution(class_dist: Dict[str, int]) -> plt.Figure:
    """Plot a bar chart of class distribution."""
    fig, ax = plt.subplots(figsize=(8, 4))
    names = list(class_dist.keys())
    counts = list(class_dist.values())

    colors = ["#e74c3c" if "drone" in n.lower() or "uav" in n.lower() else "#3498db" for n in names]
    ax.bar(names, counts, color=colors, alpha=0.8, edgecolor="white")
    ax.set_xlabel("Class")
    ax.set_ylabel("Count")
    ax.set_title("Class Distribution")
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    return fig
