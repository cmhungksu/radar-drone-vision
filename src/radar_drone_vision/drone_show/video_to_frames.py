"""Video keyframe extraction for drone show animation.

Reads a video file, extracts keyframes based on visual change,
and outputs each keyframe as an image for formation generation.

PRIVATE CORE — SIMULATION_ONLY.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def extract_keyframes(
    video_path: str | Path,
    max_frames: int = 10,
    min_change_ratio: float = 0.15,
    output_dir: str | Path | None = None,
) -> List[dict]:
    """Extract keyframes from a video based on visual change.

    Computes frame-to-frame difference and keeps frames where
    the change exceeds min_change_ratio.

    Parameters:
        video_path: path to MP4/AVI/MOV video
        max_frames: maximum number of keyframes to extract
        min_change_ratio: minimum pixel change ratio to qualify as keyframe
        output_dir: if set, save keyframe PNGs here

    Returns:
        list of {frame_index, timestamp_sec, change_ratio, image_path?}
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    logger.info("Video: %s, %.1fs, %d frames, %.0f fps",
                Path(video_path).name, duration, total_frames, fps)

    prev_gray = None
    candidates = []

    # Sample every N frames (don't process every single frame)
    sample_step = max(1, total_frames // (max_frames * 10))

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_small = cv2.resize(gray, (160, 120))

            if prev_gray is not None:
                diff = cv2.absdiff(gray_small, prev_gray)
                change_ratio = float(np.mean(diff > 30)) # fraction of pixels changed
                candidates.append({
                    "frame_index": frame_idx,
                    "timestamp_sec": round(frame_idx / fps, 2),
                    "change_ratio": round(change_ratio, 4),
                    "frame_bgr": frame,
                })

            prev_gray = gray_small

        frame_idx += 1

    cap.release()

    if not candidates:
        logger.warning("No keyframes found in video")
        return []

    # Always include first and last frame
    # Filter by change_ratio threshold, then take top max_frames
    significant = [c for c in candidates if c["change_ratio"] >= min_change_ratio]

    # If too few significant changes, take evenly spaced
    if len(significant) < 3:
        step = max(1, len(candidates) // max_frames)
        significant = candidates[::step]

    # Sort by change_ratio descending, take top N
    significant.sort(key=lambda c: c["change_ratio"], reverse=True)
    selected = significant[:max_frames]
    # Re-sort by time
    selected.sort(key=lambda c: c["frame_index"])

    # Save keyframe images if output_dir specified
    results = []
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

    for i, kf in enumerate(selected):
        entry = {
            "frame_index": kf["frame_index"],
            "timestamp_sec": kf["timestamp_sec"],
            "change_ratio": kf["change_ratio"],
        }
        if output_dir:
            img_path = Path(output_dir) / f"keyframe_{i:03d}.png"
            cv2.imwrite(str(img_path), kf["frame_bgr"])
            entry["image_path"] = str(img_path)

        results.append(entry)
        del kf["frame_bgr"]  # free memory

    logger.info("Extracted %d keyframes from %d candidates", len(results), len(candidates))
    return results
