"""Convert 2-D feature maps and complex matrices to 1-D feature vectors."""

from __future__ import annotations

import numpy as np


def vectorize_2d(
    feature_2d: np.ndarray,
    mode: str = "flatten",
) -> np.ndarray:
    """Convert a 2-D feature map into a 1-D vector.

    Parameters
    ----------
    feature_2d : np.ndarray
        2-D array of shape ``(rows, cols)``.
    mode : str
        - ``flatten`` -- row-major ravel (default).
        - ``upper_triangle`` -- upper-triangular elements (including
          diagonal), useful for symmetric matrices such as covariance.
        - ``mean_pool`` -- column-wise mean, yielding a vector of length
          ``cols``.

    Returns
    -------
    vec : np.ndarray
        1-D feature vector.

    Raises
    ------
    ValueError
        If *mode* is unrecognised or the input is not 2-D.
    """
    feature_2d = np.asarray(feature_2d)
    if feature_2d.ndim != 2:
        raise ValueError(
            f"Expected 2-D input, got shape {feature_2d.shape}"
        )

    if mode == "flatten":
        return feature_2d.ravel()
    elif mode == "upper_triangle":
        return feature_2d[np.triu_indices(feature_2d.shape[0])]
    elif mode == "mean_pool":
        return feature_2d.mean(axis=0)
    else:
        raise ValueError(
            f"Unknown mode '{mode}'. Choose from: flatten, upper_triangle, mean_pool"
        )


def to_feature_vector(
    complex_matrix: np.ndarray,
    feature_mode: str = "real_imag_concat",
) -> np.ndarray:
    """Convert a complex-valued matrix to a real feature vector.

    Parameters
    ----------
    complex_matrix : np.ndarray
        Arbitrarily shaped array (may be real or complex).
    feature_mode : str
        - ``real_imag_concat`` -- flatten real part, then imaginary part,
          and concatenate (default).  Output length = 2 * numel.
        - ``magnitude_only`` -- flatten ``|z|``.
        - ``magnitude_phase_concat`` -- flatten ``|z|`` then ``angle(z)``
          and concatenate.  Output length = 2 * numel.
        - ``complex_abs`` -- alias for ``magnitude_only``.

    Returns
    -------
    vec : np.ndarray (float)
        1-D real-valued feature vector.

    Raises
    ------
    ValueError
        If *feature_mode* is unrecognised.
    """
    arr = np.asarray(complex_matrix)

    if feature_mode == "real_imag_concat":
        return np.concatenate([arr.real.ravel(), arr.imag.ravel()])
    elif feature_mode == "magnitude_only" or feature_mode == "complex_abs":
        return np.abs(arr).ravel()
    elif feature_mode == "magnitude_phase_concat":
        return np.concatenate([np.abs(arr).ravel(), np.angle(arr).ravel()])
    else:
        raise ValueError(
            f"Unknown feature_mode '{feature_mode}'. Choose from: "
            "real_imag_concat, magnitude_only, magnitude_phase_concat, complex_abs"
        )
