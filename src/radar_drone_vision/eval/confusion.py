"""Confusion matrix utilities."""

from __future__ import annotations

from typing import List, Optional

import numpy as np
from sklearn.metrics import confusion_matrix as sk_confusion_matrix


def compute_confusion_matrix(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    labels: Optional[List[int]] = None,
) -> np.ndarray:
    """Compute a confusion matrix.

    Parameters
    ----------
    y_true : array-like
        Ground-truth labels.
    y_pred : array-like
        Predicted labels.
    labels : list of int, optional
        Label ordering. Defaults to ``[0, 1]``.

    Returns
    -------
    np.ndarray
        Confusion matrix of shape ``(n_classes, n_classes)``.
    """
    if labels is None:
        labels = [0, 1]
    return sk_confusion_matrix(y_true, y_pred, labels=labels)


def format_confusion_matrix(
    cm: np.ndarray,
    class_names: Optional[List[str]] = None,
) -> str:
    """Return a human-readable string representation of a confusion matrix.

    Parameters
    ----------
    cm : np.ndarray
        Confusion matrix (2-D).
    class_names : list of str, optional
        Class names. Defaults to ``["non-UAV", "UAV"]``.

    Returns
    -------
    str
        Formatted table string.
    """
    if class_names is None:
        class_names = ["non-UAV", "UAV"]

    cm = np.asarray(cm)
    n = cm.shape[0]
    max_name = max(len(c) for c in class_names) if class_names else 6
    col_w = max(max_name, 8)

    header = " " * (max_name + 2) + "  ".join(f"{c:>{col_w}}" for c in class_names[:n])
    lines = [f"{'Predicted →':>{max_name + 2 + (col_w + 2) * n // 2}}", header]

    for i in range(n):
        label = class_names[i] if i < len(class_names) else str(i)
        row_vals = "  ".join(f"{cm[i, j]:>{col_w}d}" for j in range(n))
        lines.append(f"{label:>{max_name}}  {row_vals}")

    return "\n".join(lines)
