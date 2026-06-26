"""Classical ML methods for radar micro-Doppler classification."""

from radar_drone_vision.classical.pca import fit_pca, transform_pca
from radar_drone_vision.classical.sra import SubspaceReliabilityAnalysis
from radar_drone_vision.classical.mahalanobis import mahalanobis_distance, fit_class_stats
from radar_drone_vision.classical.thresholds import (
    sweep_thresholds,
    find_eer_threshold,
    find_far_at_frr,
)

__all__ = [
    "fit_pca",
    "transform_pca",
    "SubspaceReliabilityAnalysis",
    "mahalanobis_distance",
    "fit_class_stats",
    "sweep_thresholds",
    "find_eer_threshold",
    "find_far_at_frr",
]
