"""Dataset-related API routes."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from radar_drone_vision.api.schemas import (
    DatasetInfo,
    DatasetPrepareRequest,
    DatasetPrepareResponse,
    SampleResponse,
    SpectrogramResponse,
)

router = APIRouter(tags=["datasets"])

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))


# In-memory registry of loaded datasets (populated by prepare endpoint)
_datasets: dict[str, dict] = {}


@router.get("/datasets", response_model=list[DatasetInfo])
async def list_datasets():
    """List all available / prepared datasets."""
    results: list[DatasetInfo] = []

    # Always advertise known dataset names even if not yet prepared
    known = {"zenodo77": "Zenodo micro-Doppler drone/bird dataset (77 GHz)"}

    for name, desc in known.items():
        info = _datasets.get(name)
        if info is not None:
            results.append(DatasetInfo(
                name=name,
                num_samples=info.get("num_samples", 0),
                classes=info.get("classes", {}),
                splits=info.get("splits", {}),
                signal_shape=info.get("signal_shape", []),
                description=desc,
            ))
        else:
            results.append(DatasetInfo(name=name, num_samples=0, description=f"{desc} (not prepared)"))

    return results


@router.post("/datasets/prepare", response_model=DatasetPrepareResponse)
async def prepare_dataset(req: DatasetPrepareRequest):
    """Download / process a dataset so it is ready for training."""
    try:
        if req.dataset == "zenodo77":
            from radar_drone_vision.datasets.zenodo77 import Zenodo77Dataset  # noqa: F811

            ds = Zenodo77Dataset(data_dir=DATA_DIR / "raw" / "zenodo_77ghz")
            classes = ds.class_distribution()
            n_samples = len(ds)
            signal_shape = list(ds[0].signal.shape) if n_samples > 0 else []

            _datasets["zenodo77"] = {
                "num_samples": n_samples,
                "classes": classes,
                "splits": {},
                "signal_shape": signal_shape,
            }
            return DatasetPrepareResponse(dataset=req.dataset, status="ready", message=f"{n_samples} samples loaded")
        else:
            raise HTTPException(status_code=404, detail=f"Unknown dataset: {req.dataset}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/samples/{sample_id}", response_model=SampleResponse)
async def get_sample(sample_id: str):
    """Get metadata for a specific sample by ID."""
    # Search across loaded datasets
    for ds_info in _datasets.values():
        samples = ds_info.get("_samples")
        if samples is None:
            continue
        for s in samples:
            if s.sample_id == sample_id:
                return SampleResponse(
                    sample_id=s.sample_id,
                    label=s.label,
                    label_binary=s.label_binary,
                    shape=list(s.signal.shape),
                    radar_type=s.radar_type,
                    carrier_frequency_hz=s.carrier_frequency_hz,
                    metadata=s.metadata,
                )

    raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}")


@router.get("/samples/{sample_id}/spectrogram", response_model=SpectrogramResponse)
async def get_spectrogram(sample_id: str, fmt: str = "base64_png"):
    """Generate and return a spectrogram image for a sample.

    Query params:
        fmt: ``base64_png`` (default) or ``json``
    """
    import base64
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    # Find the sample
    sample = None
    for ds_info in _datasets.values():
        samples = ds_info.get("_samples")
        if samples is None:
            continue
        for s in samples:
            if s.sample_id == sample_id:
                sample = s
                break

    if sample is None:
        raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}")

    signal = sample.signal
    if signal.ndim == 1:
        # Compute spectrogram from 1-D signal
        from scipy.signal import spectrogram as scipy_spectrogram
        _, _, Sxx = scipy_spectrogram(signal, nperseg=min(256, len(signal)))
        img_data = 10 * np.log10(Sxx + 1e-12)
    elif signal.ndim == 2:
        img_data = signal
    else:
        img_data = signal.reshape(signal.shape[0], -1)

    if fmt == "json":
        return SpectrogramResponse(
            sample_id=sample_id,
            format="json",
            data="",
            width=img_data.shape[1],
            height=img_data.shape[0],
        )

    # Render to PNG
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.imshow(img_data, aspect="auto", origin="lower", cmap="viridis")
    ax.set_xlabel("Time")
    ax.set_ylabel("Frequency")
    ax.set_title(f"{sample.label} ({sample_id})")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")

    return SpectrogramResponse(
        sample_id=sample_id,
        format="base64_png",
        data=b64,
        width=img_data.shape[1],
        height=img_data.shape[0],
    )
