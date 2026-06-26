"""Tests for the 2-D Regularized Complex-Log-Fourier Transform."""

import numpy as np
import pytest

from radar_drone_vision.signal.complex_log_fft import (
    FEATURE_MODES,
    REGULARIZERS,
    ablation_magnitude_only,
    ablation_no_regularization,
    ablation_phase_weight_sweep,
    regularized_complex_log_fft,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sine_frames():
    """Return a 2-D array of framed sine-wave data (real-valued)."""
    rng = np.random.default_rng(0)
    n_frames, frame_size = 16, 256
    t = np.linspace(0, 1, frame_size, endpoint=False)
    frames = np.zeros((n_frames, frame_size))
    for i in range(n_frames):
        freq = 10 + i * 2
        frames[i] = np.sin(2 * np.pi * freq * t) + 0.1 * rng.standard_normal(frame_size)
    return frames


@pytest.fixture
def complex_frames():
    """Return a 2-D array of framed complex IQ data."""
    rng = np.random.default_rng(1)
    n_frames, frame_size = 12, 128
    t = np.linspace(0, 1, frame_size, endpoint=False)
    frames = np.zeros((n_frames, frame_size), dtype=np.complex128)
    for i in range(n_frames):
        freq = 5 + i
        frames[i] = np.exp(1j * 2 * np.pi * freq * t) + 0.05 * (
            rng.standard_normal(frame_size) + 1j * rng.standard_normal(frame_size)
        )
    return frames


# ---------------------------------------------------------------------------
# Shape and basic properties
# ---------------------------------------------------------------------------

class TestOutputShape:
    """Verify output shapes for each feature_mode."""

    def test_real_imag_concat_shape(self, sine_frames):
        n_fft = 256
        out = regularized_complex_log_fft(sine_frames, n_fft=n_fft, feature_mode="real_imag_concat")
        assert out.ndim == 2
        assert out.shape == (sine_frames.shape[0], 2 * n_fft)

    def test_magnitude_only_shape(self, sine_frames):
        n_fft = 256
        out = regularized_complex_log_fft(sine_frames, n_fft=n_fft, feature_mode="magnitude_only")
        assert out.shape == (sine_frames.shape[0], n_fft)

    def test_magnitude_phase_concat_shape(self, sine_frames):
        n_fft = 256
        out = regularized_complex_log_fft(sine_frames, n_fft=n_fft, feature_mode="magnitude_phase_concat")
        assert out.shape == (sine_frames.shape[0], 2 * n_fft)

    def test_complex_abs_shape(self, sine_frames):
        n_fft = 128
        out = regularized_complex_log_fft(sine_frames, n_fft=n_fft, feature_mode="complex_abs")
        assert out.shape == (sine_frames.shape[0], n_fft)

    def test_1d_input_promoted(self):
        """A 1-D input should be treated as a single frame."""
        signal = np.sin(np.linspace(0, 2 * np.pi, 256))
        out = regularized_complex_log_fft(signal, n_fft=256, feature_mode="magnitude_only")
        assert out.ndim == 2
        assert out.shape[0] == 1


# ---------------------------------------------------------------------------
# Regularizer variants
# ---------------------------------------------------------------------------

class TestRegularizers:
    """Each regularizer should produce finite output without NaN/Inf."""

    @pytest.mark.parametrize("reg", REGULARIZERS)
    def test_no_nan_inf(self, sine_frames, reg):
        out = regularized_complex_log_fft(sine_frames, regularizer=reg)
        assert np.all(np.isfinite(out)), f"Non-finite values with regularizer={reg}"

    def test_median_and_mean_differ(self, sine_frames):
        out_med = regularized_complex_log_fft(sine_frames, regularizer="median")
        out_mean = regularized_complex_log_fft(sine_frames, regularizer="mean")
        # They should generally differ (unless the signal is perfectly symmetric)
        assert not np.allclose(out_med, out_mean)

    def test_none_regularizer_still_finite(self, sine_frames):
        out = regularized_complex_log_fft(sine_frames, regularizer="none")
        assert np.all(np.isfinite(out))

    def test_percentile_regularizer(self, sine_frames):
        out = regularized_complex_log_fft(sine_frames, regularizer="percentile", percentile=90.0)
        assert np.all(np.isfinite(out))


# ---------------------------------------------------------------------------
# Feature mode variants
# ---------------------------------------------------------------------------

class TestFeatureModes:
    @pytest.mark.parametrize("mode", FEATURE_MODES)
    def test_all_modes_produce_real_output(self, sine_frames, mode):
        out = regularized_complex_log_fft(sine_frames, feature_mode=mode)
        assert out.dtype in (np.float64, np.float32, float)

    @pytest.mark.parametrize("mode", FEATURE_MODES)
    def test_no_nan_inf_all_modes(self, sine_frames, mode):
        out = regularized_complex_log_fft(sine_frames, feature_mode=mode)
        assert np.all(np.isfinite(out))


# ---------------------------------------------------------------------------
# Phase weight
# ---------------------------------------------------------------------------

class TestPhaseWeight:
    def test_zero_phase_weight_ignores_phase(self, sine_frames):
        """With phase_weight=0 the imaginary part of z is zero, so the result
        should differ from the default (1/pi)."""
        out_zero = regularized_complex_log_fft(sine_frames, phase_weight=0.0)
        out_default = regularized_complex_log_fft(sine_frames, phase_weight=1.0 / np.pi)
        assert not np.allclose(out_zero, out_default)

    def test_large_phase_weight(self, sine_frames):
        out = regularized_complex_log_fft(sine_frames, phase_weight=10.0)
        assert np.all(np.isfinite(out))


# ---------------------------------------------------------------------------
# Complex input
# ---------------------------------------------------------------------------

class TestComplexInput:
    def test_complex_input_produces_finite_output(self, complex_frames):
        out = regularized_complex_log_fft(complex_frames)
        assert np.all(np.isfinite(out))

    @pytest.mark.parametrize("mode", FEATURE_MODES)
    def test_complex_input_all_modes(self, complex_frames, mode):
        out = regularized_complex_log_fft(complex_frames, feature_mode=mode)
        assert np.all(np.isfinite(out))
        assert out.ndim == 2


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestValidation:
    def test_invalid_regularizer_raises(self, sine_frames):
        with pytest.raises(ValueError, match="Unknown regularizer"):
            regularized_complex_log_fft(sine_frames, regularizer="bogus")

    def test_invalid_feature_mode_raises(self, sine_frames):
        with pytest.raises(ValueError, match="Unknown feature_mode"):
            regularized_complex_log_fft(sine_frames, feature_mode="bogus")

    def test_3d_input_raises(self):
        with pytest.raises(ValueError, match="must be 1-D or 2-D"):
            regularized_complex_log_fft(np.zeros((2, 3, 4)))


# ---------------------------------------------------------------------------
# Ablation helpers
# ---------------------------------------------------------------------------

class TestAblations:
    def test_ablation_no_regularization(self, sine_frames):
        out = ablation_no_regularization(sine_frames)
        expected = regularized_complex_log_fft(sine_frames, regularizer="none")
        np.testing.assert_allclose(out, expected)

    def test_ablation_magnitude_only(self, sine_frames):
        out = ablation_magnitude_only(sine_frames)
        assert np.all(np.isfinite(out))

    def test_ablation_phase_weight_sweep(self, sine_frames):
        results = ablation_phase_weight_sweep(sine_frames)
        assert isinstance(results, dict)
        assert len(results) == 5  # default 5 weights
        for w, feat in results.items():
            assert isinstance(w, float)
            assert np.all(np.isfinite(feat))
