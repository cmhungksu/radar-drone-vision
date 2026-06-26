"""Standard power / magnitude spectrogram from pre-framed signals.

The input is expected to be a 2-D array of windowed frames produced by
:func:`radar_drone_vision.signal.framing.frame_signal`.
"""

from __future__ import annotations

import numpy as np

from .fft import compute_fft


def compute_spectrogram(
    frames: np.ndarray,
    n_fft: int = 256,
    power: bool = True,
    log_scale: bool = False,
    eps: float = 1e-10,
    onesided: bool = False,
) -> np.ndarray:
    """Compute a spectrogram from windowed frames.

    Parameters
    ----------
    frames : np.ndarray
        2-D array of shape ``(num_frames, frame_size)`` (real or complex).
    n_fft : int
        FFT length per frame.
    power : bool
        If *True* return the **power** spectrogram (|X|²).
        If *False* return the **magnitude** spectrogram (|X|).
    log_scale : bool
        If *True*, apply ``10 * log10(S + eps)`` to the result.
    eps : float
        Floor value added before taking the logarithm (prevents -inf).
    onesided : bool
        If *True* and the input is real, return only the non-negative
        frequency bins (``n_fft // 2 + 1``).

    Returns
    -------
    S : np.ndarray
        Spectrogram of shape ``(num_frames, n_freq)`` where *n_freq* is
        *n_fft* (or ``n_fft // 2 + 1`` when *onesided* is True).
    """
    frames = np.asarray(frames)
    if frames.ndim == 1:
        frames = frames[np.newaxis, :]

    spectrum = compute_fft(frames, n_fft=n_fft, axis=-1)

    if onesided and np.isrealobj(frames):
        n_keep = n_fft // 2 + 1
        spectrum = spectrum[:, :n_keep]

    mag = np.abs(spectrum)
    S = (mag ** 2) if power else mag

    if log_scale:
        S = 10.0 * np.log10(S + eps)

    return S
