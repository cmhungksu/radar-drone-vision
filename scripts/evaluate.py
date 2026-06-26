#!/usr/bin/env python3
"""Evaluate trained models (SRA or CNN) on radar micro-Doppler datasets.

Usage:
    # Single model
    python scripts/evaluate.py \
        --model models/sra_model.joblib \
        --dataset zenodo77 \
        --out reports/sra_eval

    # All models in models/ directory
    python scripts/evaluate.py --all --dataset zenodo77 --out reports/full_eval
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):  # type: ignore[override]
        return it

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("evaluate")


# ------------------------------------------------------------------ #
# Dataset loading (shared logic)
# ------------------------------------------------------------------ #

def load_dataset(dataset_name: str, project_root: Path):
    if dataset_name in ("zenodo77", "zenodo_77ghz_fmcw"):
        from radar_drone_vision.datasets.zenodo77 import Zenodo77Dataset

        data_dir = project_root / "data" / "processed" / "zenodo_77ghz_fmcw"
        if not data_dir.exists():
            data_dir = project_root / "data" / "raw" / "zenodo_77ghz_fmcw"
        if not data_dir.exists():
            print(
                f"\n[ERROR] Dataset not found: {data_dir}\n"
                "  Run: python scripts/download_zenodo.py --out data/raw/zenodo_77ghz_fmcw\n"
            )
            sys.exit(1)
        return Zenodo77Dataset(data_dir)
    else:
        print(f"\n[ERROR] Unknown dataset: '{dataset_name}'")
        sys.exit(1)


# ------------------------------------------------------------------ #
# Model loading
# ------------------------------------------------------------------ #

def detect_model_type(model_path: Path) -> str:
    """Auto-detect model type by file extension."""
    suffix = model_path.suffix.lower()
    if suffix == ".joblib":
        return "sra"
    elif suffix == ".pt" or suffix == ".pth":
        return "cnn"
    elif suffix == ".onnx":
        return "onnx"
    else:
        raise ValueError(f"Cannot detect model type from extension '{suffix}'")


def load_sra_model(model_path: Path) -> dict:
    import joblib
    data = joblib.load(model_path)
    return data


def load_cnn_model(model_path: Path) -> dict:
    import torch
    from radar_drone_vision.torch_models.cnn import SmallRadarCNN

    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    mcfg = checkpoint.get("model_config", {})
    model = SmallRadarCNN(
        in_channels=mcfg.get("in_channels", 2),
        num_classes=mcfg.get("num_classes", 2),
        dropout=mcfg.get("dropout", 0.3),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return {"model": model, **checkpoint}


# ------------------------------------------------------------------ #
# Feature extraction
# ------------------------------------------------------------------ #

def extract_features(dataset, feature_type: str, flatten: bool = True) -> Tuple[np.ndarray, np.ndarray]:
    from radar_drone_vision.features.extractors import extract_features as _extract

    signals = [dataset[i].signal for i in range(len(dataset))]
    labels = np.array([dataset[i].label_binary for i in range(len(dataset))])
    X = _extract(signals, feature_type, {"flatten": flatten})
    return X, labels


# ------------------------------------------------------------------ #
# Evaluation metrics & plots
# ------------------------------------------------------------------ #

def compute_full_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    scores: np.ndarray,
) -> Dict[str, Any]:
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
        roc_curve,
    )

    # EER
    fpr, tpr, thresholds = roc_curve(y_true, scores)
    fnr = 1 - tpr
    eer_idx = np.nanargmin(np.abs(fpr - fnr))
    eer = float((fpr[eer_idx] + fnr[eer_idx]) / 2)
    eer_thresh = float(thresholds[eer_idx])

    # FAR @ FRR=1%
    far_idx = np.nanargmin(np.abs(fnr - 0.01))
    far_at_frr1 = float(fpr[far_idx])

    # Threshold table
    threshold_table = []
    for target_frr in [0.001, 0.005, 0.01, 0.02, 0.05, 0.10]:
        idx = np.nanargmin(np.abs(fnr - target_frr))
        threshold_table.append({
            "target_frr": target_frr,
            "actual_frr": float(fnr[idx]),
            "far": float(fpr[idx]),
            "threshold": float(thresholds[idx]),
        })

    cm = confusion_matrix(y_true, y_pred).tolist()

    try:
        auc = float(roc_auc_score(y_true, scores))
    except ValueError:
        auc = float("nan")

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "auc": auc,
        "eer": eer,
        "eer_threshold": eer_thresh,
        "far_at_frr_1pct": far_at_frr1,
        "confusion_matrix": cm,
        "threshold_table": threshold_table,
        "roc": {"fpr": fpr.tolist(), "tpr": tpr.tolist(), "thresholds": thresholds.tolist()},
        "classification_report": classification_report(
            y_true, y_pred, target_names=["non-UAV", "UAV"], output_dict=True
        ),
    }


def save_plots(
    metrics: Dict[str, Any],
    model_name: str,
    out_dir: Path,
) -> None:
    """Generate and save evaluation plots."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay, DetCurveDisplay

    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    # 1. Confusion matrix
    cm = np.array(metrics["confusion_matrix"])
    fig_cm, ax_cm = plt.subplots(figsize=(6, 5))
    disp = ConfusionMatrixDisplay(cm, display_labels=["non-UAV", "UAV"])
    disp.plot(ax=ax_cm, cmap="Blues")
    ax_cm.set_title(f"Confusion Matrix — {model_name}")
    fig_cm.tight_layout()
    fig_cm.savefig(fig_dir / f"{model_name}_confusion_matrix.png", dpi=150)
    plt.close(fig_cm)

    # 2. ROC curve
    roc = metrics.get("roc", {})
    fpr = np.array(roc.get("fpr", []))
    tpr_arr = np.array(roc.get("tpr", []))
    if len(fpr) > 0:
        fig_roc, ax_roc = plt.subplots(figsize=(6, 5))
        ax_roc.plot(fpr, tpr_arr, lw=2, label=f"AUC = {metrics.get('auc', 0):.4f}")
        ax_roc.plot([0, 1], [0, 1], "k--", lw=1)
        ax_roc.set_xlabel("False Positive Rate")
        ax_roc.set_ylabel("True Positive Rate")
        ax_roc.set_title(f"ROC Curve — {model_name}")
        ax_roc.legend()
        ax_roc.grid(True, alpha=0.3)
        fig_roc.tight_layout()
        fig_roc.savefig(fig_dir / f"{model_name}_roc.png", dpi=150)
        plt.close(fig_roc)

    # 3. DET curve (FNR vs FPR in normal-deviate scale, or linear)
    if len(fpr) > 0:
        fnr = 1 - tpr_arr
        fig_det, ax_det = plt.subplots(figsize=(6, 5))
        ax_det.plot(fpr * 100, fnr * 100, lw=2)
        ax_det.set_xlabel("FAR (%)")
        ax_det.set_ylabel("FRR (%)")
        ax_det.set_title(f"DET Curve — {model_name}")
        ax_det.set_xlim([0, 50])
        ax_det.set_ylim([0, 50])
        ax_det.plot([0, 50], [0, 50], "k--", lw=1, alpha=0.5)
        ax_det.grid(True, alpha=0.3)
        fig_det.tight_layout()
        fig_det.savefig(fig_dir / f"{model_name}_det.png", dpi=150)
        plt.close(fig_det)

    logger.info("Plots saved to %s", fig_dir)


