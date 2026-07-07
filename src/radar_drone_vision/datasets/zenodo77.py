"""Zenodo 77 GHz FMCW radar dataset loader.

Dataset DOI: 10.5281/zenodo.5845259
Sensor: 77 GHz FMCW radar (SAAB SIRS 1600)
Total segments: 75,868
Classes: 6 drone types, 2 human types, 6 bird types, 1 corner reflector

Data structure (130 x 6 object array):
  Column 0: class label string (e.g. 'D1', 'seagull', 'human_walk')
  Column 1: complex IQ matrix (1280 x N_segments), each segment = 5 range cells x 256 azimuth
  Column 2: range in meters (N_segments x 1)
  Column 3: time in seconds (N_segments x 1)
  Column 4: train/val/test split indicator (1/2/3) (N_segments x 1)
  Column 5: edge indicator (0/1) (N_segments x 1)
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

# Class mapping: which labels are UAV
_UAV_LABELS = {"D1", "D2", "D3", "D4", "D5", "D6"}
_BIRD_LABELS = {
    "seagull", "pigeon", "raven", "black-headed gull",
    "seagull and black-headed gull", "heron",
}
_HUMAN_LABELS = {"human_walk", "human_run"}
_OTHER_LABELS = {"CR"}


def _is_uav(label_name: str) -> bool:
    return label_name in _UAV_LABELS


class Zenodo77Dataset:
    """Loader for the Zenodo 77 GHz FMCW radar dataset.

    Each segment is a 1280-element complex vector (5 range cells x 256 azimuth sweeps).

    Parameters
    ----------
    data_dir : str | Path
        Directory containing data_SAAB_SIRS_77GHz_FMCW.npy and ReadMe.txt.
    include_edge : bool
        If False, exclude segments near field-of-view edges (column 5 == 1).
    include_cr : bool
        If False, exclude corner reflector measurements.
    """

    def __init__(
        self,
        data_dir: str | Path,
        include_edge: bool = True,
        include_cr: bool = False,
    ) -> None:
        self.data_dir = Path(data_dir)
        self._npy_path = self.data_dir / DATA_FILENAME

        if not self._npy_path.exists():
            raise FileNotFoundError(
                f"Dataset file not found: {self._npy_path}\n"
                f"Run: python scripts/download_zenodo.py --out {self.data_dir}"
            )

        logger.info("Loading %s …", self._npy_path)
        raw = np.load(str(self._npy_path), allow_pickle=True)
        # raw: (130, 6) object array

        # Flatten all measurements into individual segments
        signals = []       # complex64 vectors of length 1280
        labels = []        # string class labels
        ranges_m = []      # range in meters
        times_s = []       # time in seconds
        split_ids = []     # 1=train, 2=val, 3=test (from paper)
        edge_flags = []    # 1 if near edge

        for row_idx in range(raw.shape[0]):
            class_label = str(np.asarray(raw[row_idx, 0]).flat[0])

            if not include_cr and class_label == "CR":
                continue

            iq_matrix = np.asarray(raw[row_idx, 1])   # (1280, N)
            range_arr = np.asarray(raw[row_idx, 2]).flatten()  # (N,)
            time_arr = np.asarray(raw[row_idx, 3]).flatten()   # (N,)
            split_arr = np.asarray(raw[row_idx, 4]).flatten()  # (N,)
            edge_arr = np.asarray(raw[row_idx, 5]).flatten()   # (N,)

            n_segments = iq_matrix.shape[1]

            for seg_idx in range(n_segments):
                if not include_edge and int(edge_arr[seg_idx]) == 1:
                    continue

                signals.append(iq_matrix[:, seg_idx])
                labels.append(class_label)
                ranges_m.append(float(range_arr[seg_idx]))
                times_s.append(float(time_arr[seg_idx]))
                split_ids.append(int(split_arr[seg_idx]))
                edge_flags.append(int(edge_arr[seg_idx]))

        # Stack into single contiguous array instead of list of arrays
        # This saves ~2GB Python object overhead for 72k samples
        self._signals = np.array(signals)      # (N, 1280) complex128
        self._labels = labels                  # list of str
        self._ranges_m = np.array(ranges_m)
        self._times_s = np.array(times_s)
        self._split_ids = np.array(split_ids)
        self._edge_flags = np.array(edge_flags)
        self._n_samples = len(labels)

        # Release the raw .npy from memory
        del raw

        # Binary labels
        self._labels_binary = np.array([1 if _is_uav(l) else 0 for l in labels])

        logger.info(
            "Loaded %d segments: %d UAV, %d non-UAV",
            self._n_samples,
            int(self._labels_binary.sum()),
            int(self._n_samples - self._labels_binary.sum()),
        )

    def __len__(self) -> int:
        return self._n_samples

    def __getitem__(self, idx: int) -> RadarSample:
        if idx < 0 or idx >= self._n_samples:
            raise IndexError(f"Index {idx} out of range [0, {self._n_samples})")

        signal = self._signals[idx]
        label_name = self._labels[idx]

        return RadarSample(
            sample_id=f"zenodo77_{idx:06d}",
            signal=signal,
            label=label_name,
            label_binary=1 if _is_uav(label_name) else 0,
            radar_type=RADAR_TYPE,
            carrier_frequency_hz=CARRIER_FREQ_HZ,
            raw_shape=signal.shape,
            metadata={
                "dataset": "zenodo_77ghz_fmcw",
                "doi": DOI,
                "range_m": float(self._ranges_m[idx]),
                "time_s": float(self._times_s[idx]),
                "split_id": int(self._split_ids[idx]),
                "edge_flag": int(self._edge_flags[idx]),
            },
        )

    def get_all(self) -> List[RadarSample]:
        return [self[i] for i in range(self._n_samples)]

    def get_by_indices(self, indices: Sequence[int]) -> List[RadarSample]:
        return [self[i] for i in indices]

    def class_distribution(self) -> dict[str, int]:
        from collections import Counter
        return dict(Counter(self._labels))

    def get_signals_and_labels(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return (signals, binary_labels) as numpy arrays.

        signals: (N, 1280) complex128
        labels: (N,) int  (1=UAV, 0=non-UAV)
        """
        # _signals is already a contiguous ndarray, no copy needed
        return self._signals, self._labels_binary

    def train_test_split(
        self,
        method: str = "half",
        test_ratio: float = 0.5,
        seed: int = 42,
        stratify: bool = True,
        use_paper_split: bool = False,
    ) -> Tuple[List[int], List[int]]:
        """Return (train_indices, test_indices).

        Parameters
        ----------
        method : 'half' or 'ratio'
        use_paper_split : bool
            If True, use the original paper's train/val/test split from column 4.
            Train = split_id 1, Test = split_id 2+3.
        """
        indices = np.arange(self._n_samples)

        if use_paper_split:
            train_idx = indices[self._split_ids == 1].tolist()
            test_idx = indices[np.isin(self._split_ids, [2, 3])].tolist()
            return train_idx, test_idx

        rng = np.random.default_rng(seed)
        if stratify:
            train_idx = []
            test_idx = []
            for cls_name in sorted(set(self._labels)):
                cls_mask = np.array([l == cls_name for l in self._labels])
                cls_indices = indices[cls_mask].copy()
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
