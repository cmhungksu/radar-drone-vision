"""LLM Scene DSL compiler — high-level show description → planning tasks.

Converts YAML Scene DSL (created by LLM or human) into validated
planning jobs. The DSL is the ONLY interface between LLM and the
planning engine — LLM never touches raw point data.

Safety rules:
- LLM output is validated against schema before execution
- No real flight control commands in DSL
- No private core parameters exposed
- All results are SIMULATION_ONLY

Supported frame types:
- takeoff_blue: all drones rise with blue LED
- image_formation: generate points from image asset
- transform: apply geometric transform to current formation
- color_change: change LED colors
- landing_blue: descend with blue LED

Supported instructions (for 'transform' type):
- scale, rotate, translate, expand, shrink
- LLM natural language instructions get parsed into these ops
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

# ── Schema validation ────────────────────────────────────────────────────────

VALID_FRAME_TYPES = {"takeoff_blue", "image_formation", "transform",
                     "color_change", "landing_blue", "hold"}
VALID_SAFETY_PROFILES = {"safety_first", "visual_first", "fast_preview"}
VALID_FITS = {"center", "fill", "fit_width", "fit_height"}

# Forbidden patterns that indicate real flight control
_FORBIDDEN_PATTERNS = [
    r"mavlink", r"mission_upload", r"arm_command", r"takeoff_command",
    r"land_command", r"set_position_target", r"command_long",
    r"guided_mode", r"offboard", r"serial_write", r"udp_write",
    r"gps_waypoint", r"real_flight", r"px4", r"ardupilot",
]


def validate_dsl(dsl: dict) -> List[str]:
    """Validate a Scene DSL dict. Returns list of errors (empty = valid)."""
    errors = []
    scene = dsl.get("scene", {})
    if not scene:
        errors.append("Missing 'scene' root key")
        return errors

    # Check for forbidden content
    dsl_str = str(dsl).lower()
    for pattern in _FORBIDDEN_PATTERNS:
        if re.search(pattern, dsl_str):
            errors.append(f"SAFETY VIOLATION: DSL contains forbidden pattern '{pattern}'")

    if not scene.get("title"):
        errors.append("Missing scene.title")

    drones = scene.get("drones", 0)
    if not isinstance(drones, int) or drones < 5 or drones > 10000:
        errors.append(f"scene.drones must be 5-10000, got {drones}")

    profile = scene.get("safety_profile", "safety_first")
    if profile not in VALID_SAFETY_PROFILES:
        errors.append(f"Invalid safety_profile '{profile}'")

    frames = scene.get("frames", [])
    if not frames:
        errors.append("scene.frames is empty")

    for i, frame in enumerate(frames):
        ftype = frame.get("type", "")
        if ftype not in VALID_FRAME_TYPES:
            errors.append(f"Frame {i}: invalid type '{ftype}'")

        if ftype == "image_formation" and not frame.get("asset"):
            errors.append(f"Frame {i}: image_formation requires 'asset'")

        duration = frame.get("duration") or frame.get("hold")
        if duration is not None and (not isinstance(duration, (int, float)) or duration <= 0):
            errors.append(f"Frame {i}: duration must be positive, got {duration}")

    return errors


# ── Natural language instruction parser ──────────────────────────────────────

def parse_instruction(instruction: str) -> dict:
    """Parse a natural language instruction into geometric operations.

    Examples:
    - "讓圖案左右展開 15%" → {"op": "scale", "axis": "x", "factor": 1.15}
    - "往上移動 10 公尺" → {"op": "translate", "dy": 10}
    - "順時針旋轉 30 度" → {"op": "rotate", "angle": 30}
    - "放大 20%" → {"op": "scale", "factor": 1.2}
    - "縮小到一半" → {"op": "scale", "factor": 0.5}
    """
    inst = instruction.lower().strip()
    ops = []

    # Scale patterns
    m = re.search(r'(?:放大|展開|擴大|scale.*up)\s*(\d+)\s*%', inst)
    if m:
        pct = int(m.group(1))
        if "左右" in inst or "水平" in inst:
            ops.append({"op": "scale", "axis": "x", "factor": 1 + pct / 100})
        elif "上下" in inst or "垂直" in inst:
            ops.append({"op": "scale", "axis": "y", "factor": 1 + pct / 100})
        else:
            ops.append({"op": "scale", "factor": 1 + pct / 100})

    m = re.search(r'(?:縮小|shrink|scale.*down)\s*(\d+)\s*%', inst)
    if m:
        pct = int(m.group(1))
        ops.append({"op": "scale", "factor": 1 - pct / 100})

    if "縮小到一半" in inst or "half" in inst:
        ops.append({"op": "scale", "factor": 0.5})

    # Translate patterns
    m = re.search(r'(?:往上|向上|上移)\s*(\d+(?:\.\d+)?)\s*(?:公尺|m|米)?', inst)
    if m:
        ops.append({"op": "translate", "dy": float(m.group(1))})

    m = re.search(r'(?:往下|向下|下移)\s*(\d+(?:\.\d+)?)\s*(?:公尺|m|米)?', inst)
    if m:
        ops.append({"op": "translate", "dy": -float(m.group(1))})

    m = re.search(r'(?:往右|向右|右移)\s*(\d+(?:\.\d+)?)\s*(?:公尺|m|米)?', inst)
    if m:
        ops.append({"op": "translate", "dx": float(m.group(1))})

    m = re.search(r'(?:往左|向左|左移)\s*(\d+(?:\.\d+)?)\s*(?:公尺|m|米)?', inst)
    if m:
        ops.append({"op": "translate", "dx": -float(m.group(1))})

    m = re.search(r'(?:升高|提高|拉高)\s*(\d+(?:\.\d+)?)\s*(?:公尺|m|米)?', inst)
    if m:
        ops.append({"op": "translate", "dz": float(m.group(1))})

    m = re.search(r'(?:降低|降下)\s*(\d+(?:\.\d+)?)\s*(?:公尺|m|米)?', inst)
    if m:
        ops.append({"op": "translate", "dz": -float(m.group(1))})

    # Rotate patterns
    m = re.search(r'(?:順時針|右轉|clockwise)\s*(?:旋轉|rotate)?\s*(\d+)\s*(?:度|°|deg)?', inst)
    if m:
        ops.append({"op": "rotate", "angle": int(m.group(1))})

    m = re.search(r'(?:逆時針|左轉|counter.?clockwise)\s*(?:旋轉|rotate)?\s*(\d+)\s*(?:度|°|deg)?', inst)
    if m:
        ops.append({"op": "rotate", "angle": -int(m.group(1))})

    m = re.search(r'(?:旋轉|rotate)\s*(\d+)\s*(?:度|°|deg)?', inst)
    if m and not ops:
        ops.append({"op": "rotate", "angle": int(m.group(1))})

    # Color patterns
    color_map = {
        "紅": [255, 0, 0], "紅色": [255, 0, 0], "red": [255, 0, 0],
        "藍": [0, 0, 255], "藍色": [0, 0, 255], "blue": [0, 0, 255],
        "綠": [0, 255, 0], "綠色": [0, 255, 0], "green": [0, 255, 0],
        "白": [255, 255, 255], "白色": [255, 255, 255], "white": [255, 255, 255],
        "黃": [255, 255, 0], "黃色": [255, 255, 0], "yellow": [255, 255, 0],
        "紫": [128, 0, 255], "紫色": [128, 0, 255], "purple": [128, 0, 255],
        "橙": [255, 165, 0], "橙色": [255, 165, 0], "orange": [255, 165, 0],
    }
    for name, rgb in color_map.items():
        if name in inst:
            ops.append({"op": "color", "rgb": rgb, "name": name})
            break

    if not ops:
        # Fallback: treat as unknown instruction, return raw text
        ops.append({"op": "unknown", "raw": instruction})

    return {"instruction": instruction, "operations": ops}


# ── DSL Compiler ─────────────────────────────────────────────────────────────

def compile_dsl(dsl: dict, assets_dir: Path) -> dict:
    """Compile a Scene DSL into a planning job specification.

    Returns a job spec that can be executed by the planning engine.
    Does NOT execute the plan — just compiles it.

    SIMULATION_ONLY.
    """
    errors = validate_dsl(dsl)
    if errors:
        return {"success": False, "errors": errors}

    scene = dsl["scene"]
    drone_count = scene["drones"]
    title = scene.get("title", "Untitled")
    safety_profile = scene.get("safety_profile", "safety_first")
    job_id = f"dsl_{uuid.uuid4().hex[:8]}"

    compiled_frames = []
    for i, frame in enumerate(scene.get("frames", [])):
        ftype = frame["type"]
        frame_id = frame.get("id", f"frame_{i}")

        if ftype == "takeoff_blue":
            compiled_frames.append({
                "frame_id": frame_id,
                "type": "takeoff_blue",
                "duration": frame.get("duration", 8),
                "action": "generate_ground_grid_and_takeoff",
            })

        elif ftype == "image_formation":
            asset_path = frame.get("asset", "")
            # Resolve asset path
            full_path = assets_dir / asset_path if asset_path else None
            compiled_frames.append({
                "frame_id": frame_id,
                "type": "image_formation",
                "asset": asset_path,
                "asset_resolved": str(full_path) if full_path and full_path.exists() else None,
                "hold": frame.get("hold", 6),
                "fit": frame.get("fit", "center"),
                "scale": frame.get("scale", 1.0),
                "action": "generate_formation_from_image",
                "drone_count": drone_count,
            })

        elif ftype == "transform":
            instruction = frame.get("instruction", "")
            parsed = parse_instruction(instruction)
            compiled_frames.append({
                "frame_id": frame_id,
                "type": "transform",
                "instruction": instruction,
                "parsed_ops": parsed["operations"],
                "duration": frame.get("duration", 5),
                "action": "apply_transform_to_current_formation",
            })

        elif ftype == "color_change":
            compiled_frames.append({
                "frame_id": frame_id,
                "type": "color_change",
                "color": frame.get("color", [255, 255, 255]),
                "pattern": frame.get("pattern", "all"),
                "duration": frame.get("duration", 2),
                "action": "change_led_colors",
            })

        elif ftype == "hold":
            compiled_frames.append({
                "frame_id": frame_id,
                "type": "hold",
                "duration": frame.get("duration", 5),
                "action": "hold_current_formation",
            })

        elif ftype == "landing_blue":
            compiled_frames.append({
                "frame_id": frame_id,
                "type": "landing_blue",
                "duration": frame.get("duration", 8),
                "action": "land_all_drones",
            })

    # Compile obstacles
    compiled_obstacles = []
    for obs in scene.get("obstacles", []):
        compiled_obstacles.append({
            "ref": obs.get("ref", ""),
            "avoid": obs.get("avoid", True),
        })

    # Timing summary
    total_duration = sum(f.get("duration") or f.get("hold", 0) for f in compiled_frames)

    # Point insufficiency warnings
    point_warnings = []
    if drone_count < 20:
        point_warnings.append("LOW_COUNT: < 20 drones, only simple shapes possible")
    elif drone_count < 50:
        point_warnings.append("MODERATE_COUNT: 20-50 drones, symbols and outlines OK")
    elif drone_count < 200:
        point_warnings.append("GOOD_COUNT: 50-200 drones, detailed logos and IP art possible")
    elif drone_count < 1000:
        point_warnings.append("HIGH_COUNT: 200-1000 drones, high-detail formations possible")
    else:
        point_warnings.append(f"MASSIVE_SCALE: {drone_count} drones, full video-frame detail possible")

    result = {
        "success": True,
        "job_id": job_id,
        "safety": "SIMULATION_ONLY",
        "title": title,
        "drone_count": drone_count,
        "safety_profile": safety_profile,
        "total_duration_sec": total_duration,
        "frame_count": len(compiled_frames),
        "frames": compiled_frames,
        "obstacles": compiled_obstacles,
        "warnings": point_warnings,
        "compilation_version": "v1.0",
    }

    logger.info("DSL compiled: '%s' → %d frames, %d drones, %.0fs, job=%s",
                title, len(compiled_frames), drone_count, total_duration, job_id)
    return result


def parse_yaml_dsl(yaml_text: str) -> dict:
    """Parse YAML text into a DSL dict, with safety checks."""
    # Safety: reject if YAML looks like it contains executable code
    if "!!python" in yaml_text or "!!ruby" in yaml_text:
        raise ValueError("SAFETY VIOLATION: YAML contains executable code tags")

    try:
        return yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}") from e


def merge_dsl_patch(base_dsl: dict, patch: dict) -> dict:
    """Merge an LLM-generated patch into an existing Scene DSL.

    The patch can:
    - Override scene-level fields (title, drones, safety_profile)
    - Add/modify/remove individual frames by id
    - Add/remove obstacles

    Safety: patch is validated before merge. Forbidden patterns rejected.

    Returns merged DSL dict.
    """
    import copy
    merged = copy.deepcopy(base_dsl)
    scene = merged.setdefault("scene", {})
    patch_scene = patch.get("scene", patch)  # handle both {scene:{...}} and flat

    # Validate patch for safety
    errors = validate_dsl({"scene": {**scene, **patch_scene, "frames": scene.get("frames", [])}})
    # Only check for safety violations, not missing fields
    safety_errors = [e for e in errors if "SAFETY VIOLATION" in e]
    if safety_errors:
        raise ValueError(f"Patch rejected: {safety_errors}")

    # Merge scene-level fields
    for key in ["title", "drones", "safety_profile", "camera"]:
        if key in patch_scene:
            scene[key] = patch_scene[key]

    # Merge frames
    if "frames" in patch_scene:
        existing_frames = {f.get("id"): f for f in scene.get("frames", [])}
        for patch_frame in patch_scene["frames"]:
            fid = patch_frame.get("id")
            if patch_frame.get("_delete"):
                existing_frames.pop(fid, None)
            elif fid and fid in existing_frames:
                existing_frames[fid].update(patch_frame)
            else:
                existing_frames[fid or f"frame_{len(existing_frames)}"] = patch_frame
        scene["frames"] = list(existing_frames.values())

    # Merge obstacles
    if "obstacles" in patch_scene:
        scene["obstacles"] = patch_scene["obstacles"]

    logger.info("DSL patch merged: %d frame updates", len(patch_scene.get("frames", [])))
    return merged
