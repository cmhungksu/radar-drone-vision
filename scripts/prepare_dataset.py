#!/usr/bin/env python3
"""Prepare a raw radar dataset into the unified processed format.

Processed layout::

    data/processed/{name}/
        manifest.parquet
        samples/
            000000.npz
            000001.npz
            ...

Usage:
    python scripts/prepare_dataset.py --dataset zenodo77 \\
        --config configs/datasets/zenodo77.yaml

    python scripts/prepare_dataset.py --dataset synthetic --n-per-class 200
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

# Ensure the package is importable when running from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from radar_drone_vision.datasets import (  # noqa: E402
    DatasetManifest,
    SyntheticGenerator,
    Zenodo77Dataset,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load_config(config_path: str | None) -> dict:
    if config_path is None:
        return {}
    p = Path(config_path)
    if not p.exists():
        logger.warning("Config file not found: %s — using defaults", p)
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Zenodo 77 GHz
# ---------------------------------------------------------------------------


def prepare_zenodo77(config: dict, out_dir: Path) -> None:
    ds_cfg = config.get("dataset", {})
    raw_dir = Path(config.get("raw_dir", "data/raw/zenodo_77ghz"))

    logger.info("Loading Zenodo 77 GHz dataset from %s", raw_dir)
    dataset = Zenodo77Dataset(raw_dir)

    # Split
    split_cfg = config.get("split", {})
    method = split_cfg.get("method", "half")
    test_ratio = split_cfg.get("test_ratio", 0.5)
    stratify = split_cfg.get("stratify", True)
    seed = config.get("seed", 42)

    train_idx, test_idx = dataset.train_test_split(
        method=method, test_ratio=test_ratio, seed=seed, stratify=stratify
    )

    logger.info("Split: %d train, %d test", len(train_idx), len(test_idx))

    # Collect all samples in order, with split labels
    all_indices = train_idx + test_idx
    split_labels = ["train"] * len(train_idx) + ["test"] * len(test_idx)

    samples = dataset.get_by_indices(all_indices)

    # Build manifest
    name = ds_cfg.get("name", "zenodo_77ghz_fmcw")
    manifest = DatasetManifest(name=name, base_dir=out_dir)
    manifest.build_from_samples(samples, extra_columns={"split": split_labels})
    manifest.save()

    stats = manifest.stats()
    logger.info("Dataset stats: %s", stats)
    logger.info("Processed dataset saved to %s", out_dir)


# ---------------------------------------------------------------------------
# Synthetic
# ---------------------------------------------------------------------------


def prepare_synthetic(config: dict, out_dir: Path, n_per_class: int = 200) -> None:
    seed = config.get("seed", 42)
    gen = SyntheticGenerator(seed=seed)
    samples = gen.generate_balanced_dataset(n_per_class=n_per_class)

    # Simple 50/50 split
    half = len(samples) // 2
    split_labels = ["train"] * half + ["test"] * (len(samples) - half)

    manifest = DatasetManifest(name="synthetic", base_dir=out_dir)
    manifest.build_from_samples(samples, extra_columns={"split": split_labels})
    manifest.save()

    stats = manifest.stats()
    logger.info("Synthetic dataset stats: %s", stats)
    logger.info("Processed dataset saved to %s", out_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare radar dataset into processed format")
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        choices=["zenodo77", "synthetic"],
        help="Dataset to prepare",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to dataset config YAML (e.g. configs/datasets/zenodo77.yaml)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output directory (default: data/processed/{dataset})",
    )
    parser.add_argument(
        "--n-per-class",
        type=int,
        default=200,
        help="Samples per class for synthetic dataset (default: 200)",
    )
    args = parser.parse_args()

    config = _load_config(args.config)
    out_dir = Path(args.out) if args.out else Path(f"data/processed/{args.dataset}")

    if args.dataset == "zenodo77":
        prepare_zenodo77(config, out_dir)
    elif args.dataset == "synthetic":
        prepare_synthetic(config, out_dir, n_per_class=args.n_per_class)
    else:
        logger.error("Unknown dataset: %s", args.dataset)
        sys.exit(1)


if __name__ == "__main__":
    main()
