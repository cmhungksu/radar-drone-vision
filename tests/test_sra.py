"""Tests for SubspaceReliabilityAnalysis."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from radar_drone_vision.classical.sra import SubspaceReliabilityAnalysis


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_2class():
    """Return well-separated 2-class synthetic data (d=20)."""
    rng = np.random.default_rng(42)
    d = 20
    n_per_class = 80

    # UAV cluster centred at +2, non-UAV at -2
    X_uav = rng.standard_normal((n_per_class, d)) + 2.0
    X_non = rng.standard_normal((n_per_class, d)) - 2.0

    X = np.vstack([X_uav, X_non])
    y = np.concatenate([np.ones(n_per_class), np.zeros(n_per_class)])
    return X, y


@pytest.fixture
def fitted_model(synthetic_2class):
    X, y = synthetic_2class
    model = SubspaceReliabilityAnalysis(m_uav=5, m_non_uav=10, ridge=1e-4)
    model.fit(X, y)
    return model, X, y


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------

class TestFit:
    def test_eigenvector_shapes(self, fitted_model):
        model, X, _ = fitted_model
        d = X.shape[1]
        assert model.phi1_.shape == (d, 5)   # m_uav=5
        assert model.phi2_.shape == (d, 10)  # m_non_uav=10

    def test_mean_shapes(self, fitted_model):
        model, X, _ = fitted_model
        d = X.shape[1]
        assert model.mu1_.shape == (d,)
        assert model.mu2_.shape == (d,)

    def test_covariance_shapes(self, fitted_model):
        model, X, _ = fitted_model
        d = X.shape[1]
        assert model.cov1_.shape == (d, d)
        assert model.cov2_.shape == (d, d)
        assert model.cov_b_.shape == (d, d)

    def test_eigenvalues_descending(self, fitted_model):
        model, _, _ = fitted_model
        # eigenvalues should be sorted in descending order
        assert np.all(np.diff(model.eigenvalues1_) <= 1e-12)
        assert np.all(np.diff(model.eigenvalues2_) <= 1e-12)

    def test_sub_cov_inv_shapes(self, fitted_model):
        model, _, _ = fitted_model
        assert model.sub_cov_inv1_.shape == (5, 5)
        assert model.sub_cov_inv2_.shape == (10, 10)


# ---------------------------------------------------------------------------
# Score & Predict
# ---------------------------------------------------------------------------

class TestScorePredict:
    def test_score_ratio_returns_valid_shape(self, fitted_model):
        model, X, _ = fitted_model
        scores = model.score_ratio(X)
        assert scores.shape == (X.shape[0],)

    def test_score_ratio_finite(self, fitted_model):
        model, X, _ = fitted_model
        scores = model.score_ratio(X)
        assert np.all(np.isfinite(scores))

    def test_uav_scores_lower_on_average(self, fitted_model):
        """UAV samples should have lower g1/g2 ratio than non-UAV."""
        model, X, y = fitted_model
        scores = model.score_ratio(X)
        uav_mean = scores[y == 1].mean()
        non_mean = scores[y == 0].mean()
        assert uav_mean < non_mean

    def test_predict_returns_binary(self, fitted_model):
        model, X, _ = fitted_model
        preds = model.predict(X)
        assert set(np.unique(preds)).issubset({0, 1})

    def test_predict_threshold_effect(self, fitted_model):
        model, X, _ = fitted_model
        # Very high threshold => everything is UAV
        preds_high = model.predict(X, threshold=1e6)
        assert np.all(preds_high == 1)
        # Very low threshold => nothing is UAV
        preds_low = model.predict(X, threshold=-1e6)
        assert np.all(preds_low == 0)

    def test_predict_single_sample(self, fitted_model):
        model, X, _ = fitted_model
        pred = model.predict(X[0:1])
        assert pred.shape == (1,)

    def test_predict_1d_input(self, fitted_model):
        model, X, _ = fitted_model
        pred = model.predict(X[0])
        assert pred.shape == (1,)


# ---------------------------------------------------------------------------
# Save / Load roundtrip
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_load_roundtrip(self, fitted_model):
        model, X, _ = fitted_model
        scores_before = model.score_ratio(X)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "sra_model.joblib")
            model.save(path)

            loaded = SubspaceReliabilityAnalysis()
            loaded.load(path)

            scores_after = loaded.score_ratio(X)
            np.testing.assert_allclose(scores_before, scores_after)

    def test_load_preserves_config(self, fitted_model):
        model, _, _ = fitted_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "model.joblib")
            model.save(path)

            loaded = SubspaceReliabilityAnalysis()
            loaded.load(path)

            assert loaded.m_uav == model.m_uav
            assert loaded.m_non_uav == model.m_non_uav
            assert loaded.ridge == model.ridge


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_very_few_samples(self):
        """Fit should work with as few as 2 samples per class."""
        rng = np.random.default_rng(99)
        d = 5
        X = np.vstack([rng.standard_normal((2, d)) + 3, rng.standard_normal((2, d)) - 3])
        y = np.array([1, 1, 0, 0])
        model = SubspaceReliabilityAnalysis(m_uav=2, m_non_uav=2, ridge=1e-3)
        model.fit(X, y)
        scores = model.score_ratio(X)
        assert scores.shape == (4,)
        assert np.all(np.isfinite(scores))

    def test_equal_class_means(self):
        """When classes overlap completely, model should still fit without error."""
        rng = np.random.default_rng(7)
        d = 10
        X = rng.standard_normal((40, d))
        y = np.array([1] * 20 + [0] * 20)
        model = SubspaceReliabilityAnalysis(m_uav=3, m_non_uav=3, ridge=1e-3)
        model.fit(X, y)
        scores = model.score_ratio(X)
        assert np.all(np.isfinite(scores))

    def test_single_class_raises(self):
        """Fit must raise if only one class is present."""
        X = np.random.default_rng(0).standard_normal((10, 5))
        y = np.ones(10)
        model = SubspaceReliabilityAnalysis()
        with pytest.raises(ValueError, match="Both classes"):
            model.fit(X, y)

    def test_unfitted_predict_raises(self):
        model = SubspaceReliabilityAnalysis()
        with pytest.raises(RuntimeError, match="not been fitted"):
            model.score_ratio(np.zeros((3, 5)))

    def test_ridge_prevents_singular(self):
        """With perfectly collinear features, ridge should prevent failure."""
        d = 10
        X = np.zeros((20, d))
        X[:10, 0] = 1.0  # only first feature varies
        X[10:, 0] = -1.0
        y = np.array([1] * 10 + [0] * 10)
        model = SubspaceReliabilityAnalysis(m_uav=3, m_non_uav=3, ridge=1e-2)
        model.fit(X, y)
        scores = model.score_ratio(X)
        assert np.all(np.isfinite(scores))

    def test_m_larger_than_d_clipped(self):
        """m_uav > d should be clipped to d automatically."""
        rng = np.random.default_rng(5)
        d = 4
        X = np.vstack([rng.standard_normal((10, d)) + 2, rng.standard_normal((10, d)) - 2])
        y = np.array([1] * 10 + [0] * 10)
        model = SubspaceReliabilityAnalysis(m_uav=100, m_non_uav=100, ridge=1e-3)
        model.fit(X, y)
        assert model.phi1_.shape[1] == d
        assert model.phi2_.shape[1] == d
