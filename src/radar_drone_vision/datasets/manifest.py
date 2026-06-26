"""Dataset manifest manager.

Manages ``manifest.parquet`` files that track processed dataset contents,
class distributions, and per-sample metadata.

Processed dataset layout::

    data/processed/{name}/
        manifest.parquet
        samples/
            000000.npz
            000001.npz
            ...

Each ``.npz`` may contain (all optional except ``label``):
    iq, adc, range_doppler, micro_doppler, label, label_name,
    timestamp, range_m, azimuth_deg, elevation_deg, velocity_mps, track_id
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .base import RadarSample

logger = logging.getLogger(__name__)


class DatasetManifest:
    """Create, save, and load a dataset manifest (parquet).

    Parameters
    ----------
    name : str
        Human-readable dataset name.
    base_dir : str | Path
        Root directory for this processed dataset
        (e.g. ``data/processed/zenodo_77ghz``).
    """

    # Columns always present in the manifest
    _REQUIRED_COLS = ("sample_id", "file", "label", "label_binary")

    def __init__(self, name: str, base_dir: str | Path) -> None:
        self.name = name
        self.base_dir = Path(base_dir)
        self.samples_dir = self.base_dir / "samples"
        self.manifest_path = self.base_dir / "manifest.parquet"
        self._df: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # Build from RadarSamples
    # ------------------------------------------------------------------

    def build_from_samples(
        self,
        samples: Sequence[RadarSample],
        extra_columns: Optional[Dict[str, list]] = None,
    ) -> pd.DataFrame:
        """Save samples as ``.npz`` files and build the manifest DataFrame.

        Parameters
        ----------
        samples : sequence of RadarSample
        extra_columns : dict
            Additional columns to attach (e.g. ``{"split": [...]}``).
        """
        self.samples_dir.mkdir(parents=True, exist_ok=True)

        records: list[dict] = []
        for i, s in enumerate(samples):
            fname = f"{i:06d}.npz"
            fpath = self.samples_dir / fname

            npz_dict = s.to_npz_dict()
            # Add optional spatial / kinematic arrays
            for key in ("iq", "adc", "range_doppler", "micro_doppler"):
                val = s.metadata.get(key)
                if val is not None:
                    npz_dict[key] = np.asarray(val)

            np.savez(fpath, **npz_dict)

            rec: dict = {
                "sample_id": s.sample_id,
                "file": fname,
                "label": s.label,
                "label_binary": s.label_binary,
                "radar_type": s.radar_type,
                "carrier_frequency_hz": s.carrier_frequency_hz,
            }
            for attr in ("range_m", "azimuth_deg", "elevation_deg", "velocity_mps", "track_id", "timestamp"):
                val = getattr(s, attr, None)
                if val is not None:
                    rec[attr] = val
            records.append(rec)

        df = pd.DataFrame(records)

        if extra_columns:
            for col, values in extra_columns.items():
                if len(values) == len(df):
                    df[col] = values

        self._df = df
        return df

    # ------------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------------

    def save(self) -> Path:
        """Write manifest to parquet."""
        if self._df is None:
            raise RuntimeError("No manifest data to save. Call build_from_samples() first.")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._df.to_parquet(self.manifest_path, index=False)
        logger.info("Saved manifest (%d rows) to %s", len(self._df), self.manifest_path)
        return self.manifest_path

    def load(self) -> pd.DataFrame:
        """Load manifest from parquet."""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {self.manifest_path}")
        self._df = pd.read_parquet(self.manifest_path)
        logger.info("Loaded manifest (%d rows) from %s", len(self._df), self.manifest_path)
        return self._df

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            return self.load()
        return self._df

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return summary statistics for the manifest."""
        df = self.df
        class_dist = df["label"].value_counts().to_dict()
        binary_dist = df["label_binary"].value_counts().to_dict()
        info: dict = {
            "name": self.name,
            "num_samples": len(df),
            "num_classes": df["label"].nunique(),
            "class_distribution": class_dist,
            "binary_distribution": {
                "uav": binary_dist.get(1, 0),
                "non_uav": binary_dist.get(0, 0),
            },
            "columns": list(df.columns),
        }
        if "split" in df.columns:
            info["split_distribution"] = df["split"].value_counts().to_dict()
        return info

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_split(self, split: str) -> pd.DataFrame:
        """Return rows for a given split (train / test / val)."""
        if "split" not in self.df.columns:
            raise KeyError("Manifest has no 'split' column.")
        return self.df[self.df["split"] == split].reset_index(drop=True)

    def get_class(self, label: str) -> pd.DataFrame:
        return self.df[self.df["label"] == label].reset_index(drop=True)

    def load_sample(self, idx: int) -> dict:
        """Load the ``.npz`` file for the given manifest row index."""
        row = self.df.iloc[idx]
        fpath = self.samples_dir / row["file"]
        return dict(np.load(str(fpath), allow_pickle=True))

    def iter_samples(self, indices: Optional[Sequence[int]] = None):
        """Yield (row_dict, npz_dict) for the given indices (default: all)."""
        if indices is None:
            indices = range(len(self.df))
        for i in indices:
            row = self.df.iloc[i].to_dict()
            npz = self.load_sample(i)
            yield row, npz
