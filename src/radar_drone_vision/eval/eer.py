"""Equal Error Rate (EER) computation for UAV detection.

Conventions:
    - Positive class (y=1): UAV
    - FRR (False Rejection Rate): UAV classified as non-UAV (miss)
    - FAR (False Acceptance Rate): non-UAV classified as UAV (false alarm)
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def compute_eer(
    y_true: np.ndarray,
    scores: np.ndarray,
) -> Tuple[float, float]:
    """Compute the Equal Error Rate.

    Parameters
    ----------
    y_true : array-like
        Binary labels (1 = UAV positive).
    scores : array-like
        Continuous scores — higher values indicate UAV.

    Returns
    -------
    eer : float
        The EER value (between 0 and 1).
    eer_threshold : float
        The score threshold at which FAR == FRR.
    """
    y_true = np.asarray(y_true, dtype=int)
    scores = np.asarray(scores, dtype=float)

    pos = scores[y_true == 1]
    neg = scores[y_true == 0]

    if len(pos) == 0 or len(neg) == 0:
        return 0.0, 0.0

    thresholds = np.sort(np.unique(scores))

    far_arr = np.array([np.mean(neg >= t) for t in thresholds])
    frr_arr = np.array([np.mean(pos < t) for t in thresholds])

    # Find crossing point
    diff = far_arr - frr_arr
    idx = np.argmin(np.abs(diff))

    eer = float((far_arr[idx] + frr_arr[idx]) / 2.0)
    eer_threshold = float(thresholds[idx])
    return eer, eer_threshold


def compute_far_at_frr(
    y_true: np.ndarray,
    scores: np.ndarray,
    target_frr: float = 0.01,
) -> float:
    """Compute FAR at a given FRR operating point.

    Parameters
    ----------
    y_true : array-like
        Binary labels (1 = UAV).
    scores : array-like
        Continuous scores (higher = UAV).
    target_frr : float
        Desired FRR (e.g. 0.01 for 1%).

    Returns
    -------
    far : float
        The FAR when FRR <= target_frr.
    """
    y_true = np.asarray(y_true, dtype=int)
    scores = np.asarray(scores, dtype=float)

    pos = scores[y_true == 1]
    neg = scores[y_true == 0]

    if len(pos) == 0 or len(neg) == 0:
        return 0.0

    thresholds = np.sort(np.unique(scores))

    for t in thresholds:
        frr = np.mean(pos < t)
        if frr <= target_frr:
            far = float(np.mean(neg >= t))
            return far

    # If no threshold achieves target FRR, return FAR at the lowest threshold
    return float(np.mean(neg >= thresholds[0]))
