"""PyTorch Dataset for micro-Doppler radar images."""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import torch
from torch.utils.data import Dataset


class MicroDopplerDataset(Dataset):
    """Dataset wrapper for micro-Doppler feature arrays.

    Parameters
    ----------
    features : np.ndarray
        2-D or higher array of shape ``(N, ...)`` — images or feature vectors.
    labels : np.ndarray
        1-D integer array of length *N* (0 = non-UAV, 1 = UAV).
    transform : callable, optional
        Applied to each sample tensor **after** conversion to ``torch.Tensor``.
    """

    def __init__(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        transform: Optional[Callable] = None,
    ) -> None:
        if features is None or labels is None:
            raise ValueError("features and labels must not be None")
        self.features = np.asarray(features, dtype=np.float32)
        self.labels = np.asarray(labels, dtype=np.int64)
        if len(self.features) != len(self.labels):
            raise ValueError(
                f"features ({len(self.features)}) and labels ({len(self.labels)}) "
                "must have the same length"
            )
        self.transform = transform

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int):
        x = torch.from_numpy(self.features[idx])
        y = torch.tensor(self.labels[idx], dtype=torch.long)

        # If 2-D image without channel dim, add one: (H, W) -> (1, H, W)
        if x.ndim == 2:
            x = x.unsqueeze(0)

        if self.transform is not None:
            x = self.transform(x)

        return x, y
