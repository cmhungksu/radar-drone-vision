#!/usr/bin/env python3
"""Train a PyTorch CNN for radar micro-Doppler UAV classification.

Usage:
    python scripts/train_cnn.py \
        --config configs/models/cnn.yaml \
        --dataset zenodo77 \
        --feature proposed_complex_image \
        --epochs 50
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import yaml

# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

try:
    from tqdm import tqdm, trange
except ImportError:
    def tqdm(it, **kw):  # type: ignore[override]
        return it
    def trange(n, **kw):  # type: ignore[override]
        return range(n)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("train_cnn")


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def load_config(config_path: str) -> Dict[str, Any]:
    p = Path(config_path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    logger.warning("Config file %s not found — using defaults.", config_path)
    return {}


def load_dataset(dataset_name: str, project_root: Path):
    if dataset_name in ("zenodo77", "zenodo_77ghz_fmcw"):
        from radar_drone_vision.datasets.zenodo77 import Zenodo77Dataset

        for subdir in ["zenodo_77ghz", "zenodo77", "zenodo_77ghz_fmcw"]:
            for prefix in ["raw", "processed"]:
                candidate = project_root / "data" / prefix / subdir
                npy_file = candidate / "data_SAAB_SIRS_77GHz_FMCW.npy"
                if npy_file.exists():
                    return Zenodo77Dataset(candidate)
        print(
            "\n[ERROR] Dataset directory not found.\n"
            "  Please download: python scripts/download_zenodo.py --out data/raw/zenodo_77ghz\n"
        )
        sys.exit(1)
    else:
        print(f"\n[ERROR] Unknown dataset: '{dataset_name}'")
        sys.exit(1)


def extract_image_features(
    dataset,
    feature_type: str,
    config: Dict[str, Any],
    resize: Optional[Tuple[int, int]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Extract 2-D (image) features — do NOT flatten."""
    from radar_drone_vision.features.extractors import extract_features

    logger.info("Extracting image features (type=%s) ...", feature_type)
    signals = [dataset[i].signal for i in range(len(dataset))]
    labels = np.array([dataset[i].label_binary for i in range(len(dataset))])

    feat_cfg = {"flatten": False}
    if "signal" in config:
        feat_cfg.update(config["signal"])
    feat_cfg["flatten"] = False  # ensure no flattening

    X = extract_features(signals, feature_type, feat_cfg)
    logger.info("Raw feature shape: %s", X.shape)

    # Resize if requested
    if resize is not None and X.ndim >= 2:
        from scipy.ndimage import zoom

        target_h, target_w = resize
        resized = []
        for img in X:
            if img.ndim == 2:
                h, w = img.shape
                img_r = zoom(img, (target_h / h, target_w / w), order=1)
                resized.append(img_r)
            elif img.ndim == 3:
                # (H, W, C) or (C, H, W) — assume (H, W*2) from complex_image
                h, w = img.shape[:2]
                img_r = zoom(img, (target_h / h, target_w / w), order=1)
                resized.append(img_r)
            else:
                resized.append(img)
        X = np.array(resized)
        logger.info("Resized feature shape: %s", X.shape)

    return X, labels


# ------------------------------------------------------------------ #
# Trainer
# ------------------------------------------------------------------ #

