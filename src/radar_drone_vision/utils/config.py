"""Configuration loading utilities using OmegaConf."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf


def load_config(path: str = "configs/default.yaml", overrides: dict[str, Any] | None = None) -> DictConfig:
    """Load a YAML config file with optional overrides merged in.

    Parameters
    ----------
    path : str
        Path to the YAML configuration file.
    overrides : dict, optional
        Key-value pairs to merge on top of the loaded config.

    Returns
    -------
    DictConfig
        The merged, read-only configuration object.
    """
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    cfg = OmegaConf.load(cfg_path)

    if overrides is not None:
        override_cfg = OmegaConf.create(overrides)
        cfg = OmegaConf.merge(cfg, override_cfg)

    return cfg


def merge_configs(*configs: DictConfig | dict[str, Any]) -> DictConfig:
    """Merge multiple config dicts / OmegaConf objects (later ones take priority).

    Parameters
    ----------
    *configs
        Any number of ``dict`` or ``DictConfig`` objects.

    Returns
    -------
    DictConfig
        The merged configuration.
    """
    oc_cfgs = []
    for c in configs:
        if isinstance(c, dict):
            oc_cfgs.append(OmegaConf.create(c))
        else:
            oc_cfgs.append(c)
    return OmegaConf.merge(*oc_cfgs)
