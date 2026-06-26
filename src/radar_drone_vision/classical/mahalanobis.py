"""Mahalanobis distance utilities for radar classification."""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np


def mahalanobis_distance(
    x: np.ndarray,
    mean: np.ndarray,
    cov_inv: np.ndarray,
) -> np.ndarray:
    """Compute the Mahalanobis distance of samples from a distribution.

    Parameters
    ----------
    x : np.ndarray
        Sample(s).  Shape ``(d,)`` for a single sample or ``(n, d)``
        for a batch.
    mean : np.ndarray, shape (d,)
        Distribution mean.
    cov_inv : np.ndarray, shape (d, d)
        Inverse of the covariance matrix.

    Returns
    -------
    dist : np.ndarray
        Scalar (single sample) or 1-D array of Mahalanobis distances.
    """
    x = np.asarray(x, dtype=np.float64)
    mean = np.asarray(mean, dtype=np.float64)
    cov_inv = np.asarray(cov_inv, dtype=np.float64)

    single = x.ndim == 1
    if single:
        x = x.reshape(1, -1)

    diff = x - mean  # (n, d)
    left = diff @ cov_inv  # (n, d)
    dist_sq = np.sum(left * diff, axis=1)  # (n,)
    dist = np.sqrt(np.maximum(dist_sq, 0.0))

    return dist[0] if single else dist


def fit_class_stats(
    X: np.ndarray,
    y: np.ndarray,
    ridge: float = 1e-6,
) -> Dict[int, Dict[str, np.ndarray]]:
    """Compute per-class mean, covariance, and inverse covariance.

    Parameters
    ----------
    X : np.ndarray, shape (n, d)
        Feature matrix.
    y : np.ndarray, shape (n,)
        Class labels (integer).
    ridge : float
        Ridge regularisation added to covariance diagonals.

    Returns
    -------
    stats : dict
        ``{class_label: {"mean": ..., "cov": ..., "cov_inv": ...}}``.
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y).ravel()
    d = X.shape[1]
    reg = ridge * np.eye(d, dtype=np.float64)

    stats: Dict[int, Dict[str, np.ndarray]] = {}
    for label in np.unique(y):
        Xc = X[y == label]
        mean = Xc.mean(axis=0)
        cov = np.cov(Xc, rowvar=False, ddof=1) + reg
        if cov.ndim == 0:
            cov = np.atleast_2d(cov)
        cov_inv = np.linalg.pinv(cov)
        stats[int(label)] = {"mean": mean, "cov": cov, "cov_inv": cov_inv}

    return stats
