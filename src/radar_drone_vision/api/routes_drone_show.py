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


# ── Simulation ────────────────────────────────────────────────────────────────

@router.post("/simulate/{plan_id}")
async def simulate_plan(plan_id: str, body: dict = {}):
    """Run full collision/speed simulation on a timeline plan.

    Returns comprehensive risk report with inter-drone distances,
    speed/acceleration checks, and warnings.
    """
    plan_path = PLANS_DIR / f"{plan_id}.json"
    if not plan_path.exists():
        raise HTTPException(404, f"Plan not found: {plan_id}")

    from radar_drone_vision.drone_show.simulation import run_full_simulation

    with open(plan_path) as f:
        plan_data = json.load(f)

    sample_rate = body.get("sample_rate", 10)
    try:
        report = run_full_simulation(plan_data, sample_rate=sample_rate)
    except Exception as exc:
        logger.error("Simulation failed: %s", exc)
        raise HTTPException(500, f"Simulation failed: {exc}") from exc

    # Save report
    report_path = PLANS_DIR / f"{plan_id}_sim_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Simulation: %s → risk=%s, min_dist=%.2fm",
                plan_id, report["risk_level"], report["inter_drone"]["min_distance"])
    return report


# ── Path Smoothing ────────────────────────────────────────────────────────────

@router.post("/smooth-path")
async def smooth_path_api(body: dict):
    """Smooth a set of control points using Catmull-Rom → Bezier.

    Body: { control_points: [[x,y,z],...], samples_per_segment?, arc_length_count? }
    Returns smooth, C1-continuous path with optional arc-length reparameterization.
    """
    from radar_drone_vision.drone_show.smoothing import (
        smooth_path_catmull_rom, arc_length_reparameterize, validate_path_smoothness
    )

    control_points = body.get("control_points", [])
    if len(control_points) < 2:
        raise HTTPException(400, "Need at least 2 control points")

    samples = body.get("samples_per_segment", 20)
    smoothed = smooth_path_catmull_rom(control_points, samples_per_segment=samples)

    arc_count = body.get("arc_length_count")
    if arc_count:
        smoothed = arc_length_reparameterize(smoothed, target_count=arc_count)

    validation = validate_path_smoothness(smoothed)

    return {
        "input_points": len(control_points),
        "output_points": len(smoothed),
        "path": smoothed,
        "smoothness": validation,
        "algorithm": "catmull_rom_centripetal_bezier",
    }


