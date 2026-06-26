"""Report and health-check API routes."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from radar_drone_vision.api.schemas import HealthResponse, ReportSummary
from radar_drone_vision.utils.io import load_json
from radar_drone_vision.utils.logging import get_logger

router = APIRouter(tags=["reports"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Return service health status and version."""
    from radar_drone_vision import __version__
    return HealthResponse(status="ok", version=__version__)


@router.get("/reports/latest", response_model=ReportSummary)
async def get_latest_report():
    """Return the most recently generated evaluation report."""
    reports_dir = Path("reports")
    if not reports_dir.exists():
        raise HTTPException(status_code=404, detail="No reports directory found")

    # Find JSON report files sorted by modification time (newest first)
    report_files = sorted(
        reports_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not report_files:
        raise HTTPException(status_code=404, detail="No report files found")

    latest = report_files[0]
    try:
        data = load_json(latest)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read report: {exc}") from exc

    return ReportSummary(
        report_path=str(latest),
        created_at=data.get("created_at", ""),
        accuracy=data.get("accuracy", 0.0),
        eer=data.get("eer", 0.0),
        model=data.get("model", ""),
        dataset=data.get("dataset", ""),
    )


@router.get("/reports", response_model=list[ReportSummary])
async def list_reports():
    """List all available evaluation reports."""
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return []

    results: list[ReportSummary] = []
    for rp in sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = load_json(rp)
            results.append(ReportSummary(
                report_path=str(rp),
                created_at=data.get("created_at", ""),
                accuracy=data.get("accuracy", 0.0),
                eer=data.get("eer", 0.0),
                model=data.get("model", ""),
                dataset=data.get("dataset", ""),
            ))
        except Exception:
            logger.warning("Skipping unreadable report: %s", rp)

    return results
