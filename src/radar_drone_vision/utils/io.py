"""File I/O helpers for arrays and JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def ensure_dir(path: str | Path) -> Path:
    """Create directory (and parents) if it does not exist. Returns the Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_npz(path: str | Path, **arrays: np.ndarray) -> None:
    """Save numpy arrays to a compressed ``.npz`` file.

    Parameters
    ----------
    path : str or Path
        Destination file path.
    **arrays
        Keyword arguments mapping array names to ``np.ndarray`` values.
    """
    p = Path(path)
    ensure_dir(p.parent)
    np.savez_compressed(str(p), **arrays)


def load_npz(path: str | Path) -> dict[str, np.ndarray]:
    """Load a ``.npz`` file and return its contents as a plain dict.

    Parameters
    ----------
    path : str or Path
        Source ``.npz`` file path.

    Returns
    -------
    dict[str, np.ndarray]
        Mapping of array names to arrays.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"NPZ file not found: {p}")
    with np.load(str(p), allow_pickle=False) as data:
        return dict(data)


def save_json(path: str | Path, data: Any) -> None:
    """Save *data* as a JSON file with pretty-printing.

    Parameters
    ----------
    path : str or Path
        Destination file path.
    data
        JSON-serialisable object.
    """
    p = Path(path)
    ensure_dir(p.parent)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: str | Path) -> Any:
    """Load and parse a JSON file.

    Parameters
    ----------
    path : str or Path
        Source JSON file path.

    Returns
    -------
    Any
        The parsed JSON data.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"JSON file not found: {p}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)
