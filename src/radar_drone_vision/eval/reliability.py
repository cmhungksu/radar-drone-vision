"""Eigen-spectrum reliability analysis for subspace-based radar features."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import numpy as np


def compute_eigenspectrum(covariance_matrix: np.ndarray) -> np.ndarray:
    """Compute eigenvalues of a covariance matrix, sorted descending.

    Parameters
    ----------
    covariance_matrix : np.ndarray
        Symmetric positive semi-definite matrix.

    Returns
    -------
    np.ndarray
        Eigenvalues in descending order.
    """
    cov = np.asarray(covariance_matrix, dtype=np.float64)
    eigenvalues = np.linalg.eigvalsh(cov)
    return np.sort(eigenvalues)[::-1]


def reliability_score(
    eigenvalues: np.ndarray,
    threshold_ratio: float = 0.01,
) -> int:
    """Count the number of 'reliable' dimensions in the eigen-spectrum.

    A dimension is reliable if its eigenvalue is at least
    ``threshold_ratio * max_eigenvalue``.

    Parameters
    ----------
    eigenvalues : array-like
        Eigenvalues sorted in descending order.
    threshold_ratio : float
        Minimum fraction of the largest eigenvalue to be considered reliable.

    Returns
    -------
    int
        Number of reliable dimensions.
    """
    eigenvalues = np.asarray(eigenvalues, dtype=np.float64)
    if len(eigenvalues) == 0:
        return 0
    max_ev = eigenvalues[0]
    if max_ev <= 0:
        return 0
    threshold = threshold_ratio * max_ev
    return int(np.sum(eigenvalues >= threshold))


def feature_dim_vs_error(
    sra_model: Callable,
    X_test: np.ndarray,
    y_test: np.ndarray,
    dim_range: Optional[List[int]] = None,
) -> List[Tuple[int, float]]:
    """Sweep subspace dimensions and compute error rate for each.

    Parameters
    ----------
    sra_model : callable
        A fitted model with a ``predict(X, n_components=d)`` method that
        accepts the number of subspace dimensions.
    X_test : np.ndarray
        Test feature matrix.
    y_test : np.ndarray
        Test labels.
    dim_range : list of int, optional
        Subspace dimensions to test. Defaults to ``[1, 2, ..., min(20, X_test.shape[1]))]``.

    Returns
    -------
    list of (dim, error_rate) tuples
        Error rate for each subspace dimension.
    """
    X_test = np.asarray(X_test)
    y_test = np.asarray(y_test)

    if dim_range is None:
        max_dim = min(20, X_test.shape[1]) if X_test.ndim > 1 else 1
        dim_range = list(range(1, max_dim + 1))

    results: List[Tuple[int, float]] = []
    for d in dim_range:
        try:
            y_pred = sra_model.predict(X_test, n_components=d)
            error_rate = float(np.mean(y_pred != y_test))
        except Exception:
            error_rate = float("nan")
        results.append((d, error_rate))

    return results
