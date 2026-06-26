"""Benchmark all feature + classifier combinations for paper comparison."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from .eer import compute_eer, compute_far_at_frr

logger = logging.getLogger(__name__)


def benchmark_all_methods(
    X: np.ndarray,
    y: np.ndarray,
    configs: List[Dict[str, Any]],
    n_repeats: int = 20,
    n_folds: int = 5,
    random_state: int = 42,
) -> pd.DataFrame:
    """Run all feature + classifier combinations and collect metrics.

    Parameters
    ----------
    X : np.ndarray
        Raw feature matrix of shape ``(N, D)``.
    y : np.ndarray
        Binary labels (0 = non-UAV, 1 = UAV).
    configs : list of dict
        Each dict must contain:
        - ``"method"`` : str — display name
        - ``"feature"`` : str — feature type name
        - ``"classifier"`` : str — classifier type name
        - ``"feature_fn"`` : callable(X) -> X_feat — feature extraction
        - ``"make_clf"`` : callable() -> sklearn-like estimator
        - ``"dataset"`` : str, optional — dataset name
        - ``"notes"`` : str, optional
    n_repeats : int
        Number of random repetitions for averaging.
    n_folds : int
        Number of CV folds per repeat.
    random_state : int
        Base random seed.

    Returns
    -------
    pd.DataFrame
        Columns: Method, Feature, Classifier, Dataset, EER, FAR@FRR=1%, Notes
    """
    X = np.asarray(X)
    y = np.asarray(y)
    rows: List[Dict[str, Any]] = []

    for cfg in configs:
        method = cfg.get("method", "unknown")
        feature_name = cfg.get("feature", "")
        clf_name = cfg.get("classifier", "")
        dataset = cfg.get("dataset", "")
        notes = cfg.get("notes", "")
        feature_fn = cfg.get("feature_fn")
        make_clf = cfg.get("make_clf")

        if feature_fn is None or make_clf is None:
            logger.warning("Skipping config %s: missing feature_fn or make_clf", method)
            continue

        eer_list: List[float] = []
        far_list: List[float] = []

        for rep in range(n_repeats):
            seed = random_state + rep
            skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)

            for train_idx, test_idx in skf.split(X, y):
                X_train, X_test = X[train_idx], X[test_idx]
                y_train, y_test = y[train_idx], y[test_idx]

                try:
                    X_train_feat = feature_fn(X_train)
                    X_test_feat = feature_fn(X_test)
                except Exception:
                    logger.warning("Feature extraction failed for %s", method)
                    continue

                try:
                    clf = make_clf()
                    clf.fit(X_train_feat, y_train)

                    # Get scores for EER computation
                    if hasattr(clf, "decision_function"):
                        scores = clf.decision_function(X_test_feat)
                    elif hasattr(clf, "predict_proba"):
                        scores = clf.predict_proba(X_test_feat)[:, 1]
                    else:
                        scores = clf.predict(X_test_feat).astype(float)

                    eer, _ = compute_eer(y_test, scores)
                    far = compute_far_at_frr(y_test, scores, target_frr=0.01)
                    eer_list.append(eer)
                    far_list.append(far)
                except Exception as exc:
                    logger.warning("Classifier %s failed: %s", method, exc)

        rows.append({
            "Method": method,
            "Feature": feature_name,
            "Classifier": clf_name,
            "Dataset": dataset,
            "EER": float(np.mean(eer_list)) if eer_list else float("nan"),
            "EER_std": float(np.std(eer_list)) if eer_list else float("nan"),
            "FAR@FRR=1%": float(np.mean(far_list)) if far_list else float("nan"),
            "Notes": notes,
        })

        logger.info(
            "%s: EER=%.4f±%.4f  FAR@FRR=1%%=%.4f",
            method,
            rows[-1]["EER"],
            rows[-1]["EER_std"],
            rows[-1]["FAR@FRR=1%"],
        )

    return pd.DataFrame(rows)
