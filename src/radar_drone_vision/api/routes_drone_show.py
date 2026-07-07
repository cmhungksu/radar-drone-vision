"""Drone Show Studio API routes.

All outputs are SIMULATION_ONLY — no real flight control data.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from radar_drone_vision.utils.logging import get_logger

router = APIRouter(prefix="/drone-show", tags=["drone-show"])
logger = get_logger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
ASSETS_DIR = DATA_DIR / "drone_show" / "assets"
PLANS_DIR = DATA_DIR / "drone_show" / "plans"
RENDERS_DIR = DATA_DIR / "drone_show" / "renders"

for d in [ASSETS_DIR, PLANS_DIR, RENDERS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ── Asset Upload ─────────────────────────────────────────────────────────────

@router.post("/assets/upload")
async def upload_asset(file: UploadFile = File(...)):
    """Upload an image (PNG/JPG/SVG) for drone show formation."""
    if file.content_type not in ("image/png", "image/jpeg", "image/svg+xml",
                                  "image/webp", "application/octet-stream"):
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    asset_id = f"asset_{uuid.uuid4().hex[:8]}"
    ext = Path(file.filename or "image.png").suffix or ".png"
    save_path = ASSETS_DIR / f"{asset_id}{ext}"

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    logger.info("Asset uploaded: %s (%d bytes)", save_path.name, len(content))
    return {
        "asset_id": asset_id,
        "filename": file.filename,
        "size_bytes": len(content),
        "path": str(save_path),
    }


@router.get("/assets/{asset_id}/thumbnail")
async def get_asset_thumbnail(asset_id: str):
    """Return a small thumbnail of the uploaded asset."""
    import base64
    import cv2

    matches = list(ASSETS_DIR.glob(f"{asset_id}.*"))
    if not matches:
        raise HTTPException(404, f"Asset not found: {asset_id}")

    img = cv2.imread(str(matches[0]))
    if img is None:
        raise HTTPException(500, "Cannot read image")

    # Resize to max 200px
    h, w = img.shape[:2]
    scale = min(200 / w, 200 / h, 1.0)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    _, buf = cv2.imencode(".png", img)
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return {"thumbnail": f"data:image/png;base64,{b64}", "width": w, "height": h}


# ── Point Generation ─────────────────────────────────────────────────────────

@router.post("/generate-points")
async def generate_points(body: dict):
    """Generate formation points from an uploaded image.

    Body: { asset_id, drone_count, z_height?, scale? }
    Returns downsampled preview (not full private data).
    """
    asset_id = body.get("asset_id", "")
    drone_count = body.get("drone_count", 50)
    z_height = body.get("z_height", 50.0)
    scale = body.get("scale", 1.0)

    matches = list(ASSETS_DIR.glob(f"{asset_id}.*"))
    if not matches:
        raise HTTPException(404, f"Asset not found: {asset_id}")

    from radar_drone_vision.drone_show.image_to_points import generate_formation_from_image

    try:
        frame, palette = generate_formation_from_image(
            matches[0], drone_count=drone_count,
            z_height=z_height, scale=scale,
        )
    except Exception as exc:
        logger.error("Point generation failed: %s", exc)
        raise HTTPException(500, f"Point generation failed: {exc}") from exc

    # Save full frame privately
    frame_path = PLANS_DIR / f"{frame.frame_id}.json"
    with open(frame_path, "w") as f:
        json.dump(frame.model_dump(), f, indent=2)

    # Return downsampled preview (every point but without internal details)
    preview_points = [
        {
            "point_id": p.point_id,
            "xyz": p.xyz,
            "rgb888": p.rgb888,
            "importance": p.importance,
        }
        for p in frame.points
    ]

    return {
        "frame_id": frame.frame_id,
        "drone_count": frame.drone_count,
        "detail_score": frame.detail_score,
        "warnings": frame.warnings,
        "palette": palette,
        "points_preview": preview_points,
    }


# ── Planning ─────────────────────────────────────────────────────────────────

@router.post("/plan")
async def create_plan(body: dict):
    """Create a timeline plan from a formation frame.

    Body: { frame_id, takeoff_duration?, hold_duration?, landing_duration? }
    """
    frame_id = body.get("frame_id", "")

    frame_path = PLANS_DIR / f"{frame_id}.json"
    if not frame_path.exists():
        raise HTTPException(404, f"Frame not found: {frame_id}")

    from radar_drone_vision.drone_show.schemas import FormationFrame
    from radar_drone_vision.drone_show.planning import create_timeline_plan

    with open(frame_path) as f:
        frame_data = json.load(f)
    frame = FormationFrame(**frame_data)

    plan, risk = create_timeline_plan(
        frame,
        takeoff_duration=body.get("takeoff_duration", 8.0),
        hold_duration=body.get("hold_duration", 6.0),
        landing_duration=body.get("landing_duration", 8.0),
    )

    # Save full plan privately
    plan_path = PLANS_DIR / f"{plan.plan_id}.json"
    with open(plan_path, "w") as f:
        json.dump(plan.model_dump(), f)

    logger.info("Plan created: %s (%d drones, %.1fs)",
                plan.plan_id, plan.drone_count, plan.total_duration_sec)

    # Return summary (not full paths)
    return {
        "plan_id": plan.plan_id,
        "drone_count": plan.drone_count,
        "total_duration_sec": plan.total_duration_sec,
        "frames": plan.frames,
        "risk": risk,
        "metadata": plan.metadata,
        # Downsampled path preview: only first/last point per drone
        "drone_preview": [
            {
                "drone_id": d["drone_id"],
                "ground": d["ground_position"],
                "target": d["formation_point"]["xyz"],
                "color": d["formation_point"]["rgb888"],
            }
            for d in plan.drones
        ],
    }


@router.get("/plan/{plan_id}")
async def get_plan(plan_id: str):
    """Get plan summary (downsampled, no private data)."""
    plan_path = PLANS_DIR / f"{plan_id}.json"
    if not plan_path.exists():
        raise HTTPException(404, f"Plan not found: {plan_id}")

    with open(plan_path) as f:
        plan = json.load(f)

    return {
        "plan_id": plan["plan_id"],
        "drone_count": plan["drone_count"],
        "total_duration_sec": plan["total_duration_sec"],
        "frames": plan["frames"],
        "metadata": plan.get("metadata", {}),
    }


# ── Render (Blender) ─────────────────────────────────────────────────────────

@router.post("/render/{plan_id}")
async def trigger_render(plan_id: str, body: dict = {}):
    """Trigger Blender headless render for a plan.

    Returns render_job_id for polling status.
    """
    plan_path = PLANS_DIR / f"{plan_id}.json"
    if not plan_path.exists():
        raise HTTPException(404, f"Plan not found: {plan_id}")

    render_id = f"render_{uuid.uuid4().hex[:8]}"
    output_dir = RENDERS_DIR / render_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if Blender is available
    blender_bin = os.environ.get("BLENDER_BIN", "blender")

    # For now, generate a simple preview without Blender
    # (Blender integration will be added when available)
    try:
        from radar_drone_vision.drone_show.render.simple_renderer import render_formation_preview
        with open(plan_path) as f:
            plan_data = json.load(f)
        render_formation_preview(plan_data, output_dir)
        status = "completed"
    except Exception as exc:
        logger.warning("Simple render failed: %s", exc)
        status = "failed"

    return {
        "render_id": render_id,
        "plan_id": plan_id,
        "status": status,
        "output_dir": str(output_dir),
    }


@router.get("/render/{render_id}/files")
async def get_render_files(render_id: str):
    """List available render output files."""
    output_dir = RENDERS_DIR / render_id
    if not output_dir.exists():
        raise HTTPException(404, f"Render not found: {render_id}")

    files = []
    for f in output_dir.iterdir():
        if f.is_file():
            files.append({
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "url": f"/drone-show/render/{render_id}/download/{f.name}",
            })
    return {"render_id": render_id, "files": files}


@router.get("/render/{render_id}/download/{filename}")
async def download_render_file(render_id: str, filename: str):
    """Download a render output file."""
    from fastapi.responses import FileResponse

    file_path = RENDERS_DIR / render_id / filename
    if not file_path.exists():
        raise HTTPException(404, f"File not found: {filename}")

    return FileResponse(file_path, filename=filename)


# ── Multi-Frame Storyboard ────────────────────────────────────────────────────

@router.post("/storyboard/plan")
async def plan_storyboard(body: dict):
    """Create a multi-frame timeline plan from multiple formation frames.

    Body: { frame_ids: [str], hold_duration?, transition_duration?, ... }
    Sequence: takeoff → frame[0] → transition → frame[1] → ... → landing
    """
    frame_ids = body.get("frame_ids", [])
    if not frame_ids:
        raise HTTPException(400, "frame_ids is required (list of frame_id strings)")

    from radar_drone_vision.drone_show.schemas import FormationFrame
    from radar_drone_vision.drone_show.storyboard import create_multi_frame_timeline

    frames = []
    for fid in frame_ids:
        frame_path = PLANS_DIR / f"{fid}.json"
        if not frame_path.exists():
            raise HTTPException(404, f"Frame not found: {fid}")
        with open(frame_path) as f:
            frames.append(FormationFrame(**json.load(f)))

    try:
        plan, risk = create_multi_frame_timeline(
            frames,
            takeoff_duration=body.get("takeoff_duration", 8.0),
            hold_duration=body.get("hold_duration", 6.0),
            transition_duration=body.get("transition_duration", 5.0),
            landing_duration=body.get("landing_duration", 8.0),
        )
    except Exception as exc:
        raise HTTPException(500, f"Storyboard planning failed: {exc}") from exc

    # Save plan
    plan_path = PLANS_DIR / f"{plan.plan_id}.json"
    with open(plan_path, "w") as f:
        json.dump(plan.model_dump(), f)

    logger.info("Multi-frame plan: %s (%d frames, %d drones, %.1fs)",
                plan.plan_id, len(frames), plan.drone_count, plan.total_duration_sec)

    return {
        "plan_id": plan.plan_id,
        "drone_count": plan.drone_count,
        "total_duration_sec": plan.total_duration_sec,
        "frame_count": len(frames),
        "frames": plan.frames,
        "risk": risk,
    }


# ── Obstacles ─────────────────────────────────────────────────────────────────

# In-memory obstacle registry (per-session; production would use DB)
_obstacle_registries: dict[str, "ObstacleRegistry"] = {}


def _get_registry(project_id: str = "default"):
    from radar_drone_vision.drone_show.obstacles import ObstacleRegistry
    if project_id not in _obstacle_registries:
        _obstacle_registries[project_id] = ObstacleRegistry()
    return _obstacle_registries[project_id]


@router.post("/obstacles")
async def add_obstacle(body: dict):
    """Add an obstacle from Canvas drawing.

    Body: { name, type (balloon/building/no_fly/stage), shape,
            canvas_x, canvas_y, canvas_w, canvas_h,
            z_min, z_max, safety_buffer, project_id? }
    """
    from radar_drone_vision.drone_show.obstacles import canvas_to_obstacle

    project_id = body.pop("project_id", "default")
    registry = _get_registry(project_id)
    obs = canvas_to_obstacle(body)
    registry.add(obs)

    logger.info("Obstacle added: %s (%s)", obs.name, obs.obs_type)
    return obs.to_dict()


@router.get("/obstacles")
async def list_obstacles(project_id: str = Query("default")):
    """List all obstacles for a project."""
    registry = _get_registry(project_id)
    return {"obstacles": registry.to_list(), "count": len(registry.obstacles)}


@router.delete("/obstacles/{obstacle_id}")
async def remove_obstacle(obstacle_id: str, project_id: str = Query("default")):
    """Remove an obstacle."""
    registry = _get_registry(project_id)
    removed = registry.remove(obstacle_id)
    if not removed:
        raise HTTPException(404, f"Obstacle not found: {obstacle_id}")
    return {"removed": obstacle_id}


@router.post("/obstacles/check-formation")
async def check_formation_obstacles(body: dict):
    """Check a formation frame against all obstacles.

    Body: { frame_id, project_id? }
    """
    frame_id = body.get("frame_id", "")
    project_id = body.get("project_id", "default")

    frame_path = PLANS_DIR / f"{frame_id}.json"
    if not frame_path.exists():
        raise HTTPException(404, f"Frame not found: {frame_id}")

    from radar_drone_vision.drone_show.schemas import FormationFrame
    with open(frame_path) as f:
        frame = FormationFrame(**json.load(f))

    registry = _get_registry(project_id)
    result = registry.check_formation(frame.points)
    return result


# ── Status / Info ────────────────────────────────────────────────────────────

@router.get("/status")
async def drone_show_status():
    """Return Drone Show Studio status and stats."""
    assets = list(ASSETS_DIR.glob("asset_*"))
    plans = list(PLANS_DIR.glob("plan_*"))
    renders = list(RENDERS_DIR.glob("render_*"))

    blender_bin = os.environ.get("BLENDER_BIN", "blender")
    blender_ok = shutil.which(blender_bin) is not None

    return {
        "module": "drone-show-studio",
        "version": "1.0.0-mvp",
        "simulation_only": True,
        "assets_count": len(assets),
        "plans_count": len(plans),
        "renders_count": len(renders),
        "blender_available": blender_ok,
    }
