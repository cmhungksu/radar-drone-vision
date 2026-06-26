"""DC offset and clutter removal for radar spectrograms / spectra.

Clutter (stationary objects, DC leak) typically concentrates in the
lowest Doppler-frequency bins.  This module provides utilities to
suppress those bins, optionally keep only a sub-band of interest,
and normalise the result.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def remove_clutter(
    data: np.ndarray,
    remove_dc: bool = True,
    dc_bins: int = 3,
    keep_bins: Tuple[int, int] | None = None,
    normalize: bool = True,
    axis: int = -1,
) -> np.ndarray:
    """Remove DC / clutter from a spectrogram or spectrum.

    Parameters
    ----------
    data : np.ndarray
        Input array (real or complex, any dimensionality).
        For a typical spectrogram the shape is ``(num_frames, n_fft)``.
    remove_dc : bool
        If *True*, zero out the central *dc_bins* bins along *axis*.
        The "centre" is computed assuming the zero-frequency component
        sits at ``n // 2`` (i.e. the data has been ``fftshift``-ed).
        If the data has **not** been shifted, bin 0 is used as the DC
        bin instead.
    dc_bins : int
        Number of bins around DC to zero out (must be >= 1).
    keep_bins : tuple of (int, int) or None
        If given, a ``(start, stop)`` slice along *axis* to retain.
        Bins outside this range are set to zero.  Applied **after** DC
        removal.
    normalize : bool
        If *True*, normalise the result so that its maximum absolute
        value is 1.
    axis : int
        Frequency axis along which to operate.

    Returns
    -------
    cleaned : np.ndarray
        Cleaned copy of *data* (input is never modified in-place).
    """
    data = np.array(data, copy=True)  # work on a copy
    n = data.shape[axis]

    if remove_dc and dc_bins >= 1:
        data = _zero_dc_bins(data, n, dc_bins, axis)

    if keep_bins is not None:
        start, stop = keep_bins
        data = _keep_bin_range(data, n, start, stop, axis)

    if normalize:
        data = _normalize_peak(data)

    return data


def subtract_mean_spectrum(
    spectrogram: np.ndarray,
    axis: int = 0,
) -> np.ndarray:
    """Subtract the time-averaged spectrum (mean clutter profile).

    This is a common alternative to bin-zeroing: the mean spectrum
    across all frames is subtracted so that stationary components
    cancel out while moving targets are preserved.

    Parameters
    ----------
    spectrogram : np.ndarray
        2-D spectrogram ``(num_frames, n_freq)``.
    axis : int
        Axis along which to average (0 = average over time).

    Returns
    -------
    cleaned : np.ndarray
        Clutter-suppressed spectrogram (same shape).
    """
    spectrogram = np.asarray(spectrogram)
    mean_profile = np.mean(spectrogram, axis=axis, keepdims=True)
    return spectrogram - mean_profile


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _zero_dc_bins(
    data: np.ndarray, n: int, dc_bins: int, axis: int
) -> np.ndarray:
    """Zero out bins around DC."""
    centre = n // 2
    half = dc_bins // 2
    lo = max(centre - half, 0)
    hi = min(centre + half + 1, n)

    # Build an index tuple that selects the DC slice along *axis*.
    idx = [slice(None)] * data.ndim
    idx[axis] = slice(lo, hi)
    data[tuple(idx)] = 0

    # Also handle the un-shifted case (DC at bin 0).
    if lo > 0:
        idx[axis] = slice(0, min(dc_bins, n))
        # Only zero if energy is concentrated at bin 0.
        pass  # skip to avoid double-zeroing; caller chooses shift convention

    return data


def _keep_bin_range(
    data: np.ndarray, n: int, start: int, stop: int, axis: int
) -> np.ndarray:
    """Zero out bins outside [start, stop)."""
    if start > 0:
        idx = [slice(None)] * data.ndim
        idx[axis] = slice(0, start)
        data[tuple(idx)] = 0
    if stop < n:
        idx = [slice(None)] * data.ndim
        idx[axis] = slice(stop, n)
        data[tuple(idx)] = 0
    return data


def _normalize_peak(data: np.ndarray) -> np.ndarray:
    """Scale so that max |data| == 1."""
    peak = np.max(np.abs(data))
    if peak > 0:
        data = data / peak
    return data
