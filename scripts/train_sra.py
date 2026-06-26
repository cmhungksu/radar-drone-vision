#!/usr/bin/env python3
"""Train Subspace Reliability Analysis (SRA) classifier on radar micro-Doppler data.

Usage:
    python scripts/train_sra.py \
        --config configs/models/sra.yaml \
        --dataset zenodo77 \
        --feature proposed_regularized_complex_log_fft \
        --repeat 20 \
        --split half
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import yaml

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path for editable installs / direct execution
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

try:
    from tqdm import trange
except ImportError:
    # Minimal fallback if tqdm is not installed
    def trange(n, **kw):  # type: ignore[override]
        desc = kw.get("desc", "")
        for i in range(n):
            print(f"\r{desc} {i + 1}/{n}", end="", flush=True)
            yield i
        print()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("train_sra")


# ------------------------------------------------------------------ #
# SRA classifier (self-contained — no external dep beyond sklearn/numpy)
# ------------------------------------------------------------------ #

class SubspaceReliabilityAnalysis:
    """Binary classifier based on principal-subspace projection reliability.

    For each class, a PCA subspace of dimension *m* is learned.
    A test sample is projected onto both subspaces and the reconstruction
    error ratio (reliability score) determines the class.

    Parameters
    ----------
    m_uav : int
        Subspace dimension for the UAV (positive) class.
    m_non_uav : int
        Subspace dimension for the non-UAV (negative) class.
    ridge : float
        Ridge regularisation added to the covariance diagonal.
    """

    def __init__(self, m_uav: int = 10, m_non_uav: int = 100, ridge: float = 1e-5) -> None:
        self.m_uav = m_uav
        self.m_non_uav = m_non_uav
        self.ridge = ridge
        self._U_uav: np.ndarray | None = None
        self._U_non: np.ndarray | None = None
        self._mean_uav: np.ndarray | None = None
        self._mean_non: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SubspaceReliabilityAnalysis":
        """Fit subspaces from training data.

        Parameters
        ----------
        X : np.ndarray  (n_samples, n_features)
        y : np.ndarray  (n_samples,)  — binary labels (1=UAV, 0=non-UAV)
        """
        X_uav = X[y == 1]
        X_non = X[y == 0]
        self._U_uav, self._mean_uav = self._fit_subspace(X_uav, self.m_uav)
        self._U_non, self._mean_non = self._fit_subspace(X_non, self.m_non_uav)
        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        """Return reliability score for each sample (higher → more UAV-like)."""
        if self._U_uav is None or self._U_non is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        err_uav = self._reconstruction_error(X, self._U_uav, self._mean_uav)
        err_non = self._reconstruction_error(X, self._U_non, self._mean_non)
        # Score: lower error in UAV subspace → higher score
        return err_non - err_uav

    def predict(self, X: np.ndarray, threshold: float = 0.0) -> np.ndarray:
        """Predict binary labels."""
        scores = self.decision_function(X)
        return (scores > threshold).astype(int)

    # -- internals --

    def _fit_subspace(self, X: np.ndarray, m: int) -> Tuple[np.ndarray, np.ndarray]:
        mean = X.mean(axis=0)
        Xc = X - mean
        cov = (Xc.T @ Xc) / max(len(Xc) - 1, 1) + self.ridge * np.eye(Xc.shape[1])
        eigvals, eigvecs = np.linalg.eigh(cov)
        # Take top-m eigenvectors (eigh returns ascending order)
        m_clamped = min(m, eigvecs.shape[1])
        U = eigvecs[:, -m_clamped:]
        return U, mean

    @staticmethod
    def _reconstruction_error(X: np.ndarray, U: np.ndarray, mean: np.ndarray) -> np.ndarray:
        Xc = X - mean
        proj = Xc @ U @ U.T
        err = np.sum((Xc - proj) ** 2, axis=1)
        return err


# ------------------------------------------------------------------ #
# Evaluation helpers
# ------------------------------------------------------------------ #

def compute_eer(y_true: np.ndarray, scores: np.ndarray) -> Tuple[float, float]:
    """Compute Equal Error Rate and corresponding threshold."""
    from sklearn.metrics import roc_curve
    fpr, tpr, thresholds = roc_curve(y_true, scores)
    fnr = 1 - tpr
    # Find the point where FPR ≈ FNR
    idx = np.nanargmin(np.abs(fpr - fnr))
    eer = float((fpr[idx] + fnr[idx]) / 2)
    return eer, float(thresholds[idx])


def compute_far_at_frr(y_true: np.ndarray, scores: np.ndarray, target_frr: float = 0.01) -> float:
    """Compute FAR at a given FRR (False Rejection Rate)."""
    from sklearn.metrics import roc_curve
    fpr, tpr, _ = roc_curve(y_true, scores)
    fnr = 1 - tpr
    # Find threshold closest to target FRR
    idx = np.nanargmin(np.abs(fnr - target_frr))
    return float(fpr[idx])


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, scores: np.ndarray) -> Dict[str, float]:
    """Compute a battery of classification metrics."""
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    eer, eer_thresh = compute_eer(y_true, scores)
    far_at_1pct = compute_far_at_frr(y_true, scores, target_frr=0.01)

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "eer": eer,
        "eer_threshold": eer_thresh,
        "far_at_frr_1pct": far_at_1pct,
    }


# ------------------------------------------------------------------ #
# Main logic
# ------------------------------------------------------------------ #

def load_config(config_path: str) -> Dict[str, Any]:
    """Load YAML config, falling back to defaults if file is missing."""
    p = Path(config_path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    logger.warning("Config file %s not found — using defaults.", config_path)
    return {}


def load_dataset(dataset_name: str, project_root: Path):
    """Load the specified dataset, returning the dataset object."""
    if dataset_name in ("zenodo77", "zenodo_77ghz_fmcw"):
        from radar_drone_vision.datasets.zenodo77 import Zenodo77Dataset

        data_dir = project_root / "data" / "processed" / "zenodo_77ghz_fmcw"
        if not data_dir.exists():
            data_dir = project_root / "data" / "raw" / "zenodo_77ghz_fmcw"
        if not data_dir.exists():
            print(
                f"\n[ERROR] Dataset directory not found: {data_dir}\n"
                "  Please download the dataset first:\n"
                "    python scripts/download_zenodo.py --out data/raw/zenodo_77ghz_fmcw\n"
            )
            sys.exit(1)
        return Zenodo77Dataset(data_dir)
    else:
        print(f"\n[ERROR] Unknown dataset: '{dataset_name}'")
        print("  Supported datasets: zenodo77")
        sys.exit(1)


def extract_features_from_dataset(
    dataset, feature_type: str, config: Dict[str, Any]
) -> Tuple[np.ndarray, np.ndarray]:
    """Extract features from all samples in the dataset."""
    from radar_drone_vision.features.extractors import extract_features

    logger.info("Extracting features (type=%s) from %d samples ...", feature_type, len(dataset))
    signals = [dataset[i].signal for i in range(len(dataset))]
    labels = np.array([dataset[i].label_binary for i in range(len(dataset))])

    feat_cfg = {}
    if "signal" in config:
        feat_cfg.update(config["signal"])

    X = extract_features(signals, feature_type, feat_cfg)
    logger.info("Feature matrix shape: %s", X.shape)
    return X, labels


def run_training(args: argparse.Namespace) -> None:
    """Execute the SRA training loop."""
    config = load_config(args.config)
    dataset = load_dataset(args.dataset, _PROJECT_ROOT)

    # Merge SRA params from config
    sra_cfg = config.get("sra", {})
    m_uav = sra_cfg.get("m_uav", 10)
    m_non_uav = sra_cfg.get("m_non_uav", 100)
    ridge = sra_cfg.get("ridge", 1e-5)

    feature_type = args.feature or config.get("feature", {}).get(
        "type", "proposed_regularized_complex_log_fft"
    )

    # Extract features
    X, y = extract_features_from_dataset(dataset, feature_type, config)

    # Repeated random splits
    n_repeats = args.repeat
    split_method = args.split or config.get("training", {}).get("split", "half")
    base_seed = args.seed

    test_ratio = 0.5 if split_method == "half" else 0.2

    all_metrics: List[Dict[str, float]] = []
    best_eer = float("inf")
    best_model: SubspaceReliabilityAnalysis | None = None

    t0 = time.time()
    for rep in trange(n_repeats, desc="SRA repeats"):
        seed = base_seed + rep
        train_idx, test_idx = dataset.train_test_split(
            method=split_method, test_ratio=test_ratio, seed=seed, stratify=True
        )

        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        sra = SubspaceReliabilityAnalysis(m_uav=m_uav, m_non_uav=m_non_uav, ridge=ridge)
        sra.fit(X_train, y_train)

        scores = sra.decision_function(X_test)
        y_pred = sra.predict(X_test)
        metrics = compute_metrics(y_test, y_pred, scores)
        all_metrics.append(metrics)

        if metrics["eer"] < best_eer:
            best_eer = metrics["eer"]
            best_model = sra

    elapsed = time.time() - t0

    # Average metrics across repeats
    avg_metrics: Dict[str, float] = {}
    std_metrics: Dict[str, float] = {}
    for key in all_metrics[0]:
        vals = [m[key] for m in all_metrics]
        avg_metrics[key] = float(np.mean(vals))
        std_metrics[key] = float(np.std(vals))

    # Print summary table
    print("\n" + "=" * 70)
    print(f"  SRA Training Summary  ({n_repeats} repeats, split={split_method})")
    print(f"  Feature: {feature_type}")
    print(f"  Subspace dims: m_uav={m_uav}, m_non_uav={m_non_uav}, ridge={ridge}")
    print(f"  Time: {elapsed:.1f}s")
    print("=" * 70)
    print(f"  {'Metric':<20s} {'Mean':>10s} {'Std':>10s}")
    print("-" * 42)
    for key in ["accuracy", "precision", "recall", "f1", "eer", "far_at_frr_1pct"]:
        print(f"  {key:<20s} {avg_metrics[key]:>10.4f} {std_metrics[key]:>10.4f}")
    print("=" * 70)

    # Save best model
    if best_model is not None:
        import joblib

        models_dir = _PROJECT_ROOT / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        out_path = models_dir / "sra_model.joblib"
        joblib.dump(
            {
                "model": best_model,
                "feature_type": feature_type,
                "config": config,
                "avg_metrics": avg_metrics,
                "std_metrics": std_metrics,
                "n_repeats": n_repeats,
            },
            out_path,
        )
        print(f"\n  Best model saved to: {out_path}")
        print(f"  Best EER: {best_eer:.4f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train SRA classifier for UAV micro-Doppler detection."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/models/sra.yaml",
        help="Path to SRA config YAML (default: configs/models/sra.yaml)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="zenodo77",
        help="Dataset name (default: zenodo77)",
    )
    parser.add_argument(
        "--feature",
        type=str,
        default=None,
        help="Feature type override (default: from config)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=20,
        help="Number of random train/test splits (default: 20)",
    )
    parser.add_argument(
        "--split",
        type=str,
        default=None,
        choices=["half", "ratio"],
        help="Split strategy (default: from config or 'half')",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base random seed (default: 42)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    run_training(parse_args())
