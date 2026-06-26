"""Range-Doppler, Doppler-time waterfall, and range-time plots."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np


def plot_range_doppler_map(
    rd_map: np.ndarray,
    range_axis: Optional[Sequence[float]] = None,
    doppler_axis: Optional[Sequence[float]] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a 2-D range-Doppler map.

    Parameters
    ----------
    rd_map : np.ndarray
        2-D array of shape ``(n_range, n_doppler)``.
    range_axis : sequence of float, optional
        Range values in metres for the y-axis.
    doppler_axis : sequence of float, optional
        Doppler velocity values in m/s for the x-axis.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    rd_map = np.asarray(rd_map)
    if rd_map.ndim != 2:
        raise ValueError(f"Expected 2-D array, got shape {rd_map.shape}")

    fig, ax = plt.subplots(figsize=(8, 6))

    extent = None
    if doppler_axis is not None and range_axis is not None:
        doppler_axis = np.asarray(doppler_axis)
        range_axis = np.asarray(range_axis)
        extent = [
            float(doppler_axis[0]),
            float(doppler_axis[-1]),
            float(range_axis[0]),
            float(range_axis[-1]),
        ]

    im = ax.imshow(
        rd_map,
        aspect="auto",
        origin="lower",
        cmap="jet",
        interpolation="nearest",
        extent=extent,
    )
    ax.set_xlabel("Doppler velocity (m/s)" if doppler_axis is not None else "Doppler bin")
    ax.set_ylabel("Range (m)" if range_axis is not None else "Range bin")
    ax.set_title("Range-Doppler Map")
    fig.colorbar(im, ax=ax, label="Power (dB)")
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_doppler_time_waterfall(
    spectrogram: np.ndarray,
    time_axis: Optional[Sequence[float]] = None,
    doppler_axis: Optional[Sequence[float]] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a Doppler-time waterfall (micro-Doppler signature).

    Parameters
    ----------
    spectrogram : np.ndarray
        2-D array of shape ``(n_time, n_doppler)``.
    time_axis : sequence of float, optional
        Time values in seconds for the x-axis.
    doppler_axis : sequence of float, optional
        Doppler frequency or velocity values for the y-axis.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    spectrogram = np.asarray(spectrogram)
    if spectrogram.ndim != 2:
        raise ValueError(f"Expected 2-D array, got shape {spectrogram.shape}")

    fig, ax = plt.subplots(figsize=(10, 5))

    extent = None
    if time_axis is not None and doppler_axis is not None:
        time_axis = np.asarray(time_axis)
        doppler_axis = np.asarray(doppler_axis)
        extent = [
            float(time_axis[0]),
            float(time_axis[-1]),
            float(doppler_axis[0]),
            float(doppler_axis[-1]),
        ]

    im = ax.imshow(
        spectrogram.T,
        aspect="auto",
        origin="lower",
        cmap="viridis",
        interpolation="nearest",
        extent=extent,
    )
    ax.set_xlabel("Time (s)" if time_axis is not None else "Time frame")
    ax.set_ylabel("Doppler (m/s)" if doppler_axis is not None else "Doppler bin")
    ax.set_title("Doppler-Time Waterfall (micro-Doppler)")
    fig.colorbar(im, ax=ax, label="Magnitude")
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_range_time(
    data: np.ndarray,
    time_axis: Optional[Sequence[float]] = None,
    range_axis: Optional[Sequence[float]] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a range-time intensity map.

    Parameters
    ----------
    data : np.ndarray
        2-D array of shape ``(n_time, n_range)``.
    time_axis : sequence of float, optional
        Time values in seconds.
    range_axis : sequence of float, optional
        Range values in metres.
    save_path : str, optional
        If given, save figure to this path.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    data = np.asarray(data)
    if data.ndim != 2:
        raise ValueError(f"Expected 2-D array, got shape {data.shape}")

    fig, ax = plt.subplots(figsize=(10, 5))

    extent = None
    if time_axis is not None and range_axis is not None:
        time_axis = np.asarray(time_axis)
        range_axis = np.asarray(range_axis)
        extent = [
            float(time_axis[0]),
            float(time_axis[-1]),
            float(range_axis[0]),
            float(range_axis[-1]),
        ]

    im = ax.imshow(
        data.T,
        aspect="auto",
        origin="lower",
        cmap="plasma",
        interpolation="nearest",
        extent=extent,
    )
    ax.set_xlabel("Time (s)" if time_axis is not None else "Time frame")
    ax.set_ylabel("Range (m)" if range_axis is not None else "Range bin")
    ax.set_title("Range-Time Intensity")
    fig.colorbar(im, ax=ax, label="Power")
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig
