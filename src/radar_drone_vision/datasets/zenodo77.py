"""Zenodo 77 GHz FMCW radar dataset loader.

Dataset DOI: 10.5281/zenodo.5845259
Sensor: 77 GHz FMCW radar (SAAB / SIRS)
Approximate samples: 75 868
Classes: multiple drone types, birds, humans
Binary mapping: drones -> UAV (1), birds/humans -> non-UAV (0)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .base import RadarSample

logger = logging.getLogger(__name__)

DOI = "10.5281/zenodo.5845259"
CARRIER_FREQ_HZ = 77.0e9
RADAR_TYPE = "fmcw"
DATA_FILENAME = "data_SAAB_SIRS_77GHz_FMCW.npy"
README_FILENAME = "ReadMe.txt"

# ---------------------------------------------------------------------------
# Class mapping helpers
# ---------------------------------------------------------------------------

# Known class indices based on the dataset README.
# The .npy file stores (signal, label_index) pairs.
# Label names are inferred from ReadMe.txt; the mapping below is the fallback
# when the readme cannot be parsed.
_DEFAULT_LABEL_NAMES: dict[int, str] = {
    0: "bird",
    1: "drone_DJI_M600",
    2: "drone_DJI_P4",
    3: "drone_DJI_S1000",
    4: "drone_DJI_IN2",
    5: "drone_Align_TREX",
    6: "drone_SwellPro",
    7: "human",
}


def _is_uav(label_name: str) -> bool:
    """Return True if the label represents a UAV / drone class."""
    name_lower = label_name.lower()
    return "drone" in name_lower or "uav" in name_lower


def _parse_readme(readme_path: Path) -> Optional[dict[int, str]]:
    """Try to extract label-name mapping from the Zenodo ReadMe.txt."""
    if not readme_path.exists():
        return None
    try:
        text = readme_path.read_text(encoding="utf-8", errors="replace")
        # Best-effort parse — return None if we cannot find a mapping
        mapping: dict[int, str] = {}
        for line in text.splitlines():
            line = line.strip()
            # Look for lines like "0 - bird" or "0: bird"
            for sep in ["-", ":", "="]:
                if sep in line:
                    parts = line.split(sep, 1)
                    try:
                        idx = int(parts[0].strip())
                        name = parts[1].strip().strip("'\"")
                        if name:
                            mapping[idx] = name
                    except (ValueError, IndexError):
                        continue
        return mapping if mapping else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Dataset loader
# ---------------------------------------------------------------------------


class Zenodo77Dataset:
    """Loader for the Zenodo 77 GHz FMCW radar dataset.

    Parameters
    ----------
    data_dir : str | Path
        Directory containing ``data_SAAB_SIRS_77GHz_FMCW.npy`` (and
        optionally ``ReadMe.txt``).
    """

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self._npy_path = self.data_dir / DATA_FILENAME
        self._readme_path = self.data_dir / README_FILENAME

        if not self._npy_path.exists():
            raise FileNotFoundError(
                f"Dataset file not found: {self._npy_path}\n"
                f"Run `python scripts/download_zenodo.py --out {self.data_dir}` first."
            )

        # Load full dataset into memory (structured numpy array)
        logger.info("Loading %s …", self._npy_path)
        raw = np.load(str(self._npy_path), allow_pickle=True)
        # The file may be a structured array or a plain 2-D array.
        # We normalise to (signals_array, labels_array).
        if raw.dtype.names:
            # Structured array — field names vary across dataset versions
            signal_key = [k for k in raw.dtype.names if k != "label"][0]
            self._signals = np.array([row[signal_key] for row in raw])
            self._labels_idx = np.array([int(row["label"]) for row in raw])
        elif raw.ndim == 1 and isinstance(raw[0], (list, np.ndarray, tuple)):
            # Object array of (signal, label) pairs
            self._signals = np.array([np.asarray(r[0]) for r in raw])
            self._labels_idx = np.array([int(r[-1]) for r in raw])
        else:
            # Plain 2-D: last column is the label
            self._signals = raw[:, :-1]
            self._labels_idx = raw[:, -1].astype(int)

        # Resolve label names
        parsed = _parse_readme(self._readme_path)
        self._label_map: dict[int, str] = parsed if parsed else dict(_DEFAULT_LABEL_NAMES)

        self._n_samples = len(self._labels_idx)
        logger.info(
            "Loaded %d samples, %d unique classes", self._n_samples, len(set(self._labels_idx))
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return self._n_samples

    def __getitem__(self, idx: int) -> RadarSample:
        if idx < 0 or idx >= self._n_samples:
            raise IndexError(f"Index {idx} out of range [0, {self._n_samples})")
        signal = self._signals[idx]
        label_idx = int(self._labels_idx[idx])
        label_name = self._label_map.get(label_idx, f"class_{label_idx}")
        return RadarSample(
            sample_id=f"zenodo77_{idx:06d}",
            signal=np.asarray(signal, dtype=np.float32),
            label=label_name,
            label_binary=1 if _is_uav(label_name) else 0,
            radar_type=RADAR_TYPE,
            carrier_frequency_hz=CARRIER_FREQ_HZ,
            raw_shape=tuple(np.asarray(signal).shape),
            metadata={"dataset": "zenodo_77ghz_fmcw", "class_index": label_idx, "doi": DOI},
        )

    def get_all(self) -> List[RadarSample]:
        """Return every sample as a list of ``RadarSample``."""
        return [self[i] for i in range(self._n_samples)]

    def get_by_indices(self, indices: Sequence[int]) -> List[RadarSample]:
        """Return samples for the given indices."""
        return [self[i] for i in indices]

    def class_distribution(self) -> dict[str, int]:
        """Return {label_name: count}."""
        from collections import Counter

        names = [self._label_map.get(int(l), f"class_{l}") for l in self._labels_idx]
        return dict(Counter(names))

    # ------------------------------------------------------------------
    # Train / test split
    # ------------------------------------------------------------------

    def train_test_split(
        self,
        method: str = "half",
        test_ratio: float = 0.5,
        seed: int = 42,
        stratify: bool = True,
    ) -> Tuple[List[int], List[int]]:
        """Return (train_indices, test_indices).

        Parameters
        ----------
        method : str
            ``'half'`` for 50/50 split (as in the original paper).
        test_ratio : float
            Fraction of data used for testing (only for method='ratio').
        seed : int
            Random seed for reproducibility.
        stratify : bool
            If True, preserve class proportions in each split.
        """
        rng = np.random.default_rng(seed)
        indices = np.arange(self._n_samples)

        if stratify:
            train_idx: list[int] = []
            test_idx: list[int] = []
            for cls in np.unique(self._labels_idx):
                cls_indices = indices[self._labels_idx == cls]
                rng.shuffle(cls_indices)
                n_test = int(len(cls_indices) * test_ratio)
                test_idx.extend(cls_indices[:n_test].tolist())
                train_idx.extend(cls_indices[n_test:].tolist())
        else:
            rng.shuffle(indices)
            n_test = int(self._n_samples * test_ratio)
            test_idx = indices[:n_test].tolist()
            train_idx = indices[n_test:].tolist()

        return train_idx, test_idx
