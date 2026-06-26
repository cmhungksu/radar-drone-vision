#!/usr/bin/env python3
"""Generate paper comparison report from evaluation results.

Usage:
    python scripts/export_report.py --out reports/paper_comparison.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("export_report")


# ------------------------------------------------------------------ #
# Paper reference values (NOT reproduced — from original publication)
# ------------------------------------------------------------------ #

PAPER_REFERENCE_RESULTS: List[Dict[str, Any]] = [
    {
        "method": "Spectrogram + PCA",
        "feature": "spectrogram",
        "classifier": "PCA/Mahalanobis",
        "dataset": "X-band CW (paper)",
        "eer": "~5.0%",
        "far_at_frr_1pct": "N/A",
        "source": "Paper Table II (original CW dataset)",
        "reproduced": False,
    },
    {
        "method": "Cepstrogram + PCA",
        "feature": "cepstrogram",
        "classifier": "PCA/Mahalanobis",
        "dataset": "X-band CW (paper)",
        "eer": "~4.5%",
        "far_at_frr_1pct": "N/A",
        "source": "Paper Table II (original CW dataset)",
        "reproduced": False,
    },
    {
        "method": "CVD + PCA",
        "feature": "CVD",
        "classifier": "PCA/Mahalanobis",
        "dataset": "X-band CW (paper)",
        "eer": "~4.0%",
        "far_at_frr_1pct": "N/A",
        "source": "Paper Table II (original CW dataset)",
        "reproduced": False,
    },
    {
        "method": "Proposed + PCA",
        "feature": "regularized complex-log FFT",
        "classifier": "PCA/Mahalanobis",
        "dataset": "X-band CW (paper)",
        "eer": "~2.0%",
        "far_at_frr_1pct": "N/A",
        "source": "Paper Table II (original CW dataset)",
        "reproduced": False,
    },
    {
        "method": "Proposed + SRA",
        "feature": "regularized complex-log FFT",
        "classifier": "SRA",
        "dataset": "X-band CW (paper)",
        "eer": "~0.92%",
        "far_at_frr_1pct": "~0.5%",
        "source": "Paper Table II (original CW dataset)",
        "reproduced": False,
    },
]


# ------------------------------------------------------------------ #
# Load evaluation results from disk
# ------------------------------------------------------------------ #

def find_eval_results(reports_dir: Path) -> List[Dict[str, Any]]:
    """Scan reports/ for *_metrics.json files."""
    results = []
    if not reports_dir.exists():
        return results

    for json_file in sorted(reports_dir.rglob("*_metrics.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            model_name = json_file.stem.replace("_metrics", "")
            results.append({
                "model_name": model_name,
                "file": str(json_file),
                "metrics": data,
            })
        except Exception as e:
            logger.warning("Failed to load %s: %s", json_file, e)

    return results


def infer_method_info(model_name: str, metrics: Dict[str, Any]) -> Dict[str, str]:
    """Infer feature/classifier from model name."""
    name = model_name.lower()
    if "sra" in name:
        return {
            "method": "Proposed + SRA",
            "feature": "regularized complex-log FFT",
            "classifier": "SRA",
        }
    elif "cnn" in name:
        return {
            "method": "Proposed + CNN",
            "feature": "complex image (2-ch)",
            "classifier": "SmallRadarCNN",
        }
    else:
        return {
            "method": model_name,
            "feature": "unknown",
            "classifier": "unknown",
        }


# ------------------------------------------------------------------ #
# Report generation
# ------------------------------------------------------------------ #

def generate_comparison_report(
    eval_results: List[Dict[str, Any]],
    out_path: Path,
    dataset_name: str = "Zenodo 77 GHz FMCW",
) -> None:
    """Generate the full comparison Markdown report."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []

    lines.append("# Paper Comparison Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## Reference")
    lines.append("")
    lines.append(
        "> **Paper**: \"Regularized 2-D Complex-Log Spectral Analysis and "
        "Subspace Reliability Analysis of Micro-Doppler Signature for UAV Detection\""
    )
    lines.append(">")
    lines.append("> **Original dataset**: X-band CW radar (not publicly available)")
    lines.append(">")
    lines.append(
        f"> **Reproduction dataset**: {dataset_name} "
        "(DOI: 10.5281/zenodo.5845259 — 77 GHz FMCW, different sensor/band)"
    )
    lines.append("")
    lines.append(
        "**Note**: Results on the Zenodo dataset are for *algorithm validation* only. "
        "They are not directly comparable to the paper's original results due to "
        "differences in sensor type, frequency band, and target characteristics."
    )
    lines.append("")

    # Paper reference table
    lines.append("## Paper Results (reference — NOT reproduced)")
    lines.append("")
    lines.append(
        "| Method | Feature | Classifier | Dataset | EER | FAR@FRR=1% | Notes |"
    )
    lines.append(
        "|--------|---------|------------|---------|-----|-----------|-------|"
    )
    for row in PAPER_REFERENCE_RESULTS:
        lines.append(
            f"| {row['method']} | {row['feature']} | {row['classifier']} | "
            f"{row['dataset']} | {row['eer']} | {row['far_at_frr_1pct']} | "
            f"{row['source']} |"
        )
    lines.append("")

    # Reproduced results table
    if eval_results:
        lines.append(f"## Reproduced Results ({dataset_name})")
        lines.append("")
        lines.append(
            "| Method | Feature | Classifier | Dataset | EER | FAR@FRR=1% | F1 | AUC | Notes |"
        )
        lines.append(
            "|--------|---------|------------|---------|-----|-----------|----|----|-------|"
        )

        for entry in eval_results:
            m = entry["metrics"]
            info = infer_method_info(entry["model_name"], m)
            eer = m.get("eer", None)
            eer_str = f"{eer:.4f}" if isinstance(eer, (int, float)) else str(eer or "N/A")
            far = m.get("far_at_frr_1pct", None)
            far_str = f"{far:.4f}" if isinstance(far, (int, float)) else str(far or "N/A")
            f1 = m.get("f1", None)
            f1_str = f"{f1:.4f}" if isinstance(f1, (int, float)) else str(f1 or "N/A")
            auc = m.get("auc", None)
            auc_str = f"{auc:.4f}" if isinstance(auc, (int, float)) else str(auc or "N/A")

            lines.append(
                f"| {info['method']} | {info['feature']} | {info['classifier']} | "
                f"{dataset_name} | {eer_str} | {far_str} | {f1_str} | {auc_str} | "
                f"Reproduced on different sensor |"
            )
        lines.append("")
    else:
        lines.append("## Reproduced Results")
        lines.append("")
        lines.append(
            "*No evaluation results found.* Run `python scripts/evaluate.py --all` first."
        )
        lines.append("")

    # Detailed per-model results
    if eval_results:
        lines.append("## Detailed Results")
        lines.append("")
        for entry in eval_results:
            m = entry["metrics"]
            lines.append(f"### {entry['model_name']}")
            lines.append("")
            lines.append(f"- Source: `{entry['file']}`")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            for key in ["accuracy", "precision", "recall", "f1", "auc", "eer",
                         "eer_threshold", "far_at_frr_1pct"]:
                val = m.get(key, "N/A")
                if isinstance(val, float):
                    val = f"{val:.4f}"
                lines.append(f"| {key} | {val} |")
            lines.append("")

            # Threshold table
            tt = m.get("threshold_table", [])
            if tt:
                lines.append("**Threshold operating points:**")
                lines.append("")
                lines.append("| Target FRR | Actual FRR | FAR | Threshold |")
                lines.append("|-----------|------------|-----|-----------|")
                for row in tt:
                    lines.append(
                        f"| {row['target_frr']:.3f} | {row['actual_frr']:.4f} | "
                        f"{row['far']:.4f} | {row['threshold']:.4f} |"
                    )
                lines.append("")

            # Confusion matrix
            cm = m.get("confusion_matrix")
            if cm:
                lines.append("**Confusion matrix** (rows=true, cols=predicted):")
                lines.append("")
                lines.append("```")
                lines.append(f"           pred-nonUAV  pred-UAV")
                if len(cm) == 2 and len(cm[0]) == 2:
                    lines.append(f"true-nonUAV    {cm[0][0]:>7d}    {cm[0][1]:>7d}")
                    lines.append(f"true-UAV       {cm[1][0]:>7d}    {cm[1][1]:>7d}")
                else:
                    lines.append(str(cm))
                lines.append("```")
                lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        "*This report was generated by `scripts/export_report.py`. "
        "Paper values are reference targets from the original publication and "
        "are clearly marked as not reproduced.*"
    )

    report_text = "\n".join(lines)
    out_path.write_text(report_text, encoding="utf-8")
    logger.info("Report written to: %s", out_path)
    print(f"\n  Report saved: {out_path}")
    print(f"  Lines: {len(lines)}")


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def run_export(args: argparse.Namespace) -> None:
    reports_dir = _PROJECT_ROOT / "reports"
    eval_results = find_eval_results(reports_dir)

    if eval_results:
        print(f"\n  Found {len(eval_results)} evaluation result(s):")
        for r in eval_results:
            print(f"    - {r['model_name']} ({r['file']})")
    else:
        print("\n  No evaluation results found in reports/")
        print("  Paper reference values will still be included.")

    out_path = Path(args.out) if args.out else reports_dir / "paper_comparison.md"

    generate_comparison_report(
        eval_results,
        out_path,
        dataset_name="Zenodo 77 GHz FMCW",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate paper comparison report from evaluation results."
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="Output path for the report (default: reports/paper_comparison.md)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    run_export(parse_args())
