"""Disk-backed cache for computed feature matrices."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np


class FeatureStore:
    """Simple file-system cache for ``(X, y)`` feature arrays.

    Each entry is stored as a directory containing:
    - ``X.npy`` -- feature matrix
    - ``y.npy`` -- label vector
    - ``metadata.json`` -- arbitrary metadata dict

    Parameters
    ----------
    cache_dir : str or Path
        Root directory for the cache.  Created on first write.
    """

    def __init__(self, cache_dir: str = "data/cache") -> None:
        self.cache_dir = Path(cache_dir)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def save(
        self,
        key: str,
        X: np.ndarray,
        y: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Persist a feature set to disk.

        Parameters
        ----------
        key : str
            Unique identifier (e.g. ``"spectrogram_256_hann"``).
        X : np.ndarray
            Feature matrix ``(n_samples, n_features)``.
        y : np.ndarray
            Label vector ``(n_samples,)``.
        metadata : dict, optional
            Additional information to store alongside the arrays.

        Returns
        -------
        entry_dir : Path
            Directory where the entry was written.
        """
        entry_dir = self._key_dir(key)
        entry_dir.mkdir(parents=True, exist_ok=True)

        np.save(entry_dir / "X.npy", X)
        np.save(entry_dir / "y.npy", y)

        meta = metadata if metadata is not None else {}
        meta["key"] = key
        meta["X_shape"] = list(X.shape)
        meta["y_shape"] = list(y.shape)
        with open(entry_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        return entry_dir

    def load(self, key: str) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """Load a cached feature set.

        Returns
        -------
        X, y, metadata
        """
        entry_dir = self._key_dir(key)
        if not entry_dir.exists():
            raise FileNotFoundError(f"No cache entry for key '{key}'")

        X = np.load(entry_dir / "X.npy")
        y = np.load(entry_dir / "y.npy")
        with open(entry_dir / "metadata.json", "r", encoding="utf-8") as f:
            metadata = json.load(f)

        return X, y, metadata

    def exists(self, key: str) -> bool:
        """Return *True* if a cache entry for *key* is present."""
        entry_dir = self._key_dir(key)
        return (entry_dir / "X.npy").exists() and (entry_dir / "y.npy").exists()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _key_dir(self, key: str) -> Path:
        """Map a key string to a filesystem-safe directory name."""
        safe = key.replace("/", "_").replace("\\", "_").replace(" ", "_")
        return self.cache_dir / safe