def generate_report_markdown(
    metrics: Dict[str, Any],
    model_name: str,
    model_path: str,
    dataset_name: str,
    out_dir: Path,
) -> Path:
    """Generate a Markdown evaluation report."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{model_name}_report.md"

    lines = [
        f"# Evaluation Report: {model_name}",
        "",
        f"- **Model**: `{model_path}`",
        f"- **Dataset**: {dataset_name}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]
    for key in ["accuracy", "precision", "recall", "f1", "auc", "eer", "far_at_frr_1pct"]:
        val = metrics.get(key, "N/A")
        if isinstance(val, float):
            val = f"{val:.4f}"
        lines.append(f"| {key} | {val} |")

    lines += [
        "",
        "## Threshold Table",
        "",
        "| Target FRR | Actual FRR | FAR | Threshold |",
        "|-----------|------------|-----|-----------|",
    ]
    for row in metrics.get("threshold_table", []):
        lines.append(
            f"| {row['target_frr']:.3f} | {row['actual_frr']:.4f} | "
            f"{row['far']:.4f} | {row['threshold']:.4f} |"
        )

    lines += [
        "",
        "## Confusion Matrix",
        "",
        "```",
        f"  {metrics.get('confusion_matrix', 'N/A')}",
        "```",
        "",
        "## Plots",
        "",
        f"- Confusion matrix: `figures/{model_name}_confusion_matrix.png`",
        f"- ROC curve: `figures/{model_name}_roc.png`",
        f"- DET curve: `figures/{model_name}_det.png`",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Report saved: %s", report_path)
    return report_path


# ------------------------------------------------------------------ #
# Evaluation entrypoints
# ------------------------------------------------------------------ #

def evaluate_sra(model_path: Path, dataset, out_dir: Path, dataset_name: str) -> Dict[str, Any]:
    """Evaluate an SRA model."""
    data = load_sra_model(model_path)
    sra_model = data["model"]
    feature_type = data.get("feature_type", "proposed_regularized_complex_log_fft")

    X, y = extract_features(dataset, feature_type, flatten=True)

    # Use a fixed test split for evaluation
    _, test_idx = dataset.train_test_split(method="half", seed=42)
    X_test, y_test = X[test_idx], y[test_idx]

    scores = sra_model.decision_function(X_test)
    y_pred = sra_model.predict(X_test)

    metrics = compute_full_metrics(y_test, y_pred, scores)

    model_name = model_path.stem
    save_plots(metrics, model_name, out_dir)
    generate_report_markdown(metrics, model_name, str(model_path), dataset_name, out_dir)

    # Save raw metrics JSON
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{model_name}_metrics.json"
    # Strip non-serialisable items for JSON
    json_safe = {k: v for k, v in metrics.items() if k != "roc"}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_safe, f, indent=2, ensure_ascii=False)

    return metrics


def evaluate_cnn(model_path: Path, dataset, out_dir: Path, dataset_name: str) -> Dict[str, Any]:
    """Evaluate a CNN model."""
    import torch
    from torch.utils.data import DataLoader

    from radar_drone_vision.torch_models.datasets import MicroDopplerDataset

    data = load_cnn_model(model_path)
    model = data["model"]
    feature_type = data.get("feature_type", "proposed_complex_image")

    X, y = extract_features(dataset, feature_type, flatten=False)

    # Reshape for CNN
    if "complex_image" in feature_type and X.ndim == 3:
        n, h, w = X.shape
        half_w = w // 2
        X = np.stack([X[:, :, :half_w], X[:, :, half_w:]], axis=1)
    elif X.ndim == 3:
        X = X[:, np.newaxis, :, :]

    # Use latter half as test set
    _, test_idx = dataset.train_test_split(method="half", seed=42)
    X_test, y_test = X[test_idx], y[test_idx]

    test_ds = MicroDopplerDataset(X_test, y_test)
    test_loader = DataLoader(test_ds, batch_size=64, shuffle=False)

    device = torch.device("cpu")
    model = model.to(device)
    model.eval()

    # Get scores (softmax probabilities for class 1)
    all_scores = []
    all_preds = []
    all_labels = []
    with torch.no_grad():
        for xb, yb in test_loader:
            xb = xb.to(device)
            logits = model(xb)
            probs = torch.softmax(logits, dim=1)
            all_scores.extend(probs[:, 1].cpu().numpy())
            all_preds.extend(logits.argmax(dim=1).cpu().numpy())
            all_labels.extend(yb.numpy())

    y_test_np = np.array(all_labels)
    y_pred_np = np.array(all_preds)
    scores_np = np.array(all_scores)

    metrics = compute_full_metrics(y_test_np, y_pred_np, scores_np)

    model_name = model_path.stem
    save_plots(metrics, model_name, out_dir)
    generate_report_markdown(metrics, model_name, str(model_path), dataset_name, out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{model_name}_metrics.json"
    json_safe = {k: v for k, v in metrics.items() if k != "roc"}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_safe, f, indent=2, ensure_ascii=False)

    return metrics


def evaluate_model(model_path: Path, dataset, out_dir: Path, dataset_name: str) -> Dict[str, Any]:
    """Auto-detect model type and evaluate."""
    mtype = detect_model_type(model_path)
    logger.info("Evaluating %s model: %s", mtype.upper(), model_path)
    if mtype == "sra":
        return evaluate_sra(model_path, dataset, out_dir, dataset_name)
    elif mtype in ("cnn", "onnx"):
        return evaluate_cnn(model_path, dataset, out_dir, dataset_name)
    else:
        raise ValueError(f"Unsupported model type: {mtype}")


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def run_evaluate(args: argparse.Namespace) -> None:
    dataset = load_dataset(args.dataset, _PROJECT_ROOT)
    out_dir = Path(args.out) if args.out else _PROJECT_ROOT / "reports" / "eval"

    if args.all:
        # Find all models in models/
        models_dir = _PROJECT_ROOT / "models"
        if not models_dir.exists():
            print(f"\n[ERROR] Models directory not found: {models_dir}")
            sys.exit(1)
        model_files = sorted(
            p for p in models_dir.iterdir()
            if p.suffix in (".joblib", ".pt", ".pth")
        )
        if not model_files:
            print(f"\n[INFO] No model files found in {models_dir}")
            sys.exit(0)

        print(f"\nFound {len(model_files)} model(s) to evaluate:")
        for mf in model_files:
            print(f"  - {mf.name}")

        all_results = {}
        for mf in model_files:
            try:
                metrics = evaluate_model(mf, dataset, out_dir, args.dataset)
                all_results[mf.name] = metrics
                print(f"\n  {mf.name}: EER={metrics['eer']:.4f}  F1={metrics['f1']:.4f}")
            except Exception as e:
                logger.error("Failed to evaluate %s: %s", mf.name, e)

        # Summary
        if all_results:
            print("\n" + "=" * 70)
            print("  Evaluation Summary (all models)")
            print("=" * 70)
            print(f"  {'Model':<30s} {'EER':>8s} {'F1':>8s} {'AUC':>8s} {'FAR@1%':>8s}")
            print("-" * 64)
            for name, m in all_results.items():
                print(
                    f"  {name:<30s} {m['eer']:>8.4f} {m['f1']:>8.4f} "
                    f"{m.get('auc', 0):>8.4f} {m['far_at_frr_1pct']:>8.4f}"
                )
            print("=" * 70)
    else:
        if not args.model:
            print("\n[ERROR] Specify --model <path> or use --all")
            sys.exit(1)
        model_path = Path(args.model)
        if not model_path.exists():
            print(f"\n[ERROR] Model not found: {model_path}")
            sys.exit(1)
        metrics = evaluate_model(model_path, dataset, out_dir, args.dataset)
        print("\n" + "=" * 60)
        print(f"  Evaluation Results: {model_path.name}")
        print("=" * 60)
        for k in ["accuracy", "precision", "recall", "f1", "auc", "eer", "far_at_frr_1pct"]:
            print(f"  {k:<20s} {metrics.get(k, 0):>10.4f}")
        print("=" * 60)
        print(f"\n  Output: {out_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate trained radar micro-Doppler models.")
    parser.add_argument("--model", type=str, default=None, help="Path to model file (.joblib or .pt)")
    parser.add_argument("--all", action="store_true", help="Evaluate all models in models/ dir")
    parser.add_argument("--dataset", type=str, default="zenodo77", help="Dataset name")
    parser.add_argument("--out", type=str, default=None, help="Output directory for reports")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser.parse_args()


if __name__ == "__main__":
    run_evaluate(parse_args())
