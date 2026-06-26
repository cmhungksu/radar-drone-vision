"""Signal processing primitives for radar micro-Doppler analysis.

Submodules
----------
framing
    Frame a 1-D signal into overlapping windowed segments.
fft
    Basic FFT / IFFT utilities.
spectrogram
    Standard power / magnitude spectrogram.
cepstrogram
    Cepstral analysis (power cepstrum per frame).
cvd
    Cadence Velocity Diagram computation.
complex_log_fft
    2-D Regularized Complex-Log-Fourier Transform (core algorithm).
clutter_removal
    DC and clutter suppression.
normalization
    Feature normalisation strategies.
"""

from .framing import frame_signal
from .fft import compute_fft, compute_ifft, compute_rfft, compute_irfft
from .spectrogram import compute_spectrogram
from .cepstrogram import compute_cepstrogram
from .cvd import compute_cvd
from .complex_log_fft import (
    regularized_complex_log_fft,
    ablation_no_regularization,
    ablation_magnitude_only,
    ablation_phase_weight_sweep,
    FEATURE_MODES,
    REGULARIZERS,
)
from .clutter_removal import remove_clutter, subtract_mean_spectrum
from .normalization import normalize_features

__all__ = [
    # framing
    "frame_signal",
    # fft
    "compute_fft",
    "compute_ifft",
    "compute_rfft",
    "compute_irfft",
    # spectrogram
    "compute_spectrogram",
    # cepstrogram
    "compute_cepstrogram",
    # cvd
    "compute_cvd",
    # complex_log_fft
    "regularized_complex_log_fft",
    "ablation_no_regularization",
    "ablation_magnitude_only",
    "ablation_phase_weight_sweep",
    "FEATURE_MODES",
    "REGULARIZERS",
    # clutter_removal
    "remove_clutter",
    "subtract_mean_spectrum",
    # normalization
    "normalize_features",
]
