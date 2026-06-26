"""Evaluation metrics for radar UAV detection."""

from .benchmark import benchmark_all_methods
from .confusion import compute_confusion_matrix, format_confusion_matrix
from .det_curve import compute_det_curve
from .eer import compute_eer, compute_far_at_frr
from .metrics import compute_all_metrics
from .reliability import compute_eigenspectrum, feature_dim_vs_error, reliability_score

__all__ = [
    "compute_all_metrics",
    "compute_eer",
    "compute_far_at_frr",
    "compute_det_curve",
    "compute_confusion_matrix",
    "format_confusion_matrix",
    "compute_eigenspectrum",
    "reliability_score",
    "feature_dim_vs_error",
    "benchmark_all_methods",
]
