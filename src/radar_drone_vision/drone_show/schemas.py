"""Pydantic schemas for Drone Show Studio."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class FormationPoint(BaseModel):
    """A single drone position in a formation frame."""
    point_id: str
    xyz: List[float] = Field(..., min_length=3, max_length=3)
    rgb565: int = Field(ge=0, le=65535)
    rgb888: List[int] = Field(default=[0, 0, 255], min_length=3, max_length=3)
    importance: float = Field(ge=0.0, le=1.0)
    source_feature: str = ""
    group_id: str = ""


class FormationFrame(BaseModel):
    """A complete drone formation (one 'image' converted to points)."""
    frame_id: str
    points: List[FormationPoint]
    drone_count: int
    detail_score: float = 0.0
    warnings: List[str] = []
    image_width: int = 0
    image_height: int = 0


class PointGenRequest(BaseModel):
    """Request to generate formation points from an uploaded image."""
    asset_id: str
    drone_count: int = Field(default=50, ge=5, le=2000)
    z_height: float = Field(default=50.0, ge=10.0, le=200.0)
    scale: float = Field(default=1.0, ge=0.1, le=5.0)


class PointGenResponse(BaseModel):
    """Response with generated formation frame (downsampled for frontend)."""
    frame: FormationFrame
    palette: List[List[int]] = []  # dominant colors [[r,g,b], ...]


class BezierSegment(BaseModel):
    """One drone's path segment between two formation states."""
    drone_id: str
    segment_id: str
    from_frame: str
    to_frame: str
    control_points: List[List[float]]
    duration_sec: float
    led_timeline: List[dict] = []


class TimelinePlan(BaseModel):
    """Complete show timeline with all drone paths."""
    plan_id: str
    drone_count: int
    total_duration_sec: float
    frames: List[str] = []
    drones: List[dict] = []  # [{drone_id, segments: [BezierSegment]}]
    metadata: dict = {}


class RiskSummary(BaseModel):
    """Feasibility risk report for a planning job."""
    min_drone_distance: float
    max_speed_index: float
    path_crossing_count: int
    detail_score: float
    warnings: List[str] = []
