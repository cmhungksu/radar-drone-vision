"""Aggregate classification metrics for radar UAV detection."""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def compute_all_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_scores: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Compute a full set of binary classification metrics.

    Parameters
    ----------
    y_true : array-like
        Ground-truth labels (0 = non-UAV, 1 = UAV).
    y_pred : array-like
        Predicted labels.
    y_scores : array-like, optional
        Continuous scores or probabilities for the positive class (UAV).
        Required for AUC.

    Returns
    -------
    dict
        Keys: accuracy, precision, recall, f1, auc (or None),
        confusion_matrix, classification_report.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    metrics: Dict[str, Any] = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "auc": None,
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "classification_report": classification_report(
            y_true, y_pred, target_names=["non-UAV", "UAV"], zero_division=0
        ),
    }

    if y_scores is not None:
        y_scores = np.asarray(y_scores)
        try:
            metrics["auc"] = float(roc_auc_score(y_true, y_scores))
        except ValueError:
            metrics["auc"] = None

    return metrics
