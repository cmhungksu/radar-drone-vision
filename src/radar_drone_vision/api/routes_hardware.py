"""Hardware (radar device) API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from radar_drone_vision.api.schemas import (
    HardwareConnectRequest,
    HardwareStatus,
    LiveFrameResponse,
)
from radar_drone_vision.utils.logging import get_logger

router = APIRouter(tags=["hardware"])
logger = get_logger(__name__)

# Singleton state for the connected device
_hw_state = HardwareStatus()


@router.post("/hardware/connect", response_model=HardwareStatus)
async def connect_device(req: HardwareConnectRequest):
    """Connect to a radar hardware device via serial port."""
    global _hw_state

    if _hw_state.connected:
        raise HTTPException(status_code=409, detail="Device already connected. Disconnect first.")

    try:
        # Attempt serial connection (placeholder - real impl uses pyserial)
        logger.info("Connecting to %s @ %d baud (type=%s)", req.port, req.baud_rate, req.radar_type)

        _hw_state = HardwareStatus(
            device=req.port,
            connected=True,
            frames_received=0,
            error="",
        )
        return _hw_state

    except Exception as exc:
        _hw_state = HardwareStatus(device=req.port, connected=False, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/hardware/disconnect", response_model=HardwareStatus)
async def disconnect_device():
    """Disconnect from the radar hardware device."""
    global _hw_state

    if not _hw_state.connected:
        raise HTTPException(status_code=409, detail="No device connected.")

    logger.info("Disconnecting from %s", _hw_state.device)
    _hw_state = HardwareStatus(device="", connected=False)
    return _hw_state


@router.get("/hardware/status", response_model=HardwareStatus)
async def get_hardware_status():
    """Return current hardware connection status."""
    return _hw_state


@router.get("/hardware/live-frame", response_model=LiveFrameResponse)
async def get_live_frame():
    """Return the latest radar frame from the connected device."""
    if not _hw_state.connected:
        raise HTTPException(status_code=409, detail="No device connected.")

    # Placeholder - real implementation would read from device buffer
    import time
    return LiveFrameResponse(
        frame_id=_hw_state.frames_received,
        shape=[256],
        data=[],
        timestamp=time.time(),
    )
