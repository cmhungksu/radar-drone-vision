"""Training and inference API routes."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from radar_drone_vision.api.schemas import (
    EvalRequest,
    EvalResponse,
    InferenceRequest,
    InferenceResponse,
    TrainRequest,
    TrainStatusResponse,
)
from radar_drone_vision.utils.logging import get_logger

router = APIRouter(tags=["inference"])
logger = get_logger(__name__)

# In-memory task tracker
_train_tasks: dict[str, TrainStatusResponse] = {}


# ---------------------------------------------------------------------------
# Background training helpers
# ---------------------------------------------------------------------------

def _run_training(task_id: str, req: TrainRequest, model_type: str) -> None:
    """Execute a training run in the background."""
    try:
        _train_tasks[task_id].status = "running"
        logger.info("Training started: task=%s model=%s dataset=%s", task_id, model_type, req.dataset)

        from radar_drone_vision.utils.config import load_config
        cfg = load_config(req.config_path, overrides=req.overrides)

        from radar_drone_vision.utils.seed import set_seed
        seed = cfg.get("seed", 42) if hasattr(cfg, "get") else 42
        set_seed(seed)

        # Placeholder: real training loop would go here
        _train_tasks[task_id].total_epochs = req.epochs
        for epoch in range(1, req.epochs + 1):
            _train_tasks[task_id].epoch = epoch

        _train_tasks[task_id].status = "completed"
        _train_tasks[task_id].message = f"Training completed ({req.epochs} epochs)"
        logger.info("Training completed: task=%s", task_id)

    except Exception as exc:
        _train_tasks[task_id].status = "failed"
        _train_tasks[task_id].message = str(exc)
        logger.error("Training failed: task=%s error=%s", task_id, exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/models/sra/train", response_model=TrainStatusResponse)
async def train_sra(req: TrainRequest, background_tasks: BackgroundTasks):
    """Trigger SRA (Sparse Representation Analysis) training as a background task."""
    task_id = str(uuid.uuid4())
    _train_tasks[task_id] = TrainStatusResponse(
        task_id=task_id, status="queued", total_epochs=req.epochs,
    )
    background_tasks.add_task(_run_training, task_id, req, "sra")
    return _train_tasks[task_id]


@router.post("/models/cnn/train", response_model=TrainStatusResponse)
async def train_cnn(req: TrainRequest, background_tasks: BackgroundTasks):
    """Trigger CNN training as a background task."""
    task_id = str(uuid.uuid4())
    _train_tasks[task_id] = TrainStatusResponse(
        task_id=task_id, status="queued", total_epochs=req.epochs,
    )
    background_tasks.add_task(_run_training, task_id, req, "cnn")
    return _train_tasks[task_id]


@router.get("/models/train/{task_id}", response_model=TrainStatusResponse)
async def get_train_status(task_id: str):
    """Check training task status."""
    task = _train_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Training task not found: {task_id}")
    return task


@router.post("/models/evaluate", response_model=EvalResponse)
async def evaluate_model(req: EvalRequest):
    """Evaluate a trained model on a dataset split."""
    model_path = Path(req.model_path)
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model file not found: {req.model_path}")

    try:
        # Placeholder evaluation - real implementation would load model and run eval
        logger.info("Evaluating model=%s dataset=%s split=%s", req.model_path, req.dataset, req.split)
        return EvalResponse(
            accuracy=0.0,
            eer=0.0,
            far_at_frr1=0.0,
            confusion_matrix=[],
            classification_report="(evaluation not yet implemented)",
            model_path=req.model_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/inference/sample", response_model=InferenceResponse)
async def infer_sample(req: InferenceRequest):
    """Run inference on a single sample (by ID or raw data)."""
    if req.sample_id is None and req.data is None:
        raise HTTPException(status_code=400, detail="Provide either sample_id or data")

    try:
        import numpy as np
        import torch

        # Resolve model path
        model_path = req.model_path
        if model_path is None:
            model_path = f"models/{req.model}_best.pt"

        mp = Path(model_path)
        if not mp.exists():
            raise HTTPException(status_code=404, detail=f"Model file not found: {model_path}")

        # Load model
        if req.model == "cnn":
            from radar_drone_vision.torch_models.cnn import SmallRadarCNN
            model = SmallRadarCNN()
            state = torch.load(str(mp), map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            model.eval()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown model type: {req.model}")

        # Prepare input
        if req.data is not None:
            arr = np.array(req.data, dtype=np.float32)
        else:
            raise HTTPException(status_code=501, detail="Inference by sample_id not yet implemented")

        tensor = torch.from_numpy(arr).unsqueeze(0)  # add batch dim
        if tensor.ndim == 3:
            tensor = tensor.unsqueeze(0)  # add channel dim if needed

        with torch.no_grad():
            logits = model(tensor)
            probs = torch.softmax(logits, dim=-1).squeeze(0)

        class_names = ["non_uav", "uav"]
        scores = {name: float(probs[i]) for i, name in enumerate(class_names)}
        pred_idx = int(probs.argmax())

        return InferenceResponse(
            prediction=class_names[pred_idx],
            confidence=float(probs[pred_idx]),
            scores=scores,
            model=req.model,
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
