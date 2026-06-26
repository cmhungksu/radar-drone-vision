"""2-D Regularized Complex-Log-Fourier Transform.

This is the **core algorithm** from the micro-Doppler classification
paper.  The processing chain is:

1. ``fi = FFT(xi)`` for each frame *i*.
2. ``mi = |fi|``, ``theta_i = angle(fi)`` — magnitude and phase.
3. ``Ci = regularizer(mi)`` per frame — stabilises the logarithm.
4. ``zi = log(mi + Ci + eps) + j * phase_weight * theta_i`` — complex
   log representation.
5. ``F2 = FFT(z, axis=time_axis)`` — second FFT across frames.

The output can be returned in several **feature modes** and the
regulariser can be varied for **ablation studies**.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from .fft import compute_fft

# ──────────────────────────────────────────────────────────────────────
# Public constants
# ──────────────────────────────────────────────────────────────────────

FEATURE_MODES = (
    "real_imag_concat",
    "magnitude_only",
    "magnitude_phase_concat",
    "complex_abs",
)

REGULARIZERS = (
    "none",
    "median",
    "mean",
    "percentile",
)


# ──────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────

def regularized_complex_log_fft(
    frames: np.ndarray,
    n_fft: int = 256,
    phase_weight: float = 1.0 / np.pi,
    regularizer: str = "median",
    second_fft_axis: int = 0,
    eps: float = 1e-8,
    feature_mode: str = "real_imag_concat",
    percentile: float = 75.0,
) -> np.ndarray:
    """Compute the 2-D Regularized Complex-Log-Fourier Transform.

    Parameters
    ----------
    frames : np.ndarray
        2-D array of shape ``(num_frames, frame_size)`` produced by
        :func:`~radar_drone_vision.signal.framing.frame_signal`.
        Real or complex input.
    n_fft : int
        FFT length for the *first* (per-frame) FFT.
    phase_weight : float
        Scaling factor applied to the phase before combining with the
        log-magnitude.  The paper uses ``1 / pi``.
    regularizer : str
        Regularisation strategy applied per frame to the magnitude
        vector.  One of ``"median"`` (paper default), ``"mean"``,
        ``"percentile"``, or ``"none"`` (no regularisation).
    second_fft_axis : int
        Axis along which the second FFT is computed.  ``0`` means
        across frames (slow-time), ``-1`` means across frequency bins.
    eps : float
        Small constant to prevent ``log(0)``.
    feature_mode : str
        How to convert the complex 2-D FFT output into real-valued
        features:

        * ``"real_imag_concat"`` – concatenate real and imaginary parts
          along the frequency axis → shape ``(T, 2*F)``.
        * ``"magnitude_only"`` – ``|F2|`` → shape ``(T, F)``.
        * ``"magnitude_phase_concat"`` – concatenate ``|F2|`` and
          ``angle(F2)`` → shape ``(T, 2*F)``.
        * ``"complex_abs"`` – same as ``"magnitude_only"`` (alias).
    percentile : float
        Percentile value used when ``regularizer="percentile"``.

    Returns
    -------
    features : np.ndarray (float64)
        2-D real feature matrix.  Shape depends on *feature_mode*.

    Raises
    ------
    ValueError
        On invalid *regularizer* or *feature_mode*.
    """
    frames = np.asarray(frames)
    if frames.ndim == 1:
        frames = frames[np.newaxis, :]
    if frames.ndim != 2:
        raise ValueError(f"frames must be 1-D or 2-D, got shape {frames.shape}")

    _validate_params(regularizer, feature_mode)

    # ------------------------------------------------------------------
    # Step 1: Per-frame FFT
    # ------------------------------------------------------------------
    spectrum = compute_fft(frames, n_fft=n_fft, axis=-1)  # (M, n_fft)

    # ------------------------------------------------------------------
    # Step 2: Magnitude and phase
    # ------------------------------------------------------------------
    magnitude = np.abs(spectrum)      # mi
    phase = np.angle(spectrum)        # theta_i

    # ------------------------------------------------------------------
    # Step 3: Regulariser
    # ------------------------------------------------------------------
    C = _compute_regularizer(magnitude, regularizer, percentile)

    # ------------------------------------------------------------------
    # Step 4: Complex log representation
    # ------------------------------------------------------------------
    log_mag = np.log(magnitude + C + eps)
    z = log_mag + 1j * phase_weight * phase

    # ------------------------------------------------------------------
    # Step 5: Second FFT
    # ------------------------------------------------------------------
    F2 = np.fft.fft(z, axis=second_fft_axis)

    # ------------------------------------------------------------------
    # Step 6: Feature extraction
    # ------------------------------------------------------------------
    return _extract_features(F2, feature_mode)


# ──────────────────────────────────────────────────────────────────────
# Ablation helpers
# ──────────────────────────────────────────────────────────────────────

def ablation_no_regularization(
    frames: np.ndarray, **kwargs
) -> np.ndarray:
    """Ablation: skip regularisation entirely."""
    kwargs["regularizer"] = "none"
    return regularized_complex_log_fft(frames, **kwargs)


def ablation_magnitude_only(
    frames: np.ndarray,
    n_fft: int = 256,
    regularizer: str = "median",
    eps: float = 1e-8,
    second_fft_axis: int = 0,
    percentile: float = 75.0,
    feature_mode: str = "magnitude_only",
) -> np.ndarray:
    """Ablation: use only log-magnitude (no phase information)."""
    frames = np.asarray(frames)
    if frames.ndim == 1:
        frames = frames[np.newaxis, :]

    spectrum = compute_fft(frames, n_fft=n_fft, axis=-1)
    magnitude = np.abs(spectrum)
    C = _compute_regularizer(magnitude, regularizer, percentile)
    log_mag = np.log(magnitude + C + eps)
    F2 = np.fft.fft(log_mag, axis=second_fft_axis)
    return _extract_features(F2, feature_mode)


def ablation_phase_weight_sweep(
    frames: np.ndarray,
    weights: tuple[float, ...] | list[float] | None = None,
    **kwargs,
) -> dict[float, np.ndarray]:
    """Run the full transform for several phase weights.

    Parameters
    ----------
    frames : np.ndarray
        Windowed frames.
    weights : sequence of float
        Phase weights to evaluate.  Defaults to
        ``(0.0, 0.1, 1/pi, 0.5, 1.0)``.
    **kwargs
        Forwarded to :func:`regularized_complex_log_fft`.

    Returns
    -------
    results : dict[float, np.ndarray]
        Mapping from phase weight to the corresponding feature matrix.
    """
    if weights is None:
        weights = (0.0, 0.1, 1.0 / np.pi, 0.5, 1.0)

    results: dict[float, np.ndarray] = {}
    for w in weights:
        kwargs["phase_weight"] = w
        results[w] = regularized_complex_log_fft(frames, **kwargs)
    return results


# ──────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────

def _validate_params(regularizer: str, feature_mode: str) -> None:
    if regularizer not in REGULARIZERS:
        raise ValueError(
            f"Unknown regularizer '{regularizer}'. "
            f"Choose from {REGULARIZERS}."
        )
    if feature_mode not in FEATURE_MODES:
        raise ValueError(
            f"Unknown feature_mode '{feature_mode}'. "
            f"Choose from {FEATURE_MODES}."
        )


def _compute_regularizer(
    magnitude: np.ndarray,
    method: str,
    percentile: float = 75.0,
) -> np.ndarray:
    """Return per-frame regularisation constants (broadcastable)."""
    if method == "none":
        return np.float64(0.0)

    # Compute a scalar per frame → shape (M, 1) for broadcasting.
    if method == "median":
        C = np.median(magnitude, axis=-1, keepdims=True)
    elif method == "mean":
        C = np.mean(magnitude, axis=-1, keepdims=True)
    elif method == "percentile":
        C = np.percentile(magnitude, percentile, axis=-1, keepdims=True)
    else:
        # Should not reach here after validation, but be safe.
        C = np.float64(0.0)

    return C


def _extract_features(
    F2: np.ndarray,
    mode: str,
) -> np.ndarray:
    """Convert a complex 2-D FFT result into a real feature matrix."""
    if mode == "magnitude_only" or mode == "complex_abs":
        return np.abs(F2)

    if mode == "real_imag_concat":
        return np.concatenate([F2.real, F2.imag], axis=-1)

    if mode == "magnitude_phase_concat":
        return np.concatenate([np.abs(F2), np.angle(F2)], axis=-1)

    raise ValueError(f"Unsupported feature_mode: {mode}")
