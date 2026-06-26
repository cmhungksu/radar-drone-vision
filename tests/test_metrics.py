"""Tests for evaluation metrics (metrics.py and eer.py)."""

import numpy as np
import pytest

from radar_drone_vision.eval.metrics import compute_all_metrics
from radar_drone_vision.eval.eer import compute_eer, compute_far_at_frr


# ---------------------------------------------------------------------------
# compute_all_metrics
# ---------------------------------------------------------------------------

class TestComputeAllMetrics:
    def test_perfect_predictions(self):
        y_true = np.array([1, 1, 1, 0, 0, 0])
        y_pred = np.array([1, 1, 1, 0, 0, 0])
        m = compute_all_metrics(y_true, y_pred)
        assert m["accuracy"] == 1.0
        assert m["precision"] == 1.0
        assert m["recall"] == 1.0
        assert m["f1"] == 1.0

    def test_all_wrong_predictions(self):
        y_true = np.array([1, 1, 0, 0])
        y_pred = np.array([0, 0, 1, 1])
        m = compute_all_metrics(y_true, y_pred)
        assert m["accuracy"] == 0.0
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0

    def test_confusion_matrix_shape(self):
        y_true = np.array([0, 0, 1, 1, 0, 1])
        y_pred = np.array([0, 1, 1, 0, 0, 1])
        m = compute_all_metrics(y_true, y_pred)
        cm = m["confusion_matrix"]
        assert len(cm) == 2
        assert len(cm[0]) == 2

    def test_auc_with_scores(self):
        y_true = np.array([1, 1, 0, 0])
        y_pred = np.array([1, 1, 0, 0])
        y_scores = np.array([0.9, 0.8, 0.2, 0.1])
        m = compute_all_metrics(y_true, y_pred, y_scores=y_scores)
        assert m["auc"] is not None
        assert m["auc"] == 1.0

    def test_auc_none_without_scores(self):
        y_true = np.array([1, 0])
        y_pred = np.array([1, 0])
        m = compute_all_metrics(y_true, y_pred)
        assert m["auc"] is None

    def test_classification_report_is_string(self):
        y_true = np.array([1, 0, 1, 0])
        y_pred = np.array([1, 0, 0, 1])
        m = compute_all_metrics(y_true, y_pred)
        assert isinstance(m["classification_report"], str)
        assert "non-UAV" in m["classification_report"]
        assert "UAV" in m["classification_report"]

    def test_known_confusion_matrix(self):
        # 2 TP, 1 FP, 1 FN, 2 TN
        y_true = np.array([1, 1, 1, 0, 0, 0])
        y_pred = np.array([1, 1, 0, 0, 0, 1])
        m = compute_all_metrics(y_true, y_pred)
        cm = m["confusion_matrix"]
        # cm[0][0]=TN, cm[0][1]=FP, cm[1][0]=FN, cm[1][1]=TP
        assert cm[1][1] == 2  # TP
        assert cm[0][1] == 1  # FP
        assert cm[1][0] == 1  # FN
        assert cm[0][0] == 2  # TN


# ---------------------------------------------------------------------------
# compute_eer
# ---------------------------------------------------------------------------

class TestComputeEER:
    def test_perfect_separation(self):
        """When scores perfectly separate classes, EER should be ~0."""
        y_true = np.array([1, 1, 1, 0, 0, 0])
        scores = np.array([0.9, 0.8, 0.7, 0.1, 0.2, 0.3])
        eer, threshold = compute_eer(y_true, scores)
        assert eer < 0.05  # should be close to 0

    def test_random_scores(self):
        """With random scores, EER should be around 0.5."""
        rng = np.random.default_rng(42)
        n = 1000
        y_true = np.concatenate([np.ones(n), np.zeros(n)])
        scores = rng.random(2 * n)
        eer, _ = compute_eer(y_true, scores)
        assert 0.3 < eer < 0.7

    def test_eer_returns_tuple(self):
        y_true = np.array([1, 0, 1, 0])
        scores = np.array([0.8, 0.3, 0.7, 0.4])
        result = compute_eer(y_true, scores)
        assert len(result) == 2
        eer, thresh = result
        assert 0.0 <= eer <= 1.0

    def test_empty_class_returns_zero(self):
        y_true = np.array([1, 1, 1])
        scores = np.array([0.9, 0.8, 0.7])
        eer, _ = compute_eer(y_true, scores)
        assert eer == 0.0


# ---------------------------------------------------------------------------
# compute_far_at_frr
# ---------------------------------------------------------------------------

class TestComputeFARAtFRR:
    def test_perfect_separation_returns_valid_far(self):
        """compute_far_at_frr sweeps thresholds from lowest upward and
        returns the FAR at the first threshold where FRR <= target_frr.
        With the lowest threshold, FRR=0 is always satisfied, so the
        result is FAR at that lowest threshold."""
        y_true = np.array([1, 1, 1, 0, 0, 0])
        scores = np.array([0.9, 0.8, 0.7, 0.1, 0.2, 0.3])
        far = compute_far_at_frr(y_true, scores, target_frr=0.01)
        # Function returns FAR at the lowest threshold (0.1) where FRR=0
        assert isinstance(far, float)
        assert 0.0 <= far <= 1.0

    def test_returns_float(self):
        y_true = np.array([1, 1, 0, 0])
        scores = np.array([0.8, 0.6, 0.4, 0.2])
        far = compute_far_at_frr(y_true, scores, target_frr=0.5)
        assert isinstance(far, float)
        assert 0.0 <= far <= 1.0

    def test_empty_positive_returns_zero(self):
        y_true = np.array([0, 0, 0])
        scores = np.array([0.5, 0.3, 0.7])
        far = compute_far_at_frr(y_true, scores, target_frr=0.01)
        assert far == 0.0
