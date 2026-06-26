"""Synthetic micro-Doppler data generator for testing and development.

**IMPORTANT**: Results produced with synthetic data are for algorithm testing
and visualisation only.  They must **never** be reported or treated as real
radar performance metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .base import RadarSample

logger = logging.getLogger(__name__)

_SYNTHETIC_TAG = "SYNTHETIC"


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass
class UAVParams:
    """Parameters for synthetic UAV rotor micro-Doppler."""

    n_rotors: int = 4
    rotor_rate_hz: float = 150.0  # blade rotation rate
    rotor_rate_std: float = 10.0  # variation across rotors
    n_harmonics: int = 5
    blade_length_m: float = 0.15
    body_velocity_mps: float = 5.0
    snr_db: float = 15.0


@dataclass
class BirdParams:
    """Parameters for synthetic bird wingbeat micro-Doppler."""

    wingbeat_freq_hz: float = 8.0  # wingbeat frequency
    wingbeat_freq_std: float = 1.5
    max_wing_velocity_mps: float = 3.0
    body_velocity_mps: float = 10.0
    glide_fraction: float = 0.2  # fraction of time spent gliding
    snr_db: float = 12.0


@dataclass
class ClutterParams:
    """Noise floor and clutter parameters."""

    noise_floor_db: float = -30.0
    clutter_rcs_db: float = -20.0
    clutter_doppler_spread_hz: float = 2.0
    n_clutter_sources: int = 3


@dataclass
class SpatialParams:
    """Range / angle / velocity metadata for airspace visualisation."""

    range_min_m: float = 50.0
    range_max_m: float = 2000.0
    azimuth_min_deg: float = -60.0
    azimuth_max_deg: float = 60.0
    elevation_min_deg: float = 0.0
    elevation_max_deg: float = 45.0


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class SyntheticGenerator:
    """Generate synthetic radar micro-Doppler samples.

    All output is clearly marked as synthetic.
    """

    def __init__(
        self,
        carrier_frequency_hz: float = 77.0e9,
        sample_duration_s: float = 0.5,
        sample_rate_hz: float = 2000.0,
        seed: int = 42,
    ) -> None:
        self.fc = carrier_frequency_hz
        self.duration = sample_duration_s
        self.fs = sample_rate_hz
        self.rng = np.random.default_rng(seed)
        self._wavelength = 3e8 / self.fc
        self._n_samples = int(self.duration * self.fs)

    # ------------------------------------------------------------------
    # UAV rotor signature
    # ------------------------------------------------------------------

    def _generate_uav_signal(self, params: UAVParams) -> np.ndarray:
        t = np.linspace(0, self.duration, self._n_samples, endpoint=False)
        signal = np.zeros(self._n_samples, dtype=np.float64)

        # Body Doppler
        body_phase = 2 * np.pi * (2 * params.body_velocity_mps / self._wavelength) * t
        signal += np.cos(body_phase)

        # Rotor harmonics — stable parallel lines in spectrogram
        for r in range(params.n_rotors):
            rate = params.rotor_rate_hz + self.rng.normal(0, params.rotor_rate_std)
            for h in range(1, params.n_harmonics + 1):
                freq = h * rate
                amp = 1.0 / h  # harmonics decay
                tip_vel = 2 * np.pi * rate * params.blade_length_m
                doppler_shift = 2 * tip_vel / self._wavelength
                phase = self.rng.uniform(0, 2 * np.pi)
                signal += amp * np.cos(2 * np.pi * freq * t + phase)

        return signal / (np.max(np.abs(signal)) + 1e-12)

    # ------------------------------------------------------------------
    # Bird wingbeat signature
    # ------------------------------------------------------------------

    def _generate_bird_signal(self, params: BirdParams) -> np.ndarray:
        t = np.linspace(0, self.duration, self._n_samples, endpoint=False)
        signal = np.zeros(self._n_samples, dtype=np.float64)

        # Body Doppler
        body_phase = 2 * np.pi * (2 * params.body_velocity_mps / self._wavelength) * t
        signal += np.cos(body_phase)

        # Sinusoidal wingbeat modulation
        wb_freq = params.wingbeat_freq_hz + self.rng.normal(0, params.wingbeat_freq_std)
        wing_vel = params.max_wing_velocity_mps * np.sin(2 * np.pi * wb_freq * t)

        # Glide periods (zero wing velocity)
        glide_mask = self.rng.random(self._n_samples) < params.glide_fraction
        wing_vel[glide_mask] = 0.0

        wing_doppler = 2 * wing_vel / self._wavelength
        wing_phase = 2 * np.pi * np.cumsum(wing_doppler) / self.fs
        signal += 0.6 * np.cos(wing_phase)

        return signal / (np.max(np.abs(signal)) + 1e-12)

    # ------------------------------------------------------------------
    # Noise and clutter
    # ------------------------------------------------------------------

    def _add_noise_and_clutter(
        self, signal: np.ndarray, snr_db: float, clutter: Optional[ClutterParams] = None
    ) -> np.ndarray:
        # Additive white Gaussian noise
        sig_power = np.mean(signal**2)
        noise_power = sig_power / (10 ** (snr_db / 10))
        noise = self.rng.normal(0, np.sqrt(noise_power), len(signal))

        out = signal + noise

        if clutter is not None:
            t = np.linspace(0, self.duration, self._n_samples, endpoint=False)
            for _ in range(clutter.n_clutter_sources):
                c_amp = 10 ** (clutter.clutter_rcs_db / 20)
                c_freq = self.rng.normal(0, clutter.clutter_doppler_spread_hz)
                c_phase = self.rng.uniform(0, 2 * np.pi)
                out += c_amp * np.cos(2 * np.pi * c_freq * t + c_phase)

        return out

    # ------------------------------------------------------------------
    # Spatial metadata
    # ------------------------------------------------------------------

    def _random_spatial(self, sp: SpatialParams) -> dict:
        return {
            "range_m": float(self.rng.uniform(sp.range_min_m, sp.range_max_m)),
            "azimuth_deg": float(self.rng.uniform(sp.azimuth_min_deg, sp.azimuth_max_deg)),
            "elevation_deg": float(self.rng.uniform(sp.elevation_min_deg, sp.elevation_max_deg)),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_uav_samples(
        self,
        n: int = 100,
        uav_params: Optional[UAVParams] = None,
        clutter_params: Optional[ClutterParams] = None,
        spatial_params: Optional[SpatialParams] = None,
    ) -> List[RadarSample]:
        params = uav_params or UAVParams()
        clutter = clutter_params or ClutterParams()
        sp = spatial_params or SpatialParams()
        samples: List[RadarSample] = []

        for i in range(n):
            sig = self._generate_uav_signal(params)
            sig = self._add_noise_and_clutter(sig, params.snr_db, clutter)
            spatial = self._random_spatial(sp)
            vel = params.body_velocity_mps + self.rng.normal(0, 1.0)

            samples.append(
                RadarSample(
                    sample_id=f"synth_uav_{i:06d}",
                    signal=sig.astype(np.float32),
                    label="synthetic_uav",
                    label_binary=1,
                    radar_type="fmcw",
                    carrier_frequency_hz=self.fc,
                    raw_shape=(len(sig),),
                    range_m=spatial["range_m"],
                    azimuth_deg=spatial["azimuth_deg"],
                    elevation_deg=spatial["elevation_deg"],
                    velocity_mps=float(vel),
                    track_id=f"synth_track_uav_{i // 10:04d}",
                    timestamp=float(i * self.duration),
                    metadata={
                        "source": _SYNTHETIC_TAG,
                        "WARNING": "Synthetic data — do NOT treat as real performance.",
                        "generator_params": {
                            "n_rotors": params.n_rotors,
                            "rotor_rate_hz": params.rotor_rate_hz,
                        },
                    },
                )
            )
        logger.info("Generated %d synthetic UAV samples", n)
        return samples

    def generate_bird_samples(
        self,
        n: int = 100,
        bird_params: Optional[BirdParams] = None,
        clutter_params: Optional[ClutterParams] = None,
        spatial_params: Optional[SpatialParams] = None,
    ) -> List[RadarSample]:
        params = bird_params or BirdParams()
        clutter = clutter_params or ClutterParams()
        sp = spatial_params or SpatialParams()
        samples: List[RadarSample] = []

        for i in range(n):
            sig = self._generate_bird_signal(params)
            sig = self._add_noise_and_clutter(sig, params.snr_db, clutter)
            spatial = self._random_spatial(sp)
            vel = params.body_velocity_mps + self.rng.normal(0, 2.0)

            samples.append(
                RadarSample(
                    sample_id=f"synth_bird_{i:06d}",
                    signal=sig.astype(np.float32),
                    label="synthetic_bird",
                    label_binary=0,
                    radar_type="fmcw",
                    carrier_frequency_hz=self.fc,
                    raw_shape=(len(sig),),
                    range_m=spatial["range_m"],
                    azimuth_deg=spatial["azimuth_deg"],
                    elevation_deg=spatial["elevation_deg"],
                    velocity_mps=float(vel),
                    track_id=f"synth_track_bird_{i // 10:04d}",
                    timestamp=float(i * self.duration),
                    metadata={
                        "source": _SYNTHETIC_TAG,
                        "WARNING": "Synthetic data — do NOT treat as real performance.",
                        "generator_params": {
                            "wingbeat_freq_hz": params.wingbeat_freq_hz,
                        },
                    },
                )
            )
        logger.info("Generated %d synthetic bird samples", n)
        return samples

    def generate_balanced_dataset(
        self,
        n_per_class: int = 100,
        uav_params: Optional[UAVParams] = None,
        bird_params: Optional[BirdParams] = None,
        clutter_params: Optional[ClutterParams] = None,
        spatial_params: Optional[SpatialParams] = None,
    ) -> List[RadarSample]:
        """Generate a balanced dataset with equal UAV and bird samples."""
        uav = self.generate_uav_samples(n_per_class, uav_params, clutter_params, spatial_params)
        bird = self.generate_bird_samples(n_per_class, bird_params, clutter_params, spatial_params)
        combined = uav + bird
        self.rng.shuffle(combined)  # type: ignore[arg-type]
        return combined
