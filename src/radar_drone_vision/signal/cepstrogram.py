"""Cepstral analysis – cepstrogram from pre-framed signals.

The cepstrogram is derived from the power spectrum via:

    FFT → |FFT|² → log → IFFT → |IFFT|²

Each row of the output corresponds to one frame's *power cepstrum*.
"""

from __future__ import annotations

import numpy as np

from .fft import compute_fft, compute_ifft


def compute_cepstrogram(
    frames: np.ndarray,
    n_fft: int = 256,
    eps: float = 1e-10,
    n_quefrency: int | None = None,
) -> np.ndarray:
    """Compute the cepstrogram (power cepstrum per frame).

    Parameters
    ----------
    frames : np.ndarray
        2-D array of shape ``(num_frames, frame_size)`` (real or complex).
    n_fft : int
        FFT length used for both the forward and inverse transforms.
    eps : float
        Floor added to the power spectrum before taking the log so that
        the logarithm is numerically stable.
    n_quefrency : int or None
        If given, truncate the output to the first *n_quefrency* quefrency
        bins.  Useful for keeping only the low-quefrency envelope.

    Returns
    -------
    cepstrogram : np.ndarray
        2-D real array of shape ``(num_frames, n_fft)`` (or
        ``(num_frames, n_quefrency)`` if truncated).
    """
    frames = np.asarray(frames)
    if frames.ndim == 1:
        frames = frames[np.newaxis, :]

    # 1. FFT of each frame.
    spectrum = compute_fft(frames, n_fft=n_fft, axis=-1)

    # 2. Power spectrum: |FFT|²
    power_spectrum = np.abs(spectrum) ** 2

    # 3. Log power spectrum.
    log_power = np.log(power_spectrum + eps)

    # 4. IFFT of log power spectrum.
    cepstrum_complex = compute_ifft(log_power, n_fft=n_fft, axis=-1)

    # 5. Power cepstrum: |IFFT|²
    cepstrogram = np.abs(cepstrum_complex) ** 2

    if n_quefrency is not None:
        cepstrogram = cepstrogram[:, :n_quefrency]

    return cepstrogram
