"""DET (Detection Error Tradeoff) curve computation."""

from __future__ import annotations

from typing import Tuple

import numpy as np


def compute_det_curve(
    y_true: np.ndarray,
    scores: np.ndarray,
    n_thresholds: int = 500,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute FAR and FRR arrays for a DET curve.

    Parameters
    ----------
    y_true : array-like
        Binary labels (1 = UAV positive).
    scores : array-like
        Continuous scores (higher = UAV).
    n_thresholds : int
        Number of threshold points to evaluate.

    Returns
    -------
    far : np.ndarray
        False Acceptance Rate at each threshold.
    frr : np.ndarray
        False Rejection Rate at each threshold.
    thresholds : np.ndarray
        The thresholds evaluated.
    """
    y_true = np.asarray(y_true, dtype=int)
    scores = np.asarray(scores, dtype=float)

    pos = scores[y_true == 1]
    neg = scores[y_true == 0]

    if len(pos) == 0 or len(neg) == 0:
        return np.array([0.0]), np.array([0.0]), np.array([0.0])

    lo, hi = float(scores.min()), float(scores.max())
    thresholds = np.linspace(lo, hi, n_thresholds)

    far = np.array([np.mean(neg >= t) for t in thresholds])
    frr = np.array([np.mean(pos < t) for t in thresholds])

    return far, frr, thresholds
