"""Feature extraction pipeline for radar micro-Doppler signals.

Supported feature types:
- spectrogram
- cepstrogram
- cvd (Cadence Velocity Diagram)
- proposed_regularized_complex_log_fft
- proposed_complex_image
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import numpy as np

from radar_drone_vision.signal.framing import frame_signal
from radar_drone_vision.signal.fft import compute_fft


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def extract_features(
    samples: List[np.ndarray],
    feature_type: str,
    config: Optional[Dict[str, Any]] = None,
) -> np.ndarray:
    """Extract features from a list of radar samples.

    Parameters
    ----------
    samples : list of np.ndarray
        Each element is a 1-D raw radar signal (real or complex).
    feature_type : str
        One of ``spectrogram``, ``cepstrogram``, ``cvd``,
        ``proposed_regularized_complex_log_fft``,
        ``proposed_complex_image``.
    config : dict, optional
        Extraction parameters.  Recognised keys (with defaults):

        - ``frame_size`` (256)
        - ``hop_size`` (128)
        - ``n_fft`` (256)
        - ``window`` ("hann")
        - ``ridge`` (1e-6) -- regularisation for log operations
        - ``flatten`` (True) -- flatten 2-D feature to 1-D vector

    Returns
    -------
    X : np.ndarray
        Feature matrix of shape ``(n_samples, n_features)``.

    Raises
    ------
    ValueError
        If *feature_type* is unknown.
    """
    cfg = _default_config()
    if config is not None:
        cfg.update(config)

    extractors = {
        "spectrogram": _extract_spectrogram,
        "cepstrogram": _extract_cepstrogram,
        "cvd": _extract_cvd,
        "proposed_regularized_complex_log_fft": _extract_regularized_complex_log_fft,
        "proposed_complex_image": _extract_complex_image,
    }

    if feature_type not in extractors:
        raise ValueError(
            f"Unknown feature_type '{feature_type}'. "
            f"Choose from {list(extractors.keys())}"
        )

    feat_list: list[np.ndarray] = []
    for sig in samples:
        feat_2d = extractors[feature_type](sig, cfg)
        if cfg.get("flatten", True):
            feat_list.append(feat_2d.ravel())
        else:
            feat_list.append(feat_2d)

    return np.array(feat_list)


# ------------------------------------------------------------------ #
# Internal extractors
# ------------------------------------------------------------------ #

def _default_config() -> Dict[str, Any]:
    return {
        "frame_size": 256,
        "hop_size": 128,
        "n_fft": 256,
        "window": "hann",
        "ridge": 1e-6,
        "flatten": True,
    }


def _stft(signal: np.ndarray, cfg: Dict[str, Any]) -> np.ndarray:
    """Short-time Fourier Transform helper -> (n_frames, n_fft) complex."""
    frames = frame_signal(
        signal,
        frame_size=cfg["frame_size"],
        hop_size=cfg["hop_size"],
        window=cfg["window"],
    )
    return compute_fft(frames, n_fft=cfg["n_fft"], shift=True)


def _extract_spectrogram(signal: np.ndarray, cfg: Dict[str, Any]) -> np.ndarray:
    """Log-magnitude spectrogram (real-valued)."""
    spec = _stft(signal, cfg)
    mag = np.abs(spec)
    return np.log1p(mag)


def _extract_cepstrogram(signal: np.ndarray, cfg: Dict[str, Any]) -> np.ndarray:
    """Cepstrogram: IFFT of log-magnitude spectrum per frame."""
    spec = _stft(signal, cfg)
    mag = np.abs(spec)
    log_mag = np.log(mag + cfg["ridge"])
    ceps = np.fft.ifft(log_mag, axis=-1).real
    return ceps


def _extract_cvd(signal: np.ndarray, cfg: Dict[str, Any]) -> np.ndarray:
    """Cadence Velocity Diagram: 2-D FFT of spectrogram."""
    spec = _stft(signal, cfg)
    mag = np.abs(spec)
    cvd = np.fft.fft2(mag)
    cvd = np.fft.fftshift(cvd)
    return np.abs(cvd)


def _extract_regularized_complex_log_fft(
    signal: np.ndarray, cfg: Dict[str, Any]
) -> np.ndarray:
    """Proposed: regularised complex log-FFT feature.

    log(|S| + ridge) concatenated with the phase, giving a real 2-D
    representation that retains phase information.
    """
    spec = _stft(signal, cfg)
    mag = np.abs(spec)
    phase = np.angle(spec)
    log_mag = np.log(mag + cfg["ridge"])
    return np.concatenate([log_mag, phase], axis=-1)


def _extract_complex_image(signal: np.ndarray, cfg: Dict[str, Any]) -> np.ndarray:
    """Proposed: 2-channel complex image (real + imag stacked).

    Returns shape ``(n_frames, 2 * n_fft)`` with real and imaginary
    parts concatenated along the frequency axis.
    """
    spec = _stft(signal, cfg)
    return np.concatenate([spec.real, spec.imag], axis=-1)
