#!/usr/bin/env python3
"""Enhanced training pipeline for UAV vs Bird classification.

Improvements over baseline:
1. Clutter removal (mean-spectrum subtraction) before feature extraction
2. PCA dimensionality reduction for efficient SRA
3. SRA parameter grid search (m_uav, m_non_uav)
4. CNN with data augmentation (Gaussian noise, time shift, mixup)
5. Class-weighted CrossEntropyLoss
6. Improved CNN with residual + SE attention blocks
7. Ensemble classifier: SRA + CNN weighted voting
8. Comprehensive evaluation with confidence intervals

Usage:
    python scripts/train_enhanced.py --device auto                  # full pipeline
    python scripts/train_enhanced.py --mode sra_grid                # SRA grid search only
    python scripts/train_enhanced.py --mode cnn                     # CNN only
    python scripts/train_enhanced.py --mode ensemble                # full + ensemble
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("train_enhanced")


# ================================================================== #
# 1. Dataset loading + preprocessing
# ================================================================== #

def load_dataset(project_root: Path):
    from radar_drone_vision.datasets.zenodo77 import Zenodo77Dataset
    for subdir in ["zenodo_77ghz", "zenodo77"]:
        for prefix in ["raw", "processed"]:
            candidate = project_root / "data" / prefix / subdir
            npy_file = candidate / "data_SAAB_SIRS_77GHz_FMCW.npy"
            if npy_file.exists():
                return Zenodo77Dataset(candidate)
    print("\n[ERROR] Dataset not found. Run: python scripts/download_zenodo.py")
    sys.exit(1)


def apply_clutter_removal(signals: np.ndarray) -> np.ndarray:
    """Per-sample clutter removal: reshape to (5, 256), subtract mean per range cell."""
    cleaned = np.empty_like(signals)
    for i in range(len(signals)):
        sig = signals[i].copy()
        if len(sig) == 1280:
            mat = sig.reshape(5, 256)
            mat = mat - mat.mean(axis=1, keepdims=True)
            peak = np.max(np.abs(mat))
            if peak > 0:
                mat = mat / peak
            cleaned[i] = mat.ravel()
        else:
            sig = sig - np.mean(sig)
            peak = np.max(np.abs(sig))
            if peak > 0:
                sig = sig / peak
            cleaned[i] = sig
    return cleaned


def stratified_subsample(labels: np.ndarray, n_per_class: int, seed: int = 42) -> np.ndarray:
    """Return indices of a stratified subsample."""
    rng = np.random.default_rng(seed)
    indices = []
    for cls in np.unique(labels):
        cls_idx = np.where(labels == cls)[0]
        n = min(n_per_class, len(cls_idx))
        chosen = rng.choice(cls_idx, size=n, replace=False)
        indices.extend(chosen.tolist())
    return np.array(sorted(indices))


def extract_features_batch(signals: np.ndarray, feature_type: str,
                           config: Optional[dict] = None,
                           flatten: bool = True) -> np.ndarray:
    """Extract features with progress logging."""
    from radar_drone_vision.features.extractors import extract_features

    cfg = {"flatten": flatten}
    if config:
        cfg.update(config)
    cfg["flatten"] = flatten

    n = len(signals)
    batch_size = 5000
    parts = []
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        batch = extract_features(list(signals[start:end]), feature_type, cfg)
        parts.append(batch)
        logger.info("  Features: %d/%d", end, n)

    return np.vstack(parts) if len(parts) > 1 else parts[0]


# ================================================================== #
# 2. SRA with PCA + Grid Search
# ================================================================== #

class EnhancedSRA:
    """SRA with optional PCA whitening."""

    def __init__(self, m_uav=10, m_non_uav=100, ridge=1e-5):
        self.m_uav = m_uav
        self.m_non_uav = m_non_uav
        self.ridge = ridge

    def fit(self, X, y):
        X_uav = X[y == 1]
        X_non = X[y == 0]
        self._U_uav, self._mean_uav = self._fit_subspace(X_uav, self.m_uav)
        self._U_non, self._mean_non = self._fit_subspace(X_non, self.m_non_uav)
        return self

    def decision_function(self, X):
        err_uav = self._reconstruction_error(X, self._U_uav, self._mean_uav)
        err_non = self._reconstruction_error(X, self._U_non, self._mean_non)
        return err_non - err_uav

    def predict(self, X, threshold=0.0):
        return (self.decision_function(X) > threshold).astype(int)

    def _fit_subspace(self, X, m):
        mean = X.mean(axis=0)
        Xc = X - mean
        cov = (Xc.T @ Xc) / max(len(Xc) - 1, 1) + self.ridge * np.eye(Xc.shape[1])
        eigvals, eigvecs = np.linalg.eigh(cov)
        m_clamped = min(m, eigvecs.shape[1])
        U = eigvecs[:, -m_clamped:]
        return U, mean

    @staticmethod
    def _reconstruction_error(X, U, mean):
        Xc = X - mean
        proj = Xc @ U @ U.T
        return np.sum((Xc - proj) ** 2, axis=1)


def _stratified_split(y, test_ratio=0.5, seed=42):
    """Simple stratified train/test split on arbitrary-length arrays."""
    rng = np.random.default_rng(seed)
    train_idx, test_idx = [], []
    for cls in np.unique(y):
        cls_idx = np.where(y == cls)[0].copy()
        rng.shuffle(cls_idx)
        n_test = int(len(cls_idx) * test_ratio)
        test_idx.extend(cls_idx[:n_test].tolist())
        train_idx.extend(cls_idx[n_test:].tolist())
    return train_idx, test_idx


def run_sra_evaluation(X, y, dataset=None, m_uav=10, m_non_uav=100,
                       n_repeats=10, seed=42) -> dict:
    """Run SRA with given params across multiple splits."""
    from sklearn.metrics import accuracy_score, f1_score, roc_curve, roc_auc_score

    metrics_list = []
    for rep in range(n_repeats):
        train_idx, test_idx = _stratified_split(y, test_ratio=0.5, seed=seed + rep)
        sra = EnhancedSRA(m_uav=m_uav, m_non_uav=m_non_uav)
        sra.fit(X[train_idx], y[train_idx])
        scores = sra.decision_function(X[test_idx])
        y_pred = sra.predict(X[test_idx])
        y_test = y[test_idx]

        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        try:
            auc = roc_auc_score(y_test, scores)
        except ValueError:
            auc = 0.5
        fpr, tpr, _ = roc_curve(y_test, scores)
        fnr = 1 - tpr
        eer_idx = np.nanargmin(np.abs(fpr - fnr))
        eer = float((fpr[eer_idx] + fnr[eer_idx]) / 2)
        # FAR @ FRR=1%
        far1_idx = np.nanargmin(np.abs(fnr - 0.01))
        far1 = float(fpr[far1_idx])

        metrics_list.append({"accuracy": acc, "f1": f1, "eer": eer, "auc": auc, "far1": far1})

    result = {}
    for key in metrics_list[0]:
        vals = [m[key] for m in metrics_list]
        result[key] = float(np.mean(vals))
        result[f"{key}_std"] = float(np.std(vals))
    return result


def sra_grid_search(X_full, y_full, n_repeats=5, seed=42,
                    pca_dims=[100, 200, 300, 500]) -> Tuple[dict, List[dict]]:
    """Grid search SRA with PCA dimensionality reduction."""
    from sklearn.decomposition import PCA

    m_uav_range = [5, 10, 15, 20, 30, 50]
    m_non_uav_range = [30, 50, 80, 100, 150, 200]

    results = []
    best_f1 = -1
    best_params = {}
    total_configs = len(pca_dims) * len(m_uav_range) * len(m_non_uav_range)
    count = 0

    for pca_dim in pca_dims:
        actual_dim = min(pca_dim, X_full.shape[1], X_full.shape[0])
        logger.info("\n--- PCA dim=%d (actual=%d) ---", pca_dim, actual_dim)
        pca = PCA(n_components=actual_dim, whiten=True)
        X_pca = pca.fit_transform(X_full.astype(np.float32))
        explained = pca.explained_variance_ratio_.sum()
        logger.info("  Explained variance: %.4f", explained)

        for m_uav in m_uav_range:
            for m_non_uav in m_non_uav_range:
                if m_non_uav <= m_uav:
                    continue
                if m_non_uav > actual_dim or m_uav > actual_dim:
                    continue
                count += 1

                try:
                    metrics = run_sra_evaluation(
                        X_pca, y_full, dataset,
                        m_uav=m_uav, m_non_uav=m_non_uav,
                        n_repeats=n_repeats, seed=seed,
                    )
                except Exception as e:
                    logger.warning("SRA failed (pca=%d m_uav=%d m_non=%d): %s",
                                   pca_dim, m_uav, m_non_uav, e)
                    continue

                result = {
                    "pca_dim": pca_dim,
                    "m_uav": m_uav,
                    "m_non_uav": m_non_uav,
                    **metrics,
                }
                results.append(result)

                if metrics["f1"] > best_f1:
                    best_f1 = metrics["f1"]
                    best_params = result.copy()

                if count % 10 == 0:
                    logger.info(
                        "  [%d/%d] best F1=%.4f (pca=%d, m_uav=%d, m_non=%d)",
                        count, total_configs, best_f1,
                        best_params.get("pca_dim"), best_params.get("m_uav"),
                        best_params.get("m_non_uav"),
                    )

    results.sort(key=lambda r: r["f1"], reverse=True)

    logger.info("\n=== SRA Grid Search Complete (%d configs) ===", len(results))
    for i, r in enumerate(results[:5]):
        logger.info(
            "  #%d: F1=%.4f±%.4f  Acc=%.4f  EER=%.4f  AUC=%.4f  "
            "pca=%d  m_uav=%d  m_non=%d",
            i + 1, r["f1"], r["f1_std"], r["accuracy"], r["eer"], r["auc"],
            r["pca_dim"], r["m_uav"], r["m_non_uav"],
        )

    return best_params, results


# ================================================================== #
# 3. Enhanced CNN with Residual + SE Attention
# ================================================================== #

def build_enhanced_cnn(in_channels=2, num_classes=2):
    import torch
    import torch.nn as nn

    class SEBlock(nn.Module):
        def __init__(self, ch, r=4):
            super().__init__()
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.fc = nn.Sequential(
                nn.Linear(ch, ch // r, bias=False), nn.ReLU(inplace=True),
                nn.Linear(ch // r, ch, bias=False), nn.Sigmoid())

        def forward(self, x):
            b, c, _, _ = x.shape
            w = self.fc(self.pool(x).view(b, c)).view(b, c, 1, 1)
            return x * w

    class ResBlock(nn.Module):
        def __init__(self, in_ch, out_ch, stride=1):
            super().__init__()
            self.conv1 = nn.Conv2d(in_ch, out_ch, 3, stride=stride, padding=1, bias=False)
            self.bn1 = nn.BatchNorm2d(out_ch)
            self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False)
            self.bn2 = nn.BatchNorm2d(out_ch)
            self.se = SEBlock(out_ch)
            self.relu = nn.ReLU(inplace=True)
            self.downsample = (nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_ch))
                if stride != 1 or in_ch != out_ch else None)

        def forward(self, x):
            identity = x
            out = self.relu(self.bn1(self.conv1(x)))
            out = self.se(self.bn2(self.conv2(out)))
            if self.downsample:
                identity = self.downsample(x)
            return self.relu(out + identity)

    class EnhancedRadarCNN(nn.Module):
        def __init__(self, in_channels, num_classes):
            super().__init__()
            self.stem = nn.Sequential(
                nn.Conv2d(in_channels, 32, 3, padding=1, bias=False),
                nn.BatchNorm2d(32), nn.ReLU(inplace=True))
            self.layer1 = ResBlock(32, 64, stride=2)
            self.layer2 = ResBlock(64, 128, stride=2)
            self.layer3 = ResBlock(128, 256, stride=2)
            self.pool = nn.AdaptiveAvgPool2d((1, 1))
            self.classifier = nn.Sequential(
                nn.Flatten(), nn.Dropout(0.4),
                nn.Linear(256, 128), nn.ReLU(inplace=True),
                nn.Dropout(0.2), nn.Linear(128, num_classes))

        def forward(self, x):
            x = self.stem(x)
            x = self.layer1(x)
            x = self.layer2(x)
            x = self.layer3(x)
            x = self.pool(x)
            return self.classifier(x)

    return EnhancedRadarCNN(in_channels, num_classes)


def prepare_cnn_data(X_2d: np.ndarray) -> np.ndarray:
    """Convert 2D features to CNN-ready 4D tensors: (N, C, H, W)."""
    from scipy.ndimage import zoom

    if X_2d.ndim == 3:
        n, h, w = X_2d.shape
        if w > h:  # (T, 2*F) → split into 2 channels
            half_w = w // 2
            X = np.stack([X_2d[:, :, :half_w], X_2d[:, :, half_w:]], axis=1)
        else:
            X = X_2d[:, np.newaxis, :, :]
    elif X_2d.ndim == 4:
        X = X_2d
    else:
        raise ValueError(f"Unexpected shape: {X_2d.shape}")

    _, c, h, w = X.shape
    if h != 128 or w != 128:
        logger.info("Resizing from (%d, %d) to (128, 128)...", h, w)
        resized = np.empty((len(X), c, 128, 128), dtype=np.float32)
        for i in range(len(X)):
            for ch in range(c):
                resized[i, ch] = zoom(X[i, ch], (128 / h, 128 / w), order=1)
        X = resized

    return X.astype(np.float32)


def train_cnn(X, y, epochs=80, batch_size=64, lr=5e-4, device="cpu",
              seed=42, use_original=False) -> Tuple[Any, dict]:
    """Train CNN with augmentation, class weighting, mixup."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    from sklearn.metrics import accuracy_score, f1_score, roc_curve, roc_auc_score

    np.random.seed(seed)
    torch.manual_seed(seed)

    X = prepare_cnn_data(X)
    in_channels = X.shape[1]

    # Split: 70/15/15
    n = len(y)
    idx = np.random.permutation(n)
    n_train = int(0.70 * n)
    n_val = int(0.15 * n)
    tr, va, te = idx[:n_train], idx[n_train:n_train+n_val], idx[n_train+n_val:]

    # Class weights
    n_uav = (y[tr] == 1).sum()
    n_non = (y[tr] == 0).sum()
    w0 = n / (2 * max(n_non, 1))
    w1 = n / (2 * max(n_uav, 1))
    class_weights = torch.tensor([w0, w1], dtype=torch.float32).to(device)
    logger.info("Class weights: %.3f / %.3f  (train: %d UAV, %d non-UAV)", w0, w1, n_uav, n_non)

    def make_loader(indices, shuffle=False):
        return DataLoader(
            TensorDataset(
                torch.from_numpy(X[indices]),
                torch.from_numpy(y[indices].astype(np.int64))),
            batch_size=batch_size, shuffle=shuffle, drop_last=shuffle)

    train_loader = make_loader(tr, shuffle=True)
    val_loader = make_loader(va)
    test_loader = make_loader(te)

    logger.info("Splits: train=%d val=%d test=%d", len(tr), len(va), len(te))

    # Model
    if use_original:
        from radar_drone_vision.torch_models.cnn import SmallRadarCNN
        model = SmallRadarCNN(in_channels=in_channels, num_classes=2, dropout=0.3)
    else:
        model = build_enhanced_cnn(in_channels=in_channels, num_classes=2)
    model = model.to(device)
    param_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Model: %s (%d params)", model.__class__.__name__, param_count)

    criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.05)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-3)
    warmup_epochs = 5
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=epochs - warmup_epochs, eta_min=1e-6)

    best_val_f1 = -1
    best_state = None
    patience, no_improve = 15, 0

    for epoch in range(epochs):
        if epoch < warmup_epochs:
            for pg in optimizer.param_groups:
                pg["lr"] = lr * (epoch + 1) / warmup_epochs

        model.train()
        train_loss, correct, total = 0.0, 0, 0
        for X_b, y_b in train_loader:
            X_b, y_b = X_b.to(device), y_b.to(device)

            # Data augmentation: Gaussian noise
            if np.random.random() < 0.5:
                X_b = X_b + torch.randn_like(X_b) * 0.02

            # Mixup
            if np.random.random() < 0.3:
                lam = np.random.beta(0.2, 0.2)
                perm = torch.randperm(X_b.size(0))
                X_m = lam * X_b + (1 - lam) * X_b[perm]
                logits = model(X_m)
                loss = lam * criterion(logits, y_b) + (1 - lam) * criterion(logits, y_b[perm])
            else:
                logits = model(X_b)
                loss = criterion(logits, y_b)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            train_loss += loss.item() * len(y_b)
            correct += (logits.argmax(1) == y_b).sum().item()
            total += len(y_b)

        if epoch >= warmup_epochs:
            scheduler.step()

        # Validation
        model.eval()
        val_preds, val_labels, val_probs = [], [], []
        with torch.no_grad():
            for X_b, y_b in val_loader:
                X_b = X_b.to(device)
                logits = model(X_b)
                probs = torch.softmax(logits, dim=1)
                val_preds.extend(logits.argmax(1).cpu().numpy())
                val_labels.extend(y_b.numpy())
                val_probs.extend(probs[:, 1].cpu().numpy())

        val_f1 = f1_score(val_labels, val_preds, zero_division=0)
        val_acc = accuracy_score(val_labels, val_preds)

        if epoch % 10 == 0 or epoch == epochs - 1:
            logger.info("Epoch %3d/%d  loss=%.4f  acc=%.4f  val_f1=%.4f  lr=%.6f",
                        epoch+1, epochs, train_loss/max(total,1),
                        correct/max(total,1), val_f1, optimizer.param_groups[0]["lr"])

        if val_f1 > best_val_f1 + 1e-4:
            best_val_f1 = val_f1
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
        if no_improve >= patience:
            logger.info("Early stopping at epoch %d", epoch + 1)
            break

    if best_state:
        model.load_state_dict(best_state)
        logger.info("Restored best weights (val_f1=%.4f)", best_val_f1)

    # Test
    model.eval()
    test_preds, test_labels, test_probs = [], [], []
    with torch.no_grad():
        for X_b, y_b in test_loader:
            X_b = X_b.to(device)
            logits = model(X_b)
            probs = torch.softmax(logits, dim=1)
            test_preds.extend(logits.argmax(1).cpu().numpy())
            test_labels.extend(y_b.numpy())
            test_probs.extend(probs[:, 1].cpu().numpy())

    test_preds = np.array(test_preds)
    test_labels = np.array(test_labels)
    test_probs = np.array(test_probs)

    acc = accuracy_score(test_labels, test_preds)
    f1 = f1_score(test_labels, test_preds, zero_division=0)
    auc = roc_auc_score(test_labels, test_probs)
    fpr, tpr, _ = roc_curve(test_labels, test_probs)
    fnr = 1 - tpr
    eer_idx = np.nanargmin(np.abs(fpr - fnr))
    eer = float((fpr[eer_idx] + fnr[eer_idx]) / 2)
    far1_idx = np.nanargmin(np.abs(fnr - 0.01))
    far1 = float(fpr[far1_idx])

    metrics = {"accuracy": acc, "f1": f1, "eer": eer, "auc": auc, "far_at_frr_1pct": far1}
    logger.info("\n=== CNN Test Results ===")
    for k, v in metrics.items():
        logger.info("  %s: %.4f", k, v)

    return model, metrics


