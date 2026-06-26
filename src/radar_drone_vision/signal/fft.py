"""Basic FFT / IFFT utilities for framed radar signals.

All helpers operate on arbitrary-dimensional arrays and default to
transforming along the last axis (``axis=-1``).  Both real and complex
inputs are handled transparently.
"""

from __future__ import annotations

import numpy as np


def compute_fft(
    frames: np.ndarray,
    n_fft: int = 256,
    axis: int = -1,
    shift: bool = False,
) -> np.ndarray:
    """Compute the DFT of each frame.

    Parameters
    ----------
    frames : np.ndarray
        Input array (real or complex).  Typically 2-D with shape
        ``(num_frames, frame_size)`` but any dimensionality is accepted.
    n_fft : int
        FFT length.  If larger than the frame length along *axis* the
        input is zero-padded; if smaller it is truncated.
    axis : int
        Axis along which to compute the FFT.
    shift : bool
        If *True*, apply :func:`numpy.fft.fftshift` so that the zero-
        frequency component is centred.

    Returns
    -------
    spectrum : np.ndarray (complex)
        Complex FFT result with the same shape as *frames* except the
        size along *axis* becomes *n_fft*.
    """
    frames = np.asarray(frames)
    spectrum = np.fft.fft(frames, n=n_fft, axis=axis)
    if shift:
        spectrum = np.fft.fftshift(spectrum, axes=axis)
    return spectrum


def compute_ifft(
    spectrum: np.ndarray,
    n_fft: int = 256,
    axis: int = -1,
    shift: bool = False,
) -> np.ndarray:
    """Compute the inverse DFT.

    Parameters
    ----------
    spectrum : np.ndarray
        Complex spectrum (or real – will be cast to complex internally).
    n_fft : int
        IFFT length.
    axis : int
        Axis along which to compute the IFFT.
    shift : bool
        If *True*, apply :func:`numpy.fft.ifftshift` **before** the
        IFFT (undo a prior ``fftshift``).

    Returns
    -------
    signal : np.ndarray (complex)
        Inverse FFT result.
    """
    spectrum = np.asarray(spectrum)
    if shift:
        spectrum = np.fft.ifftshift(spectrum, axes=axis)
    return np.fft.ifft(spectrum, n=n_fft, axis=axis)


def compute_rfft(
    frames: np.ndarray,
    n_fft: int = 256,
    axis: int = -1,
) -> np.ndarray:
    """Real-input FFT returning only non-negative frequencies.

    Parameters
    ----------
    frames : np.ndarray
        Real-valued input array.
    n_fft : int
        FFT length.
    axis : int
        Transform axis.

    Returns
    -------
    spectrum : np.ndarray (complex)
        Shape along *axis* is ``n_fft // 2 + 1``.
    """
    frames = np.asarray(frames, dtype=float)
    return np.fft.rfft(frames, n=n_fft, axis=axis)


def compute_irfft(
    spectrum: np.ndarray,
    n_fft: int = 256,
    axis: int = -1,
) -> np.ndarray:
    """Inverse real FFT.

    Parameters
    ----------
    spectrum : np.ndarray (complex)
        Non-negative-frequency spectrum produced by :func:`compute_rfft`.
    n_fft : int
        Desired output length.
    axis : int
        Transform axis.

    Returns
    -------
    signal : np.ndarray (float)
    """
    return np.fft.irfft(spectrum, n=n_fft, axis=axis)
