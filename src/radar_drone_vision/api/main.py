"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from radar_drone_vision.api.routes_dataset import router as dataset_router
from radar_drone_vision.api.routes_hardware import router as hardware_router
from radar_drone_vision.api.routes_inference import router as inference_router
from radar_drone_vision.api.routes_reports import router as reports_router
from radar_drone_vision.utils.logging import setup_logging

setup_logging()

app = FastAPI(
    title="Radar Drone Vision API",
    description="Low-altitude radar AI validation platform for UAV / bird discrimination",
    version="0.1.0",
)

# CORS – allow React dev server and any localhost origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(dataset_router)
app.include_router(inference_router)
app.include_router(hardware_router)
app.include_router(reports_router)
