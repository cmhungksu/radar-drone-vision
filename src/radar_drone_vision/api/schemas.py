"""Pydantic models for the FastAPI endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
class DatasetInfo(BaseModel):
    name: str
    num_samples: int
    classes: dict[str, int] = Field(default_factory=dict, description="class_name -> count")
    splits: dict[str, int] = Field(default_factory=dict, description="split_name -> count")
    signal_shape: list[int] = Field(default_factory=list)
    description: str = ""


class DatasetPrepareRequest(BaseModel):
    dataset: str = "zenodo77"
    force: bool = False


class DatasetPrepareResponse(BaseModel):
    dataset: str
    status: str
    message: str = ""


class SampleResponse(BaseModel):
    sample_id: str
    label: str
    label_binary: int
    shape: list[int]
    radar_type: str = ""
    carrier_frequency_hz: float = 0.0
    metadata: dict = Field(default_factory=dict)


class SpectrogramResponse(BaseModel):
    sample_id: str
    format: str = "base64_png"
    data: str = ""
    width: int = 0
    height: int = 0


# ---------------------------------------------------------------------------
# Training / Evaluation
# ---------------------------------------------------------------------------
class TrainRequest(BaseModel):
    config_path: str = "configs/default.yaml"
    dataset: str = "zenodo77"
    epochs: int = 50
    batch_size: int = 32
    learning_rate: float = 1e-3
    overrides: dict = Field(default_factory=dict)


class TrainStatusResponse(BaseModel):
    task_id: str
    status: str  # queued / running / completed / failed
    epoch: int = 0
    total_epochs: int = 0
    message: str = ""


class EvalRequest(BaseModel):
    model_path: str
    dataset: str = "zenodo77"
    split: str = "test"


class EvalResponse(BaseModel):
    accuracy: float = 0.0
    eer: float = 0.0
    far_at_frr1: float = 0.0
    confusion_matrix: list[list[int]] = Field(default_factory=list)
    classification_report: str = ""
    model_path: str = ""


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
class InferenceRequest(BaseModel):
    sample_id: str | None = None
    data: list[float] | None = None
    model: str = "cnn"
    model_path: str | None = None


class InferenceResponse(BaseModel):
    prediction: str
    confidence: float
    scores: dict[str, float] = Field(default_factory=dict)
    model: str = ""


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------
class HardwareConnectRequest(BaseModel):
    port: str = "/dev/ttyUSB0"
    baud_rate: int = 115200
    radar_type: str = "fmcw"


class HardwareStatus(BaseModel):
    device: str = ""
    connected: bool = False
    frames_received: int = 0
    last_frame_time: float | None = None
    error: str = ""


class LiveFrameResponse(BaseModel):
    frame_id: int = 0
    shape: list[int] = Field(default_factory=list)
    data: list[float] = Field(default_factory=list)
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
class ReportSummary(BaseModel):
    report_path: str = ""
    created_at: str = ""
    accuracy: float = 0.0
    eer: float = 0.0
    model: str = ""
    dataset: str = ""


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    detail: str