class Trainer:
    """Simple training loop for PyTorch models."""

    def __init__(
        self,
        model,
        device: str = "cpu",
        lr: float = 1e-3,
        weight_decay: float = 1e-4,
        class_weight: Optional[str] = None,
        patience: int = 10,
        min_delta: float = 1e-3,
    ):
        import torch
        import torch.nn as nn

        self.device = torch.device(device)
        self.model = model.to(self.device)

        self.optimizer = torch.optim.Adam(
            model.parameters(), lr=lr, weight_decay=weight_decay
        )
        self.scheduler: Optional[torch.optim.lr_scheduler._LRScheduler] = None

        # Loss
        self.criterion = nn.CrossEntropyLoss()
        self.patience = patience
        self.min_delta = min_delta

        self.best_val_metric = -float("inf")
        self.best_state: Optional[dict] = None
        self.epochs_no_improve = 0

    def set_cosine_scheduler(self, epochs: int) -> None:
        import torch
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=epochs
        )

    def train_epoch(self, loader) -> Dict[str, float]:
        import torch
        self.model.train()
        total_loss = 0.0
        correct = 0
        total = 0
        for X_batch, y_batch in loader:
            X_batch = X_batch.to(self.device)
            y_batch = y_batch.to(self.device)

            self.optimizer.zero_grad()
            logits = self.model(X_batch)
            loss = self.criterion(logits, y_batch)
            loss.backward()
            self.optimizer.step()

            total_loss += loss.item() * len(y_batch)
            preds = logits.argmax(dim=1)
            correct += (preds == y_batch).sum().item()
            total += len(y_batch)

        if self.scheduler is not None:
            self.scheduler.step()

        return {
            "train_loss": total_loss / max(total, 1),
            "train_acc": correct / max(total, 1),
        }

    @staticmethod
    def evaluate(model, loader, device) -> Dict[str, float]:
        import torch
        import torch.nn as nn
        from sklearn.metrics import f1_score

        model.eval()
        criterion = nn.CrossEntropyLoss()
        total_loss = 0.0
        all_preds = []
        all_labels = []

        with torch.no_grad():
            for X_batch, y_batch in loader:
                X_batch = X_batch.to(device)
                y_batch = y_batch.to(device)
                logits = model(X_batch)
                loss = criterion(logits, y_batch)
                total_loss += loss.item() * len(y_batch)
                preds = logits.argmax(dim=1)
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(y_batch.cpu().numpy())

        all_preds_np = np.array(all_preds)
        all_labels_np = np.array(all_labels)
        n = len(all_labels_np)
        acc = float((all_preds_np == all_labels_np).sum()) / max(n, 1)
        f1 = float(f1_score(all_labels_np, all_preds_np, zero_division=0))
        return {
            "val_loss": total_loss / max(n, 1),
            "val_acc": acc,
            "val_f1": f1,
        }

    def fit(
        self,
        train_loader,
        val_loader,
        epochs: int,
    ) -> list:
        history = []
        for epoch in trange(epochs, desc="Training"):
            train_m = self.train_epoch(train_loader)
            val_m = self.evaluate(self.model, val_loader, self.device)

            row = {**train_m, **val_m, "epoch": epoch + 1}
            history.append(row)

            # Early stopping on val_f1
            metric = val_m.get("val_f1", val_m.get("val_acc", 0))
            if metric > self.best_val_metric + self.min_delta:
                self.best_val_metric = metric
                self.best_state = {k: v.cpu().clone() for k, v in self.model.state_dict().items()}
                self.epochs_no_improve = 0
            else:
                self.epochs_no_improve += 1

            if epoch % 5 == 0 or epoch == epochs - 1:
                lr = self.optimizer.param_groups[0]["lr"]
                logger.info(
                    "Epoch %3d/%d  train_loss=%.4f  val_loss=%.4f  val_f1=%.4f  lr=%.6f",
                    epoch + 1, epochs,
                    train_m["train_loss"], val_m["val_loss"], metric, lr,
                )

            if self.epochs_no_improve >= self.patience:
                logger.info("Early stopping at epoch %d (patience=%d)", epoch + 1, self.patience)
                break

        # Restore best weights
        if self.best_state is not None:
            self.model.load_state_dict(self.best_state)
            logger.info("Restored best model weights (val_f1=%.4f)", self.best_val_metric)

        return history


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def run_training(args: argparse.Namespace) -> None:
    import torch
    from torch.utils.data import DataLoader

    from radar_drone_vision.torch_models.cnn import SmallRadarCNN
    from radar_drone_vision.torch_models.datasets import MicroDopplerDataset

    config = load_config(args.config)
    dataset = load_dataset(args.dataset, _PROJECT_ROOT)

    # Feature type
    feature_type = args.feature or config.get("feature", {}).get("type", "proposed_complex_image")
    resize_cfg = config.get("feature", {}).get("resize", [128, 128])
    resize = tuple(resize_cfg) if resize_cfg else (128, 128)

    # Extract 2-D features
    X, y = extract_image_features(dataset, feature_type, config, resize=resize)

    # For complex_image features: split into 2 channels (real, imag)
    if "complex_image" in feature_type and X.ndim == 3:
        # X is (N, H, W*2) — split into (N, 2, H, W//2) or reshape
        n, h, w = X.shape
        half_w = w // 2
        X_real = X[:, :, :half_w]
        X_imag = X[:, :, half_w:]
        X = np.stack([X_real, X_imag], axis=1)  # (N, 2, H, W/2)
        logger.info("Reshaped to 2-channel image: %s", X.shape)
    elif X.ndim == 3:
        # Single-channel: (N, H, W) -> (N, 1, H, W)
        X = X[:, np.newaxis, :, :]

    # Train / val / test split (60/20/20)
    np.random.seed(args.seed)
    n = len(y)
    indices = np.random.permutation(n)
    n_train = int(0.6 * n)
    n_val = int(0.2 * n)
    train_idx = indices[:n_train]
    val_idx = indices[n_train : n_train + n_val]
    test_idx = indices[n_train + n_val :]

    train_ds = MicroDopplerDataset(X[train_idx], y[train_idx])
    val_ds = MicroDopplerDataset(X[val_idx], y[val_idx])
    test_ds = MicroDopplerDataset(X[test_idx], y[test_idx])

    batch_size = config.get("training", {}).get("batch_size", 64)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False)

    logger.info("Splits: train=%d  val=%d  test=%d", len(train_ds), len(val_ds), len(test_ds))

    # Build model
    model_cfg = config.get("model", {})
    in_channels = model_cfg.get("in_channels", X.shape[1] if X.ndim == 4 else 1)
    num_classes = model_cfg.get("num_classes", 2)
    dropout = model_cfg.get("dropout", 0.3)

    model = SmallRadarCNN(in_channels=in_channels, num_classes=num_classes, dropout=dropout)
    logger.info("Model: %s (in_ch=%d, classes=%d)", model.__class__.__name__, in_channels, num_classes)

    # Device
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    # Training params
    train_cfg = config.get("training", {})
    epochs = args.epochs or train_cfg.get("epochs", 50)
    lr = train_cfg.get("learning_rate", 1e-3)
    wd = train_cfg.get("weight_decay", 1e-4)
    es_cfg = train_cfg.get("early_stopping", {})
    patience = es_cfg.get("patience", 10)
    min_delta = es_cfg.get("min_delta", 1e-3)

    trainer = Trainer(
        model=model,
        device=device,
        lr=lr,
        weight_decay=wd,
        patience=patience,
        min_delta=min_delta,
    )
    if train_cfg.get("scheduler") == "cosine":
        trainer.set_cosine_scheduler(epochs)

    t0 = time.time()
    history = trainer.fit(train_loader, val_loader, epochs)
    elapsed = time.time() - t0

    # Evaluate on test set
    test_metrics = Trainer.evaluate(model, test_loader, torch.device(device))

    # Print summary
    print("\n" + "=" * 60)
    print(f"  CNN Training Summary  (epochs ran: {len(history)})")
    print(f"  Feature: {feature_type}")
    print(f"  Device: {device}   Time: {elapsed:.1f}s")
    print("=" * 60)
    for k, v in test_metrics.items():
        print(f"  {k:<20s} {v:>10.4f}")
    print("=" * 60)

    # Save model
    models_dir = _PROJECT_ROOT / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    pt_path = models_dir / "cnn_best.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_config": {
                "in_channels": in_channels,
                "num_classes": num_classes,
                "dropout": dropout,
            },
            "feature_type": feature_type,
            "test_metrics": test_metrics,
            "config": config,
        },
        pt_path,
    )
    print(f"\n  Model checkpoint saved: {pt_path}")

    # Export ONNX
    export_cfg = config.get("export", {})
    if export_cfg.get("onnx", True):
        try:
            onnx_path = models_dir / "cnn_best.onnx"
            input_shape = export_cfg.get("input_shape", [1, in_channels, 128, 128])
            dummy = torch.randn(*input_shape).to(torch.device(device))
            model.eval()
            torch.onnx.export(
                model,
                dummy,
                str(onnx_path),
                input_names=["input"],
                output_names=["logits"],
                dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
                opset_version=17,
            )
            print(f"  ONNX export saved: {onnx_path}")
        except Exception as e:
            logger.warning("ONNX export failed: %s", e)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train PyTorch CNN for radar micro-Doppler UAV detection."
    )
    parser.add_argument("--config", type=str, default="configs/models/cnn.yaml")
    parser.add_argument("--dataset", type=str, default="zenodo77")
    parser.add_argument("--feature", type=str, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--device", type=str, default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    run_training(parse_args())