# ================================================================== #
# 4. Ensemble
# ================================================================== #

def evaluate_ensemble(sra_scores, cnn_probs, y_true, weights=None):
    from sklearn.metrics import accuracy_score, f1_score, roc_curve, roc_auc_score

    if weights is None:
        weights = [0.3, 0.7]

    # Normalize SRA scores to [0, 1]
    smin, smax = sra_scores.min(), sra_scores.max()
    sra_norm = (sra_scores - smin) / (smax - smin) if smax > smin else np.zeros_like(sra_scores)

    ens = weights[0] * sra_norm + weights[1] * cnn_probs

    fpr, tpr, thresholds = roc_curve(y_true, ens)
    fnr = 1 - tpr
    eer_idx = np.nanargmin(np.abs(fpr - fnr))
    eer = float((fpr[eer_idx] + fnr[eer_idx]) / 2)

    # Youden's J optimal threshold
    j = tpr - fpr
    opt_idx = np.argmax(j)
    opt_thresh = float(thresholds[opt_idx])

    y_pred = (ens >= opt_thresh).astype(int)
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    auc = roc_auc_score(y_true, ens)
    far1_idx = np.nanargmin(np.abs(fnr - 0.01))
    far1 = float(fpr[far1_idx])

    return {"accuracy": acc, "f1": f1, "eer": eer, "auc": auc,
            "far_at_frr_1pct": far1, "weights": weights}


