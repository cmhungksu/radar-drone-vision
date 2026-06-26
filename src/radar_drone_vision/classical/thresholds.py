"""Threshold search utilities for binary detection evaluation.

Convention
----------
- Positive class: UAV (``y = 1``).
- FRR (False Rejection Rate): fraction of UAV samples misclassified as
  non-UAV.  Also known as *miss rate* or *FNMR*.
- FAR (False Acceptance Rate): fraction of non-UAV samples misclassified
  as UAV.  Also known as *FPR* or *FMR*.

For SRA scores, **lower** score means more UAV-like.  A sample is
predicted UAV when ``score < threshold``.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def sweep_thresholds(
    scores: np.ndarray,
    y_true: np.ndarray,
    n_points: int = 1000,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sweep thresholds and compute FAR / FRR at each.

    Parameters
    ----------
    scores : np.ndarray, shape (n,)
        Score for each sample (lower = more UAV-like).
    y_true : np.ndarray, shape (n,)
        Binary ground truth (``1`` = UAV, ``0`` = non-UAV).
    n_points : int
        Number of threshold values to evaluate.

    Returns
    -------
    thresholds : np.ndarray, shape (n_points,)
    far : np.ndarray, shape (n_points,)
        False Acceptance Rate at each threshold.
    frr : np.ndarray, shape (n_points,)
        False Rejection Rate at each threshold.
    """
    scores = np.asarray(scores, dtype=np.float64)
    y_true = np.asarray(y_true).ravel()

    uav_scores = scores[y_true == 1]
    non_uav_scores = scores[y_true == 0]
    n_uav = len(uav_scores)
    n_non_uav = len(non_uav_scores)

    lo = scores.min()
    hi = scores.max()
    margin = (hi - lo) * 0.05 + 1e-12
    thresholds = np.linspace(lo - margin, hi + margin, n_points)

    far = np.empty(n_points, dtype=np.float64)
    frr = np.empty(n_points, dtype=np.float64)

    for i, t in enumerate(thresholds):
        # Predict UAV when score < threshold
        if n_uav > 0:
            frr[i] = np.sum(uav_scores >= t) / n_uav
        else:
            frr[i] = 0.0
        if n_non_uav > 0:
            far[i] = np.sum(non_uav_scores < t) / n_non_uav
        else:
            far[i] = 0.0

    return thresholds, far, frr


def find_eer_threshold(
    scores: np.ndarray,
    y_true: np.ndarray,
    n_points: int = 10000,
) -> Tuple[float, float]:
    """Find the Equal Error Rate (EER) threshold.

    The EER is the operating point where ``FAR == FRR``.

    Parameters
    ----------
    scores, y_true : np.ndarray
    n_points : int
        Resolution of the threshold sweep.

    Returns
    -------
    eer_threshold : float
    eer_value : float
        The FAR (== FRR) at the EER operating point.
    """
    thresholds, far, frr = sweep_thresholds(scores, y_true, n_points=n_points)

    # EER is where the curves cross: find the index where |FAR - FRR| is minimised
    diff = np.abs(far - frr)
    idx = np.argmin(diff)
    eer_threshold = float(thresholds[idx])
    eer_value = float((far[idx] + frr[idx]) / 2.0)
    return eer_threshold, eer_value


def find_far_at_frr(
    scores: np.ndarray,
    y_true: np.ndarray,
    target_frr: float = 0.01,
    n_points: int = 10000,
) -> Tuple[float, float]:
    """Find the FAR at a given target FRR.

    Parameters
    ----------
    scores, y_true : np.ndarray
    target_frr : float
        Desired maximum FRR (e.g. 0.01 for 1 %).
    n_points : int

    Returns
    -------
    far_value : float
        FAR when FRR is closest to *target_frr*.
    threshold : float
        Corresponding threshold.
    """
    thresholds, far, frr = sweep_thresholds(scores, y_true, n_points=n_points)

    # Among thresholds where FRR <= target_frr, pick the one with lowest FAR
    mask = frr <= target_frr
    if not np.any(mask):
        # Fallback: pick threshold closest to target_frr
        idx = np.argmin(np.abs(frr - target_frr))
    else:
        candidates = np.where(mask)[0]
        idx = candidates[np.argmin(far[candidates])]

    return float(far[idx]), float(thresholds[idx])
