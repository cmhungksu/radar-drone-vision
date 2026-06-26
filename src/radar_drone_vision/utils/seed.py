"""Reproducibility helpers."""

from __future__ import annotations

import random


def set_seed(seed: int = 42) -> None:
    """Set random seed for Python, NumPy, and PyTorch for reproducibility.

    Parameters
    ----------
    seed : int
        The random seed value.
    """
    random.seed(seed)

    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass

    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except ImportError:
        pass