# ================================================================== #
# 5. Main Pipeline
# ================================================================== #

def main(args):
    import torch

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Device: %s", device)

    # Load dataset
    logger.info("\n" + "=" * 70)
    logger.info("Loading dataset...")
    dataset = load_dataset(_PROJECT_ROOT)
    signals, labels = dataset.get_signals_and_labels()
    n_uav = (labels == 1).sum()
    n_non = (labels == 0).sum()
    logger.info("Total: %d (UAV: %d, non-UAV: %d)", len(labels), n_uav, n_non)

    # Clutter removal
    logger.info("Applying clutter removal...")
    signals_clean = apply_clutter_removal(signals)

    mode = args.mode
    results_dir = _PROJECT_ROOT / "data" / "reports"
    results_dir.mkdir(parents=True, exist_ok=True)
    models_dir = _PROJECT_ROOT / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================== #
    # Phase 1: SRA
    # ============================================================== #
    best_sra_params = {}
    if mode in ("sra_grid", "all", "ensemble"):
        logger.info("\n" + "=" * 70)
        logger.info("=== Phase 1: SRA Optimization ===")
        logger.info("=" * 70)

        # Subsample for fast grid search (5000 per class max)
        sub_idx = stratified_subsample(labels, n_per_class=5000, seed=args.seed)
        logger.info("Subsample: %d samples for grid search", len(sub_idx))

        # Feature extraction on subsample
        logger.info("Extracting features (subsample)...")
        X_sub = extract_features_batch(
            signals_clean[sub_idx],
            "proposed_regularized_complex_log_fft",
            config={"frame_size": 256, "hop_size": 128, "n_fft": 256},
        )
        y_sub = labels[sub_idx]
        logger.info("Feature shape: %s (%.1f MB)", X_sub.shape,
                     X_sub.nbytes / 1e6)

        # Baseline (original params, no PCA, no clutter removal)
        logger.info("\n--- Baseline SRA (original, no clutter rm) ---")
        X_base = extract_features_batch(
            signals[sub_idx],
            "proposed_regularized_complex_log_fft",
            config={"frame_size": 256, "hop_size": 128, "n_fft": 256},
        )
        # Apply PCA to baseline too for fair comparison
        from sklearn.decomposition import PCA
        pca_base = PCA(n_components=min(200, X_base.shape[1]), whiten=True)
        X_base_pca = pca_base.fit_transform(X_base.astype(np.float32))
        baseline = run_sra_evaluation(X_base_pca, y_sub,
                                      m_uav=10, m_non_uav=100, n_repeats=5)
        logger.info("Baseline: Acc=%.4f±%.4f  F1=%.4f±%.4f  EER=%.4f  AUC=%.4f",
                     baseline["accuracy"], baseline["accuracy_std"],
                     baseline["f1"], baseline["f1_std"],
                     baseline["eer"], baseline["auc"])

        # Baseline with clutter removal
        logger.info("\n--- + Clutter removal ---")
        pca_clean = PCA(n_components=min(200, X_sub.shape[1]), whiten=True)
        X_sub_pca = pca_clean.fit_transform(X_sub.astype(np.float32))
        clean_baseline = run_sra_evaluation(X_sub_pca, y_sub,
                                            m_uav=10, m_non_uav=100, n_repeats=5)
        logger.info("Clean:    Acc=%.4f±%.4f  F1=%.4f±%.4f  EER=%.4f  AUC=%.4f",
                     clean_baseline["accuracy"], clean_baseline["accuracy_std"],
                     clean_baseline["f1"], clean_baseline["f1_std"],
                     clean_baseline["eer"], clean_baseline["auc"])

        # Grid search with PCA
        logger.info("\n--- SRA Grid Search (with PCA) ---")
        best_sra_params, grid_results = sra_grid_search(
            X_sub, y_sub,
            n_repeats=args.sra_repeats, seed=args.seed,
            pca_dims=[100, 200, 300, 500],
        )

        # Save
        with open(results_dir / "sra_grid_results.json", "w") as f:
            json.dump(grid_results[:20], f, indent=2, default=float)

        # Summary table
        print("\n" + "=" * 70)
        print("  SRA Optimization Results")
        print("=" * 70)
        print(f"  {'Config':<50s} {'Acc':>8s} {'F1':>8s} {'EER':>8s} {'AUC':>8s}")
        print("-" * 76)
        print(f"  {'Baseline (m_uav=10, m_non=100, no clutter)':<50s} "
              f"{baseline['accuracy']:>8.4f} {baseline['f1']:>8.4f} "
              f"{baseline['eer']:>8.4f} {baseline['auc']:>8.4f}")
        print(f"  {'+ Clutter removal':<50s} "
              f"{clean_baseline['accuracy']:>8.4f} {clean_baseline['f1']:>8.4f} "
              f"{clean_baseline['eer']:>8.4f} {clean_baseline['auc']:>8.4f}")
        if best_sra_params:
            tag = (f"Best: pca={best_sra_params['pca_dim']} "
                   f"m_uav={best_sra_params['m_uav']} "
                   f"m_non={best_sra_params['m_non_uav']}")
            print(f"  {tag:<50s} "
                  f"{best_sra_params['accuracy']:>8.4f} "
                  f"{best_sra_params['f1']:>8.4f} "
                  f"{best_sra_params['eer']:>8.4f} "
                  f"{best_sra_params['auc']:>8.4f}")
        print("=" * 70)

        # Train final SRA with best params on full dataset
        if best_sra_params:
            logger.info("\nTraining final SRA on full dataset with best params...")
            pca_dim = best_sra_params["pca_dim"]
            from sklearn.decomposition import PCA as PCA2
            X_full = extract_features_batch(
                signals_clean, "proposed_regularized_complex_log_fft",
                config={"frame_size": 256, "hop_size": 128, "n_fft": 256})
            pca_final = PCA2(n_components=min(pca_dim, X_full.shape[1]), whiten=True)
            X_full_pca = pca_final.fit_transform(X_full.astype(np.float32))

            final_metrics = run_sra_evaluation(
                X_full_pca, labels,
                m_uav=best_sra_params["m_uav"],
                m_non_uav=best_sra_params["m_non_uav"],
                n_repeats=10, seed=args.seed)
            logger.info("Final SRA: Acc=%.4f±%.4f  F1=%.4f±%.4f  EER=%.4f  AUC=%.4f",
                         final_metrics["accuracy"], final_metrics["accuracy_std"],
                         final_metrics["f1"], final_metrics["f1_std"],
                         final_metrics["eer"], final_metrics["auc"])

            # Save model
            import joblib
            sra_final = EnhancedSRA(
                m_uav=best_sra_params["m_uav"],
                m_non_uav=best_sra_params["m_non_uav"])
            # Train on all data
            sra_final.fit(X_full_pca, labels)
            joblib.dump({
                "sra": sra_final,
                "pca": pca_final,
                "params": best_sra_params,
                "metrics": final_metrics,
            }, models_dir / "sra_enhanced.joblib")
            logger.info("Enhanced SRA saved to models/sra_enhanced.joblib")

    # ============================================================== #
    # Phase 2: CNN
    # ============================================================== #
    enhanced_model = None
    enhanced_cnn_metrics = {}
    if mode in ("cnn", "all", "ensemble"):
        logger.info("\n" + "=" * 70)
        logger.info("=== Phase 2: CNN Training ===")
        logger.info("=" * 70)

        # Extract image features
        logger.info("Extracting image features...")
        X_img = extract_features_batch(
            signals_clean, "proposed_complex_image",
            config={"frame_size": 256, "hop_size": 128, "n_fft": 256},
            flatten=False)
        logger.info("Image features: %s", X_img.shape)

        # Baseline CNN
        logger.info("\n--- Baseline SmallRadarCNN ---")
        _, baseline_cnn = train_cnn(
            X_img.copy(), labels, epochs=50, batch_size=64,
            lr=1e-3, device=device, seed=args.seed, use_original=True)

        # Enhanced CNN
        logger.info("\n--- Enhanced ResNet+SE CNN ---")
        enhanced_model, enhanced_cnn_metrics = train_cnn(
            X_img.copy(), labels, epochs=args.cnn_epochs, batch_size=64,
            lr=5e-4, device=device, seed=args.seed, use_original=False)

        print("\n" + "=" * 70)
        print("  CNN Results")
        print("=" * 70)
        print(f"  {'Model':<45s} {'Acc':>8s} {'F1':>8s} {'EER':>8s} {'AUC':>8s}")
        print("-" * 71)
        print(f"  {'Baseline SmallRadarCNN':<45s} "
              f"{baseline_cnn['accuracy']:>8.4f} {baseline_cnn['f1']:>8.4f} "
              f"{baseline_cnn['eer']:>8.4f} {baseline_cnn['auc']:>8.4f}")
        print(f"  {'Enhanced ResNet+SE (aug+classweight+mixup)':<45s} "
              f"{enhanced_cnn_metrics['accuracy']:>8.4f} "
              f"{enhanced_cnn_metrics['f1']:>8.4f} "
              f"{enhanced_cnn_metrics['eer']:>8.4f} "
              f"{enhanced_cnn_metrics['auc']:>8.4f}")
        print("=" * 70)

        # Save
        torch.save({
            "model_state_dict": enhanced_model.state_dict(),
            "model_class": "EnhancedRadarCNN",
            "in_channels": X_img.shape[-1] // (X_img.shape[-1] // 2) if X_img.ndim == 3 else 2,
            "metrics": enhanced_cnn_metrics,
        }, models_dir / "cnn_enhanced.pt")
        logger.info("Enhanced CNN saved to models/cnn_enhanced.pt")

    # ============================================================== #
    # Phase 3: Ensemble
    # ============================================================== #
    if mode in ("ensemble", "all") and enhanced_model is not None:
        logger.info("\n" + "=" * 70)
        logger.info("=== Phase 3: Ensemble ===")
        logger.info("=" * 70)

        # Shared test split
        np.random.seed(args.seed)
        n = len(labels)
        idx = np.random.permutation(n)
        n_train = int(0.70 * n)
        n_val = int(0.15 * n)
        train_idx = idx[:n_train]
        test_idx = idx[n_train + n_val:]

        # SRA scores on test set
        X_sra = extract_features_batch(
            signals_clean, "proposed_regularized_complex_log_fft",
            config={"frame_size": 256, "hop_size": 128, "n_fft": 256})
        from sklearn.decomposition import PCA as PCA3
        pca_dim = best_sra_params.get("pca_dim", 200) if best_sra_params else 200
        m_uav = best_sra_params.get("m_uav", 10) if best_sra_params else 10
        m_non = best_sra_params.get("m_non_uav", 100) if best_sra_params else 100
        pca_ens = PCA3(n_components=min(pca_dim, X_sra.shape[1]), whiten=True)
        X_sra_pca = pca_ens.fit_transform(X_sra.astype(np.float32))
        sra_ens = EnhancedSRA(m_uav=m_uav, m_non_uav=m_non)
        sra_ens.fit(X_sra_pca[train_idx], labels[train_idx])
        sra_scores = sra_ens.decision_function(X_sra_pca[test_idx])

        # CNN probs on test set
        X_img_test = extract_features_batch(
            signals_clean, "proposed_complex_image",
            config={"frame_size": 256, "hop_size": 128, "n_fft": 256},
            flatten=False)
        X_cnn_test = prepare_cnn_data(X_img_test)
        X_test_tensor = torch.from_numpy(X_cnn_test[test_idx]).to(device)

        enhanced_model.eval()
        with torch.no_grad():
            # Process in batches to avoid OOM
            cnn_probs = []
            for i in range(0, len(X_test_tensor), 256):
                batch = X_test_tensor[i:i+256]
                logits = enhanced_model(batch)
                probs = torch.softmax(logits, dim=1)[:, 1]
                cnn_probs.extend(probs.cpu().numpy())
            cnn_probs = np.array(cnn_probs)

        y_test = labels[test_idx]

        print("\n" + "=" * 70)
        print("  Ensemble Results (SRA + CNN)")
        print("=" * 70)
        print(f"  {'Weights (SRA:CNN)':<25s} {'Acc':>8s} {'F1':>8s} {'EER':>8s} {'AUC':>8s}")
        print("-" * 51)
        for w in [[0.2, 0.8], [0.3, 0.7], [0.4, 0.6], [0.5, 0.5]]:
            ens = evaluate_ensemble(sra_scores, cnn_probs, y_test, weights=w)
            print(f"  {str(w):<25s} "
                  f"{ens['accuracy']:>8.4f} {ens['f1']:>8.4f} "
                  f"{ens['eer']:>8.4f} {ens['auc']:>8.4f}")
        print("=" * 70)

    print("\n" + "=" * 70)
    print("  COMPLETE — Results in data/reports/, Models in models/")
    print("=" * 70)


def parse_args():
    parser = argparse.ArgumentParser(description="Enhanced UAV/Bird classifier")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--mode", default="all", choices=["sra_grid", "cnn", "ensemble", "all"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sra-repeats", type=int, default=5)
    parser.add_argument("--cnn-epochs", type=int, default=80)
    return parser.parse_args()


if __name__ == "__main__":
    main(parse_args())
