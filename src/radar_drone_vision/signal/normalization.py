"""Feature normalisation utilities.

Provides common normalisation strategies for 2-D feature matrices
where each row is one sample (or frame).  All functions accept both
real and complex arrays; for complex input the operation is applied
independently to real and imaginary parts (except ``l2`` which
normalises the magnitude).
"""

from __future__ import annotations

from typing import Literal

import numpy as np


def normalize_features(
    features: np.ndarray,
    method: str = "zscore",
    axis: int | None = None,
    eps: float = 1e-8,
) -> np.ndarray:
    """Normalise a feature matrix.

    Parameters
    ----------
    features : np.ndarray
        Input features (typically 2-D: ``(n_samples, n_features)``).
    method : str
        Normalisation method:

        * ``"zscore"`` – zero mean, unit variance (global or per-axis).
        * ``"minmax"`` – scale to [0, 1].
        * ``"l2"`` – each row is divided by its L2 norm.
        * ``"per_sample"`` – z-score computed **per row** (each sample
          independently).
        * ``"max_abs"`` – scale by the global maximum absolute value.
    axis : int or None
        Axis along which to compute statistics for ``"zscore"`` and
        ``"minmax"``.  ``None`` means global statistics; ``0`` means
        per-feature (column-wise); ``1`` means per-sample (row-wise).
        Ignored for ``"l2"`` and ``"per_sample"``.
    eps : float
        Small constant to avoid division by zero.

    Returns
    -------
    normed : np.ndarray
        Normalised copy of *features* (input is never modified).

    Raises
    ------
    ValueError
        If *method* is not recognised.
    """
    features = np.array(features, dtype=np.result_type(features, np.float64), copy=True)

    if method == "zscore":
        return _zscore(features, axis, eps)
    if method == "minmax":
        return _minmax(features, axis, eps)
    if method == "l2":
        return _l2(features, eps)
    if method == "per_sample":
        return _zscore(features, axis=1, eps=eps)
    if method == "max_abs":
        return _max_abs(features, eps)

    raise ValueError(
        f"Unknown normalisation method '{method}'. "
        f"Choose from: zscore, minmax, l2, per_sample, max_abs."
    )


# ------------------------------------------------------------------
# Strategy implementations
# ------------------------------------------------------------------

def _zscore(
    data: np.ndarray, axis: int | None, eps: float
) -> np.ndarray:
    """Standard-score normalisation."""
    if np.iscomplexobj(data):
        data.real = _zscore(data.real.copy(), axis, eps)
        data.imag = _zscore(data.imag.copy(), axis, eps)
        return data

    mean = np.mean(data, axis=axis, keepdims=True)
    std = np.std(data, axis=axis, keepdims=True)
    return (data - mean) / (std + eps)


def _minmax(
    data: np.ndarray, axis: int | None, eps: float
) -> np.ndarray:
    """Min-max scaling to [0, 1]."""
    if np.iscomplexobj(data):
        data.real = _minmax(data.real.copy(), axis, eps)
        data.imag = _minmax(data.imag.copy(), axis, eps)
        return data

    dmin = np.min(data, axis=axis, keepdims=True)
    dmax = np.max(data, axis=axis, keepdims=True)
    return (data - dmin) / (dmax - dmin + eps)


def _l2(data: np.ndarray, eps: float) -> np.ndarray:
    """Row-wise L2 normalisation."""
    if data.ndim == 1:
        norm = np.linalg.norm(data) + eps
        return data / norm

    norms = np.linalg.norm(data, axis=-1, keepdims=True)
    return data / (norms + eps)


def _max_abs(data: np.ndarray, eps: float) -> np.ndarray:
    """Divide by the global maximum absolute value."""
    peak = np.max(np.abs(data))
    return data / (peak + eps)