@router.post("/smooth-plan/{plan_id}")
async def smooth_plan_paths(plan_id: str, body: dict = {}):
    """Apply Catmull-Rom smoothing to all drone paths in a plan.

    Returns smoothed path preview + smoothness validation for each drone.
    """
    plan_path = PLANS_DIR / f"{plan_id}.json"
    if not plan_path.exists():
        raise HTTPException(404, f"Plan not found: {plan_id}")

    with open(plan_path) as f:
        plan_data = json.load(f)

    from radar_drone_vision.drone_show.smoothing import (
        smooth_path_catmull_rom, validate_path_smoothness
    )

    samples = body.get("samples_per_segment", 15)
    results = []
    total_violations = 0

    for drone in plan_data.get("drones", [])[:100]:  # cap for performance
        all_cp = []
        for seg in drone.get("segments", []):
            all_cp.extend(seg.get("control_points", []))

        if len(all_cp) < 2:
            continue

        smoothed = smooth_path_catmull_rom(all_cp, samples_per_segment=samples)
        validation = validate_path_smoothness(smoothed)
        total_violations += len(validation.get("violations", []))

        results.append({
            "drone_id": drone["drone_id"],
            "original_points": len(all_cp),
            "smoothed_points": len(smoothed),
            "max_angle": validation["max_angle"],
            "smooth": validation["smooth"],
            "path_preview": smoothed[::max(1, len(smoothed) // 30)],  # downsample for frontend
        })

    return {
        "plan_id": plan_id,
        "drones_processed": len(results),
        "total_violations": total_violations,
        "all_smooth": total_violations == 0,
        "drones": results[:20],  # cap response
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


# ── LLM Scene DSL ────────────────────────────────────────────────────────────

@router.post("/dsl/compile")
async def compile_scene_dsl(body: dict):
    """Compile a Scene DSL (YAML or dict) into a planning job.

    Body: { yaml?: string, scene?: dict }
    Accepts either raw YAML string or pre-parsed dict.

    LLM generates the DSL; this endpoint validates and compiles it.
    SIMULATION_ONLY — no real flight control output.
    """
    from radar_drone_vision.drone_show.scene_dsl import compile_dsl, parse_yaml_dsl

    yaml_text = body.get("yaml")
    scene_dict = body.get("scene")

    if yaml_text:
        try:
            dsl = parse_yaml_dsl(yaml_text)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    elif scene_dict:
        dsl = {"scene": scene_dict}
    else:
        raise HTTPException(400, "Provide 'yaml' (string) or 'scene' (dict)")

    result = compile_dsl(dsl, assets_dir=ASSETS_DIR)

    if not result.get("success"):
        raise HTTPException(422, detail={"errors": result.get("errors", [])})

    # Save compiled job
    job_path = PLANS_DIR / f"{result['job_id']}.json"
    with open(job_path, "w") as f:
        json.dump(result, f, indent=2)

    logger.info("DSL compiled: %s (%d drones, %d frames)",
                result["title"], result["drone_count"], result["frame_count"])
    return result


@router.post("/dsl/execute/{job_id}")
async def execute_dsl_job(job_id: str):
    """Execute a compiled DSL job — generate formations and plan.

    Runs each frame in sequence: image_formation → generate points,
    transform → apply ops, then plans transitions between frames.
    """
    job_path = PLANS_DIR / f"{job_id}.json"
    if not job_path.exists():
        raise HTTPException(404, f"DSL job not found: {job_id}")

    with open(job_path) as f:
        job = json.load(f)

    if not job.get("success"):
        raise HTTPException(400, "Job was not successfully compiled")

    drone_count = job["drone_count"]
    compiled_frames = job.get("frames", [])
    generated_frame_ids = []
    results = []

    from radar_drone_vision.drone_show.image_to_points import generate_formation_from_image
    from radar_drone_vision.drone_show.schemas import FormationFrame, FormationPoint
    import copy, math, numpy as np

    current_frame = None  # track the latest formation for transforms

    for cf in compiled_frames:
        action = cf.get("action", "")

        if action == "generate_formation_from_image":
            asset_path = cf.get("asset_resolved")
            if not asset_path:
                # Try to find asset by name
                asset_name = cf.get("asset", "")
                candidates = list(ASSETS_DIR.glob(f"*{asset_name}*")) if asset_name else []
                if not candidates:
                    candidates = list(ASSETS_DIR.glob("asset_*"))
                asset_path = str(candidates[0]) if candidates else None

            if asset_path:
                try:
                    frame, palette = generate_formation_from_image(
                        asset_path, drone_count=drone_count,
                        z_height=50.0, scale=cf.get("scale", 1.0))
                    # Save frame
                    frame_path = PLANS_DIR / f"{frame.frame_id}.json"
                    with open(frame_path, "w") as f:
                        json.dump(frame.model_dump(), f, indent=2)
                    generated_frame_ids.append(frame.frame_id)
                    current_frame = frame
                    results.append({"frame_id": frame.frame_id, "type": "image_formation",
                                    "points": len(frame.points), "detail": frame.detail_score})
                except Exception as exc:
                    results.append({"type": "image_formation", "error": str(exc)})
            else:
                results.append({"type": "image_formation", "error": "Asset not found"})

        elif action == "apply_transform_to_current_formation" and current_frame:
            # Apply geometric transforms to current formation
            new_points = []
            ops = cf.get("parsed_ops", [])
            for p in current_frame.points:
                x, y, z = p.xyz
                for op in ops:
                    if op["op"] == "scale":
                        factor = op.get("factor", 1.0)
                        axis = op.get("axis")
                        if axis == "x":
                            x *= factor
                        elif axis == "y":
                            y *= factor
                        else:
                            x *= factor
                            y *= factor
                    elif op["op"] == "translate":
                        x += op.get("dx", 0)
                        y += op.get("dy", 0)
                        z += op.get("dz", 0)
                    elif op["op"] == "rotate":
                        angle = math.radians(op.get("angle", 0))
                        nx = x * math.cos(angle) - y * math.sin(angle)
                        ny = x * math.sin(angle) + y * math.cos(angle)
                        x, y = nx, ny
                    elif op["op"] == "color":
                        from radar_drone_vision.drone_show.led import rgb888_to_rgb565
                        rgb = op.get("rgb", p.rgb888)
                        p = FormationPoint(**{**p.model_dump(), "rgb888": rgb,
                                              "rgb565": rgb888_to_rgb565(*rgb)})

                new_points.append(FormationPoint(**{**p.model_dump(),
                                                    "xyz": [round(x, 2), round(y, 2), round(z, 2)]}))

            new_frame = FormationFrame(
                frame_id=f"frame_{uuid.uuid4().hex[:8]}",
                points=new_points, drone_count=drone_count,
                detail_score=current_frame.detail_score,
                warnings=[], image_width=current_frame.image_width,
                image_height=current_frame.image_height)
            frame_path = PLANS_DIR / f"{new_frame.frame_id}.json"
            with open(frame_path, "w") as f:
                json.dump(new_frame.model_dump(), f, indent=2)
            generated_frame_ids.append(new_frame.frame_id)
            current_frame = new_frame
            results.append({"frame_id": new_frame.frame_id, "type": "transform",
                            "ops": [o["op"] for o in ops]})

        elif action == "change_led_colors" and current_frame:
            rgb = cf.get("color", [255, 255, 255])
            from radar_drone_vision.drone_show.led import rgb888_to_rgb565
            new_points = [FormationPoint(**{**p.model_dump(), "rgb888": rgb,
                                            "rgb565": rgb888_to_rgb565(*rgb)})
                          for p in current_frame.points]
            new_frame = FormationFrame(
                frame_id=f"frame_{uuid.uuid4().hex[:8]}",
                points=new_points, drone_count=drone_count,
                detail_score=current_frame.detail_score, warnings=[])
            frame_path = PLANS_DIR / f"{new_frame.frame_id}.json"
            with open(frame_path, "w") as f:
                json.dump(new_frame.model_dump(), f, indent=2)
            generated_frame_ids.append(new_frame.frame_id)
            current_frame = new_frame
            results.append({"frame_id": new_frame.frame_id, "type": "color_change"})

        else:
            results.append({"type": cf.get("type", "unknown"), "action": action, "skipped": True})

    # If we have multiple image frames, create a storyboard plan
    plan_result = None
    if len(generated_frame_ids) >= 1:
        try:
            from radar_drone_vision.drone_show.schemas import FormationFrame as FF
            from radar_drone_vision.drone_show.storyboard import create_multi_frame_timeline

            frames = []
            for fid in generated_frame_ids:
                fp = PLANS_DIR / f"{fid}.json"
                if fp.exists():
                    with open(fp) as f:
                        frames.append(FF(**json.load(f)))

            if frames:
                plan, risk = create_multi_frame_timeline(frames)
                plan_path = PLANS_DIR / f"{plan.plan_id}.json"
                with open(plan_path, "w") as f:
                    json.dump(plan.model_dump(), f)
                plan_result = {
                    "plan_id": plan.plan_id,
                    "drone_count": plan.drone_count,
                    "total_duration_sec": plan.total_duration_sec,
                    "frames": plan.frames,
                    "risk": risk,
                }
        except Exception as exc:
            plan_result = {"error": str(exc)}

    return {
        "job_id": job_id,
        "executed_frames": results,
        "generated_frame_ids": generated_frame_ids,
        "plan": plan_result,
        "safety": "SIMULATION_ONLY",
    }


@router.post("/dsl/parse-instruction")
async def parse_natural_instruction(body: dict):
    """Parse a natural language instruction into geometric operations.

    Body: { instruction: string }
    Used by LLM to preview what operations will be applied.
    """
    from radar_drone_vision.drone_show.scene_dsl import parse_instruction

    instruction = body.get("instruction", "")
    if not instruction:
        raise HTTPException(400, "instruction is required")

    result = parse_instruction(instruction)
    return result


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


# ── Replay Studio (Spec 2: Flight Log Reconstruction) ─────────────────────────

@router.post("/replay/upload-log")
async def upload_flight_log(file: UploadFile = File(...)):
    """Upload a flight log (CSV/JSON) for reconstruction.

    SIMULATION_ONLY — read-only parsing, no mission upload.
    """
    replay_dir = DATA_DIR / "drone_show" / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)

    log_id = f"log_{uuid.uuid4().hex[:8]}"
    ext = Path(file.filename or "log.csv").suffix or ".csv"
    save_path = replay_dir / f"{log_id}{ext}"

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    # Parse log
    from radar_drone_vision.drone_show.replay.log_parser import parse_csv_log, detect_anomalies

    try:
        if ext in (".csv", ".tsv"):
            flight_state = parse_csv_log(save_path)
        else:
            from radar_drone_vision.drone_show.replay.log_parser import parse_json_plan
            flight_state = parse_json_plan(save_path)
    except Exception as exc:
        raise HTTPException(500, f"Log parsing failed: {exc}") from exc

    # Save parsed state
    state_path = replay_dir / f"{log_id}_state.json"
    with open(state_path, "w") as f:
        json.dump(flight_state, f)

    # Detect anomalies
    anomalies = detect_anomalies(flight_state)
    anomaly_path = replay_dir / f"{log_id}_anomalies.json"
    with open(anomaly_path, "w") as f:
        json.dump(anomalies, f, indent=2)

    return {
        "log_id": log_id,
        "drone_count": flight_state["drone_count"],
        "total_frames": sum(len(d["frames"]) for d in flight_state["drones"]),
        "anomaly_count": len(anomalies),
        "anomalies_preview": anomalies[:10],
        "safety": "SIMULATION_ONLY",
    }


@router.post("/replay/from-plan/{plan_id}")
async def reconstruct_from_plan(plan_id: str):
    """Reconstruct flight state from an existing timeline plan.

    Converts plan → flight_state_series for replay/failure simulation.
    """
    plan_path = PLANS_DIR / f"{plan_id}.json"
    if not plan_path.exists():
        raise HTTPException(404, f"Plan not found: {plan_id}")

    from radar_drone_vision.drone_show.replay.log_parser import parse_json_plan, detect_anomalies

    flight_state = parse_json_plan(plan_path)

    replay_dir = DATA_DIR / "drone_show" / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    log_id = f"plan_{plan_id}"
    state_path = replay_dir / f"{log_id}_state.json"
    with open(state_path, "w") as f:
        json.dump(flight_state, f)

    anomalies = detect_anomalies(flight_state)

    return {
        "log_id": log_id,
        "drone_count": flight_state["drone_count"],
        "total_frames": sum(len(d["frames"]) for d in flight_state["drones"]),
        "anomaly_count": len(anomalies),
        "safety": "SIMULATION_ONLY",
    }


@router.post("/replay/simulate-failure")
async def simulate_failure(body: dict):
    """Simulate a drone failure and plan visual replacement.

    Body: { log_id, drone_id, failure_type, start_time, duration?,
            candidate_pool?: [drone_ids] }

    failure_type: GPS_DRIFT | IMU_ANOMALY | LOW_BATTERY | LED_BLACKOUT |
                  COMM_LOST | DRONE_MISSING
    """
    log_id = body.get("log_id", "")
    replay_dir = DATA_DIR / "drone_show" / "replay"
    state_path = replay_dir / f"{log_id}_state.json"
    if not state_path.exists():
        raise HTTPException(404, f"Flight state not found: {log_id}")

    with open(state_path) as f:
        flight_state = json.load(f)

    from radar_drone_vision.drone_show.replay.failure_sim import (
        create_failure_scenario, apply_failure_to_state, plan_replacement
    )

    scenario = create_failure_scenario(
        drone_id=body.get("drone_id", "D001"),
        failure_type=body.get("failure_type", "LOW_BATTERY"),
        start_time=body.get("start_time", 10.0),
        duration=body.get("duration", 10.0),
        candidate_pool=body.get("candidate_pool"),
    )

    # Apply failure
    modified_state = apply_failure_to_state(flight_state, scenario)

    # Plan replacement
    replacement = plan_replacement(flight_state, scenario)

    # Save modified state
    fail_state_path = replay_dir / f"{log_id}_fail_{scenario['scenario_id']}.json"
    with open(fail_state_path, "w") as f:
        json.dump(modified_state, f)

    logger.info("Failure simulation: %s → %s on %s at t=%.1f",
                scenario["scenario_id"], body.get("failure_type"),
                body.get("drone_id"), body.get("start_time"))

    return {
        "scenario": scenario,
        "replacement": replacement,
        "modified_drone_count": modified_state["drone_count"],
        "safety": "SIMULATION_ONLY",
    }


@router.get("/replay/{log_id}/timeline")
async def get_replay_timeline(log_id: str, drone_id: Optional[str] = Query(None)):
    """Get the reconstructed timeline for replay visualization.

    Optionally filter to a single drone.
    """
    replay_dir = DATA_DIR / "drone_show" / "replay"
    state_path = replay_dir / f"{log_id}_state.json"
    if not state_path.exists():
        raise HTTPException(404, f"Flight state not found: {log_id}")

    with open(state_path) as f:
        flight_state = json.load(f)

    if drone_id:
        drones = [d for d in flight_state["drones"] if d["drone_id"] == drone_id]
    else:
        drones = flight_state["drones"]

    # Downsample for frontend (max 50 frames per drone)
    preview_drones = []
    for d in drones:
        frames = d["frames"]
        step = max(1, len(frames) // 50)
        preview_drones.append({
            "drone_id": d["drone_id"],
            "frame_count": len(frames),
            "frames_preview": frames[::step][:50],
            "time_range": [frames[0]["t"], frames[-1]["t"]] if frames else [0, 0],
        })

    return {
        "log_id": log_id,
        "drone_count": len(drones),
        "drones": preview_drones,
        "safety": "SIMULATION_ONLY",
    }


# ── Carrier Launch Station (Spec 3) ───────────────────────────────────────────

# In-memory carrier state
_carrier_manager = None


def _get_carrier():
    global _carrier_manager
    if _carrier_manager is None:
        from radar_drone_vision.drone_show.carrier.bay_manager import BayManager, CarrierConfig
        _carrier_manager = BayManager(CarrierConfig(bay_count=60, reserve_count=10))
    return _carrier_manager


@router.get("/carrier/inventory")
async def get_carrier_inventory():
    """Get current carrier bay inventory."""
    return _get_carrier().get_inventory()


@router.post("/carrier/configure")
async def configure_carrier(body: dict):
    """Configure carrier parameters.

    Body: { bay_count?, reserve_count?, max_launch_slots?,
            max_recovery_slots?, vehicle_dims? }
    """
    global _carrier_manager
    from radar_drone_vision.drone_show.carrier.bay_manager import BayManager, CarrierConfig

    config = CarrierConfig(
        bay_count=body.get("bay_count", 60),
        reserve_count=body.get("reserve_count", 10),
        max_launch_slots=body.get("max_launch_slots", 4),
        max_recovery_slots=body.get("max_recovery_slots", 2),
    )
    _carrier_manager = BayManager(config)
    logger.info("Carrier configured: %d bays, %d reserves", config.bay_count, config.reserve_count)
    return _carrier_manager.get_inventory()


@router.post("/carrier/plan-launch")
async def plan_carrier_launch(body: dict):
    """Plan a carrier-based launch schedule for a show.

    Body: { frame_id?, drone_count?, launch_interval_sec? }
    Uses formation points from a frame if provided.
    """
    from radar_drone_vision.drone_show.carrier.launch_scheduler import (
        plan_launch_schedule, create_wait_zones
    )

    carrier = _get_carrier()
    frame_id = body.get("frame_id")
    drone_count = body.get("drone_count", 50)

    # Get formation points
    formation_points = []
    if frame_id:
        frame_path = PLANS_DIR / f"{frame_id}.json"
        if frame_path.exists():
            with open(frame_path) as f:
                frame_data = json.load(f)
            formation_points = frame_data.get("points", [])

    if not formation_points:
        formation_points = [{"point_id": f"P{i+1:04d}"} for i in range(drone_count)]

    wait_zones = create_wait_zones(carrier.config.position)
    schedule = plan_launch_schedule(
        carrier,
        formation_points,
        wait_zones=wait_zones,
        launch_interval_sec=body.get("launch_interval_sec", 3.0),
    )

    # Save
    sched_path = PLANS_DIR / f"launch_{schedule['show_id']}.json"
    with open(sched_path, "w") as f:
        json.dump(schedule, f, indent=2)

    logger.info("Launch schedule: %d drones, %d waves, all-in at %.1fs",
                schedule["total_drones"], schedule["total_waves"],
                schedule["all_in_formation_time_sec"])
    return schedule


@router.post("/carrier/plan-recovery")
async def plan_carrier_recovery(body: dict):
    """Plan recovery schedule after show completion.

    Body: { show_id }
    """
    show_id = body.get("show_id", "")
    sched_path = list(PLANS_DIR.glob(f"launch_{show_id}.json"))
    if not sched_path:
        # Try to find any launch schedule
        sched_path = list(PLANS_DIR.glob("launch_*.json"))
    if not sched_path:
        raise HTTPException(404, "No launch schedule found")

    with open(sched_path[0]) as f:
        launch_schedule = json.load(f)

    from radar_drone_vision.drone_show.carrier.launch_scheduler import plan_recovery_schedule
    recovery = plan_recovery_schedule(
        _get_carrier(),
        launch_schedule,
        recovery_interval_sec=body.get("recovery_interval_sec", 4.0),
    )

    return recovery


@router.post("/carrier/simulate-charging")
async def simulate_charging(body: dict):
    """Simulate charging cycle for all docked drones.

    Body: { minutes?, rate_per_min? }
    """
    carrier = _get_carrier()
    minutes = body.get("minutes", 30.0)
    rate = body.get("rate_per_min", 2.0)
    carrier.simulate_charging(minutes=minutes, rate_per_min=rate)

    inventory = carrier.get_inventory()
    return {
        "charged_minutes": minutes,
        "rate_per_min": rate,
        "ready": inventory["ready"],
        "charging": inventory["charging"],
        "safety": "SIMULATION_ONLY",
    }


# ── Status / Info ────────────────────────────────────────────────────────────

@router.get("/status")
async def drone_show_status():
    """Return Drone Show Studio status and stats."""
    assets = list(ASSETS_DIR.glob("asset_*"))
    plans = list(PLANS_DIR.glob("plan_*"))
    renders = list(RENDERS_DIR.glob("render_*"))

    blender_bin = os.environ.get("BLENDER_BIN", "blender")
    blender_ok = shutil.which(blender_bin) is not None

    from radar_drone_vision.drone_show.isaac_connector.connector import get_connector
    isaac = get_connector().get_status()

    return {
        "module": "drone-show-studio",
        "version": "1.2.0",
        "simulation_only": True,
        "assets_count": len(assets),
        "plans_count": len(plans),
        "renders_count": len(renders),
        "blender_available": blender_ok,
        "isaac_sim": isaac,
        "features": {
            "image_to_points": True,
            "led_rgb565_rgb888": True,
            "formation_planning": True,
            "multi_frame_storyboard": True,
            "obstacle_system": True,
            "collision_simulation": True,
            "catmull_rom_smoothing": True,
            "scene_dsl_compiler": True,
            "flight_log_replay": True,
            "failure_simulation": True,
            "carrier_bay_management": True,
            "launch_recovery_scheduling": True,
            "2d_3d_animation": True,
            "max_drone_count": 10000,
        },
    }
