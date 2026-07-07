#!/usr/bin/env python3
"""Pre-compute ROC/DET curves for all algorithms and save to JSON.

Generates comparison data for:
  1. Baseline SRA (Proposed Feature + SRA, original params)
  2. Enhanced SRA (+ clutter removal + PCA)
  3. Baseline CNN (SmallRadarCNN)
  4. Enhanced CNN (ResNet+SE)
  5. Spectrogram + PCA baseline
  6. CVD + PCA baseline

Output: data/reports/roc_comparison.json
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("precompute_roc")


def load_dataset():
    from radar_drone_vision.datasets.zenodo77 import Zenodo77Dataset
    for subdir in ["zenodo_77ghz", "zenodo77"]:
        for prefix in ["raw", "processed"]:
            candidate = _PROJECT_ROOT / "data" / prefix / subdir
            npy_file = candidate / "data_SAAB_SIRS_77GHz_FMCW.npy"
            if npy_file.exists():
                return Zenodo77Dataset(candidate)
    print("[ERROR] Dataset not found")
    sys.exit(1)


def extract_features(signals, feature_type, config=None, flatten=True):
    from radar_drone_vision.features.extractors import extract_features as ef
    cfg = {"flatten": flatten}
    if config:
        cfg.update(config)
    cfg["flatten"] = flatten
    n = len(signals)
    batch = 5000
    parts = []
    for s in range(0, n, batch):
        e = min(s + batch, n)
        parts.append(ef(list(signals[s:e]), feature_type, cfg))
        logger.info("  %d/%d", e, n)
    return np.vstack(parts) if len(parts) > 1 else parts[0]


def apply_clutter_removal(signals):
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
            cleaned[i] = sig
    return cleaned


def stratified_split(y, test_ratio=0.3, seed=42):
    rng = np.random.default_rng(seed)
    train_idx, test_idx = [], []
    for cls in np.unique(y):
        cls_idx = np.where(y == cls)[0].copy()
        rng.shuffle(cls_idx)
        n_test = int(len(cls_idx) * test_ratio)
        test_idx.extend(cls_idx[:n_test].tolist())
        train_idx.extend(cls_idx[n_test:].tolist())
    return np.array(train_idx), np.array(test_idx)


def compute_roc_data(y_true, scores, max_points=200):
    """Compute ROC and DET curve data, downsampled."""
    from sklearn.metrics import roc_curve, roc_auc_score

    fpr, tpr, thresholds = roc_curve(y_true, scores)
    fnr = 1 - tpr
    auc = float(roc_auc_score(y_true, scores))

    # EER
    eer_idx = np.nanargmin(np.abs(fpr - fnr))
    eer = float((fpr[eer_idx] + fnr[eer_idx]) / 2)

    # FAR @ FRR=1%
    far1_idx = np.nanargmin(np.abs(fnr - 0.01))
    far1 = float(fpr[far1_idx])

    # Downsample
    step = max(1, len(fpr) // max_points)
    idx = list(range(0, len(fpr), step))
    if idx[-1] != len(fpr) - 1:
        idx.append(len(fpr) - 1)

    def safe(arr):
        return [float(v) if np.isfinite(v) else 0.0 for v in arr]

    return {
        "roc": {"fpr": safe(fpr[idx]), "tpr": safe(tpr[idx])},
        "det": {"fpr": safe(fpr[idx]), "fnr": safe(fnr[idx])},
        "auc": auc,
        "eer": eer,
        "far_at_frr_1pct": far1,
    }


def main():
    logger.info("Loading dataset...")
    dataset = load_dataset()
    signals, labels = dataset.get_signals_and_labels()
    n_uav = (labels == 1).sum()
    n_non = (labels == 0).sum()
    logger.info("Total: %d (UAV: %d, non-UAV: %d)", len(labels), n_uav, n_non)

    # Use subsample for faster computation (15k samples)
    rng = np.random.default_rng(42)
    sub_idx_uav = rng.choice(np.where(labels == 1)[0], size=min(10000, n_uav), replace=False)
    sub_idx_non = rng.choice(np.where(labels == 0)[0], size=min(5000, n_non), replace=False)
    sub_idx = np.sort(np.concatenate([sub_idx_uav, sub_idx_non]))
    signals_sub = signals[sub_idx]
    labels_sub = labels[sub_idx]
    logger.info("Subsample: %d samples", len(sub_idx))

    signals_clean = apply_clutter_removal(signals_sub)

    # Train/test split
    train_idx, test_idx = stratified_split(labels_sub, test_ratio=0.3, seed=42)
    y_test = labels_sub[test_idx]
    y_train = labels_sub[train_idx]

    results = {}
    stft_cfg = {"frame_size": 256, "hop_size": 128, "n_fft": 256}

    # ─── 1. SRA (Proposed Feature, original) ───
    logger.info("\n=== 1. Baseline SRA ===")
    X_sra = extract_features(signals_sub, "proposed_regularized_complex_log_fft", stft_cfg)
    from sklearn.decomposition import PCA
    pca_sra = PCA(n_components=min(200, X_sra.shape[1]), whiten=True)
    X_sra_pca = pca_sra.fit_transform(X_sra.astype(np.float32))

    from scripts.train_enhanced import EnhancedSRA
    sra = EnhancedSRA(m_uav=10, m_non_uav=100)
    sra.fit(X_sra_pca[train_idx], y_train)
    sra_scores = sra.decision_function(X_sra_pca[test_idx])
    results["Proposed Feature + SRA"] = {
        **compute_roc_data(y_test, sra_scores),
        "color": "#22c55e",
        "dash": False,
    }
    logger.info("  AUC=%.4f EER=%.4f", results["Proposed Feature + SRA"]["auc"],
                results["Proposed Feature + SRA"]["eer"])

    # ─── 2. SRA + Clutter Removal ───
    logger.info("\n=== 2. SRA + Clutter Removal ===")
    X_sra_clean = extract_features(signals_clean, "proposed_regularized_complex_log_fft", stft_cfg)
    pca_clean = PCA(n_components=min(200, X_sra_clean.shape[1]), whiten=True)
    X_sra_clean_pca = pca_clean.fit_transform(X_sra_clean.astype(np.float32))
    sra_clean = EnhancedSRA(m_uav=10, m_non_uav=100)
    sra_clean.fit(X_sra_clean_pca[train_idx], y_train)
    sra_clean_scores = sra_clean.decision_function(X_sra_clean_pca[test_idx])
    results["SRA + Clutter Removal"] = {
        **compute_roc_data(y_test, sra_clean_scores),
        "color": "#06b6d4",
        "dash": False,
    }
    logger.info("  AUC=%.4f EER=%.4f", results["SRA + Clutter Removal"]["auc"],
                results["SRA + Clutter Removal"]["eer"])

    # ─── 3. Spectrogram + PCA ───
    logger.info("\n=== 3. Spectrogram + PCA ===")
    X_spec = extract_features(signals_sub, "spectrogram", stft_cfg)
    pca_spec = PCA(n_components=min(200, X_spec.shape[1]), whiten=True)
    X_spec_pca = pca_spec.fit_transform(X_spec.astype(np.float32))
    sra_spec = EnhancedSRA(m_uav=10, m_non_uav=100)
    sra_spec.fit(X_spec_pca[train_idx], y_train)
    spec_scores = sra_spec.decision_function(X_spec_pca[test_idx])
    results["Spectrogram + PCA"] = {
        **compute_roc_data(y_test, spec_scores),
        "color": "#f59e0b",
        "dash": True,
    }
    logger.info("  AUC=%.4f EER=%.4f", results["Spectrogram + PCA"]["auc"],
                results["Spectrogram + PCA"]["eer"])

    # ─── 4. CVD + PCA ───
    logger.info("\n=== 4. CVD + PCA ===")
    X_cvd = extract_features(signals_sub, "cvd", stft_cfg)
    pca_cvd = PCA(n_components=min(200, X_cvd.shape[1]), whiten=True)
    X_cvd_pca = pca_cvd.fit_transform(X_cvd.astype(np.float32))
    sra_cvd = EnhancedSRA(m_uav=10, m_non_uav=100)
    sra_cvd.fit(X_cvd_pca[train_idx], y_train)
    cvd_scores = sra_cvd.decision_function(X_cvd_pca[test_idx])
    results["CVD + PCA"] = {
        **compute_roc_data(y_test, cvd_scores),
        "color": "#ef4444",
        "dash": True,
    }
    logger.info("  AUC=%.4f EER=%.4f", results["CVD + PCA"]["auc"],
                results["CVD + PCA"]["eer"])

    # ─── 5. Cepstrogram + PCA ───
    logger.info("\n=== 5. Cepstrogram + PCA ===")
    X_cep = extract_features(signals_sub, "cepstrogram", stft_cfg)
    pca_cep = PCA(n_components=min(200, X_cep.shape[1]), whiten=True)
    X_cep_pca = pca_cep.fit_transform(X_cep.astype(np.float32))
    sra_cep = EnhancedSRA(m_uav=10, m_non_uav=100)
    sra_cep.fit(X_cep_pca[train_idx], y_train)
    cep_scores = sra_cep.decision_function(X_cep_pca[test_idx])
    results["Cepstrogram + PCA"] = {
        **compute_roc_data(y_test, cep_scores),
        "color": "#a855f7",
        "dash": True,
    }
    logger.info("  AUC=%.4f EER=%.4f", results["Cepstrogram + PCA"]["auc"],
                results["Cepstrogram + PCA"]["eer"])

    # ─── 6. Baseline CNN (SmallRadarCNN) ───
    logger.info("\n=== 6. Baseline CNN ===")
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"

    X_img = extract_features(signals_clean, "proposed_complex_image", stft_cfg, flatten=False)
    from scripts.train_enhanced import prepare_cnn_data
    X_cnn = prepare_cnn_data(X_img)

    from radar_drone_vision.torch_models.cnn import SmallRadarCNN
    baseline_cnn = SmallRadarCNN(in_channels=X_cnn.shape[1], num_classes=2, dropout=0.3).to(device)
    baseline_cnn.train()

    # Quick train
    from torch.utils.data import DataLoader, TensorDataset
    train_ds = TensorDataset(
        torch.from_numpy(X_cnn[train_idx]),
        torch.from_numpy(labels_sub[train_idx].astype(np.int64)))
    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True, drop_last=True)
    optimizer = torch.optim.Adam(baseline_cnn.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = torch.nn.CrossEntropyLoss()

    for epoch in range(30):
        baseline_cnn.train()
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            loss = criterion(baseline_cnn(xb), yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        if (epoch + 1) % 10 == 0:
            logger.info("  Epoch %d/30", epoch + 1)

    baseline_cnn.eval()
    cnn_probs = []
    with torch.no_grad():
        for i in range(0, len(test_idx), 256):
            batch = torch.from_numpy(X_cnn[test_idx[i:i+256]]).to(device)
            probs = torch.softmax(baseline_cnn(batch), dim=1)[:, 1]
            cnn_probs.extend(probs.cpu().numpy())
    cnn_probs = np.array(cnn_probs)
    results["Baseline CNN"] = {
        **compute_roc_data(y_test, cnn_probs),
        "color": "#3b82f6",
        "dash": False,
    }
    logger.info("  AUC=%.4f EER=%.4f", results["Baseline CNN"]["auc"],
                results["Baseline CNN"]["eer"])

    # ─── 7. Enhanced CNN (ResNet+SE) ───
    logger.info("\n=== 7. Enhanced CNN ===")
    from scripts.train_enhanced import build_enhanced_cnn
    enhanced_cnn = build_enhanced_cnn(in_channels=X_cnn.shape[1], num_classes=2).to(device)

    # Check for saved model
    model_path = _PROJECT_ROOT / "models" / "cnn_enhanced.pt"
    if model_path.exists():
        state = torch.load(model_path, map_location=device, weights_only=True)
        enhanced_cnn.load_state_dict(state["model_state_dict"])
        logger.info("  Loaded pre-trained enhanced CNN")
    else:
        # Quick train
        optimizer2 = torch.optim.AdamW(enhanced_cnn.parameters(), lr=5e-4, weight_decay=1e-3)
        n_cls = np.bincount(labels_sub[train_idx].astype(int))
        w = torch.tensor([len(train_idx) / (2 * max(n_cls[0], 1)),
                          len(train_idx) / (2 * max(n_cls[1], 1))],
                         dtype=torch.float32).to(device)
        criterion2 = torch.nn.CrossEntropyLoss(weight=w, label_smoothing=0.05)
        for epoch in range(40):
            enhanced_cnn.train()
            for xb, yb in train_loader:
                xb, yb = xb.to(device), yb.to(device)
                loss = criterion2(enhanced_cnn(xb), yb)
                optimizer2.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(enhanced_cnn.parameters(), 1.0)
                optimizer2.step()
            if (epoch + 1) % 10 == 0:
                logger.info("  Epoch %d/40", epoch + 1)

    enhanced_cnn.eval()
    enh_probs = []
    with torch.no_grad():
        for i in range(0, len(test_idx), 256):
            batch = torch.from_numpy(X_cnn[test_idx[i:i+256]]).to(device)
            probs = torch.softmax(enhanced_cnn(batch), dim=1)[:, 1]
            enh_probs.extend(probs.cpu().numpy())
    enh_probs = np.array(enh_probs)
    results["Enhanced CNN (ResNet+SE)"] = {
        **compute_roc_data(y_test, enh_probs),
        "color": "#ec4899",
        "dash": False,
    }
    logger.info("  AUC=%.4f EER=%.4f", results["Enhanced CNN (ResNet+SE)"]["auc"],
                results["Enhanced CNN (ResNet+SE)"]["eer"])

    # Save
    out_dir = _PROJECT_ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "roc_comparison.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("\nSaved to %s", out_path)

    # Summary
    print("\n" + "=" * 70)
    print("  ROC Comparison Summary")
    print("=" * 70)
    print(f"  {'Method':<35s} {'AUC':>8s} {'EER':>8s} {'FAR@1%':>8s}")
    print("-" * 61)
    for name, r in results.items():
        print(f"  {name:<35s} {r['auc']:>8.4f} {r['eer']:>8.4f} {r['far_at_frr_1pct']:>8.4f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
