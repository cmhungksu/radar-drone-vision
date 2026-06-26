"""Cadence Velocity Diagram (CVD) computation.

A CVD is obtained by taking a second FFT of the spectrogram along the
**time** (slow-time) axis.  Each column of the resulting 2-D map shows
the periodic modulation strength at a given Doppler (velocity) bin.
"""

from __future__ import annotations

import numpy as np


def compute_cvd(
    spectrogram: np.ndarray,
    n_fft_time: int | None = None,
    log_scale: bool = False,
    eps: float = 1e-10,
    shift: bool = True,
) -> np.ndarray:
    """Compute the Cadence Velocity Diagram from a spectrogram.

    Parameters
    ----------
    spectrogram : np.ndarray
        2-D power/magnitude spectrogram of shape
        ``(num_frames, n_freq)``.  Typically produced by
        :func:`radar_drone_vision.signal.spectrogram.compute_spectrogram`.
    n_fft_time : int or None
        FFT length along the time axis.  Defaults to the number of
        frames (``spectrogram.shape[0]``).
    log_scale : bool
        If *True*, return ``10 * log10(|CVD| + eps)``.
    eps : float
        Floor value for log scaling.
    shift : bool
        If *True*, centre the zero-cadence component using
        :func:`numpy.fft.fftshift` along the time axis.

    Returns
    -------
    cvd : np.ndarray
        2-D array of shape ``(n_fft_time, n_freq)``.  The first axis
        represents cadence (modulation frequency) and the second axis
        represents velocity (Doppler frequency).
    """
    spectrogram = np.asarray(spectrogram)
    if spectrogram.ndim != 2:
        raise ValueError(
            f"spectrogram must be 2-D, got shape {spectrogram.shape}"
        )

    if n_fft_time is None:
        n_fft_time = spectrogram.shape[0]

    # FFT along the time axis (axis=0).
    cvd = np.fft.fft(spectrogram, n=n_fft_time, axis=0)
    cvd = np.abs(cvd)

    if shift:
        cvd = np.fft.fftshift(cvd, axes=0)

    if log_scale:
        cvd = 10.0 * np.log10(cvd + eps)

    return cvd
