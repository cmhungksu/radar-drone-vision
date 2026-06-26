"""Numerical helper functions for radar signal processing."""

from __future__ import annotations

import numpy as np


def safe_log(x: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """Compute ``log(x + eps)`` to avoid log-of-zero.

    Parameters
    ----------
    x : np.ndarray
        Input array (should be non-negative).
    eps : float
        Small constant added before taking log.

    Returns
    -------
    np.ndarray
        ``np.log(x + eps)``
    """
    return np.log(np.asarray(x, dtype=np.float64) + eps)


def complex_to_real_imag(z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split a complex array into its real and imaginary parts.

    Parameters
    ----------
    z : np.ndarray
        Complex-valued array.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(real_part, imag_part)``
    """
    z = np.asarray(z)
    return z.real.copy(), z.imag.copy()


def real_imag_to_complex(real: np.ndarray, imag: np.ndarray) -> np.ndarray:
    """Combine real and imaginary parts into a complex array.

    Parameters
    ----------
    real : np.ndarray
        Real part.
    imag : np.ndarray
        Imaginary part.

    Returns
    -------
    np.ndarray
        Complex-valued array.
    """
    return np.asarray(real) + 1j * np.asarray(imag)
