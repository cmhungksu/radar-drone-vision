"""Frame a 1-D signal into overlapping windowed segments.

Supports both real and complex input signals.  The output is always a
2-D array of shape ``(num_frames, frame_size)`` with the chosen window
function applied element-wise.
"""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
from scipy.signal import get_window


def frame_signal(
    signal: np.ndarray,
    frame_size: int = 256,
    hop_size: int = 128,
    window: Union[str, np.ndarray, None] = "hann",
    center: bool = False,
    pad_mode: str = "reflect",
) -> np.ndarray:
    """Slice a 1-D signal into overlapping frames and apply a window.

    Parameters
    ----------
    signal : np.ndarray
        1-D input signal (real or complex).
    frame_size : int
        Length of each frame in samples.
    hop_size : int
        Number of samples between successive frame starts.
    window : str, np.ndarray, or None
        Window specification accepted by :func:`scipy.signal.get_window`,
        a pre-computed window array, or ``None`` for rectangular (no window).
    center : bool
        If *True*, the signal is zero-padded on both sides by
        ``frame_size // 2`` so that the first frame is centred at t = 0.
    pad_mode : str
        Padding mode forwarded to :func:`numpy.pad` when *center* is True.

    Returns
    -------
    frames : np.ndarray
        2-D array of shape ``(num_frames, frame_size)``.

    Raises
    ------
    ValueError
        If *signal* is not 1-D or *frame_size* / *hop_size* are invalid.
    """
    signal = np.asarray(signal)
    if signal.ndim != 1:
        raise ValueError(f"signal must be 1-D, got shape {signal.shape}")
    if frame_size < 1:
        raise ValueError(f"frame_size must be >= 1, got {frame_size}")
    if hop_size < 1:
        raise ValueError(f"hop_size must be >= 1, got {hop_size}")

    if center:
        pad_len = frame_size // 2
        signal = np.pad(signal, (pad_len, pad_len), mode=pad_mode)

    n_samples = len(signal)
    if n_samples < frame_size:
        # Pad to at least one full frame.
        pad_width = frame_size - n_samples
        signal = np.pad(signal, (0, pad_width), mode="constant")
        n_samples = len(signal)

    num_frames = 1 + (n_samples - frame_size) // hop_size

    # Build a strided view – no data copy.
    strides = (signal.strides[0] * hop_size, signal.strides[0])
    frames = np.lib.stride_tricks.as_strided(
        signal, shape=(num_frames, frame_size), strides=strides
    )
    # Copy so downstream code can safely write to frames.
    frames = frames.copy()

    # Apply window.
    win = _resolve_window(window, frame_size, signal.dtype)
    if win is not None:
        frames = frames * win[np.newaxis, :]

    return frames


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _resolve_window(
    window: Union[str, np.ndarray, None],
    frame_size: int,
    dtype: np.dtype,
) -> Optional[np.ndarray]:
    """Return a 1-D window array or *None* for rectangular."""
    if window is None:
        return None

    if isinstance(window, np.ndarray):
        if window.shape != (frame_size,):
            raise ValueError(
                f"Pre-computed window shape {window.shape} != ({frame_size},)"
            )
        return window.astype(dtype, copy=False)

    if isinstance(window, str):
        win = get_window(window, frame_size, fftbins=True)
        return win.astype(dtype, copy=False)

    raise TypeError(f"Unsupported window type: {type(window)}")
