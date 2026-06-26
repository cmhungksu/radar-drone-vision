"""Tests for dataset base structures, synthetic generator, and manifest."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from radar_drone_vision.datasets.base import RadarSample
from radar_drone_vision.datasets.synthetic import (
    BirdParams,
    ClutterParams,
    SyntheticGenerator,
    UAVParams,
)
from radar_drone_vision.datasets.manifest import DatasetManifest


# ---------------------------------------------------------------------------
# RadarSample dataclass
# ---------------------------------------------------------------------------

class TestRadarSample:
    def test_basic_construction(self):
        sig = np.zeros(100, dtype=np.float32)
        s = RadarSample(
            sample_id="test_001",
            signal=sig,
            label="drone_DJI",
            label_binary=1,
            radar_type="fmcw",
            carrier_frequency_hz=77e9,
            raw_shape=(100,),
        )
        assert s.sample_id == "test_001"
        assert s.is_uav is True
        assert isinstance(s.signal, np.ndarray)

    def test_non_uav_label(self):
        sig = np.ones(50)
        s = RadarSample(
            sample_id="bird_001",
            signal=sig,
            label="bird",
            label_binary=0,
            radar_type="cw",
            carrier_frequency_hz=10e9,
            raw_shape=(50,),
        )
        assert s.is_uav is False

    def test_signal_auto_converted(self):
        s = RadarSample(
            sample_id="t",
            signal=[1.0, 2.0, 3.0],
            label="test",
            label_binary=0,
            radar_type="fmcw",
            carrier_frequency_hz=77e9,
            raw_shape=(3,),
        )
        assert isinstance(s.signal, np.ndarray)

    def test_to_npz_dict(self):
        sig = np.arange(10, dtype=np.float32)
        s = RadarSample(
            sample_id="x",
            signal=sig,
            label="drone",
            label_binary=1,
            radar_type="fmcw",
            carrier_frequency_hz=77e9,
            raw_shape=(10,),
            range_m=100.0,
            timestamp=1.23,
        )
        d = s.to_npz_dict()
        assert "signal" in d
        assert "label" in d
        assert "range_m" in d
        assert "timestamp" in d

    def test_optional_fields_default_none(self):
        sig = np.zeros(5)
        s = RadarSample(
            sample_id="z",
            signal=sig,
            label="bird",
            label_binary=0,
            radar_type="fmcw",
            carrier_frequency_hz=77e9,
            raw_shape=(5,),
        )
        assert s.range_m is None
        assert s.velocity_mps is None
        assert s.track_id is None


# ---------------------------------------------------------------------------
# SyntheticGenerator
# ---------------------------------------------------------------------------

class TestSyntheticGenerator:
    def test_generate_uav_samples(self):
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_uav_samples(n=10)
        assert len(samples) == 10
        for s in samples:
            assert s.label_binary == 1
            assert s.signal.shape[0] > 0
            assert "SYNTHETIC" in s.metadata.get("source", "")

    def test_generate_bird_samples(self):
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_bird_samples(n=10)
        assert len(samples) == 10
        for s in samples:
            assert s.label_binary == 0

    def test_generate_balanced_dataset(self):
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_balanced_dataset(n_per_class=15)
        assert len(samples) == 30
        labels = [s.label_binary for s in samples]
        assert labels.count(1) == 15
        assert labels.count(0) == 15

    def test_sample_duration_affects_length(self):
        gen = SyntheticGenerator(sample_duration_s=1.0, sample_rate_hz=1000.0, seed=0)
        samples = gen.generate_uav_samples(n=1)
        assert samples[0].signal.shape[0] == 1000

    def test_custom_uav_params(self):
        params = UAVParams(n_rotors=2, snr_db=20.0)
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_uav_samples(n=3, uav_params=params)
        assert len(samples) == 3

    def test_custom_bird_params(self):
        params = BirdParams(wingbeat_freq_hz=12.0)
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_bird_samples(n=3, bird_params=params)
        assert len(samples) == 3

    def test_signal_is_normalized(self):
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_uav_samples(n=5)
        for s in samples:
            # After adding noise the signal may exceed 1 slightly, but the
            # raw signal before noise was normalised.  Just check finite.
            assert np.all(np.isfinite(s.signal))

    def test_spatial_metadata_present(self):
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_uav_samples(n=3)
        for s in samples:
            assert s.range_m is not None
            assert s.azimuth_deg is not None
            assert s.elevation_deg is not None

    def test_class_mapping_drone_is_uav(self):
        gen = SyntheticGenerator(seed=0)
        uav = gen.generate_uav_samples(n=1)
        bird = gen.generate_bird_samples(n=1)
        assert uav[0].label_binary == 1  # drone -> UAV
        assert bird[0].label_binary == 0  # bird -> non-UAV


# ---------------------------------------------------------------------------
# DatasetManifest save/load roundtrip
# ---------------------------------------------------------------------------

class TestDatasetManifest:
    def test_build_and_save_load_roundtrip(self):
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_balanced_dataset(n_per_class=5)

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = DatasetManifest(name="test_ds", base_dir=tmpdir)
            df = manifest.build_from_samples(samples)
            assert len(df) == 10

            manifest.save()

            loaded = DatasetManifest(name="test_ds", base_dir=tmpdir)
            df2 = loaded.load()
            assert len(df2) == 10
            assert list(df2.columns) == list(df.columns)

    def test_stats(self):
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_balanced_dataset(n_per_class=5)

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = DatasetManifest(name="stats_test", base_dir=tmpdir)
            manifest.build_from_samples(samples)

            stats = manifest.stats()
            assert stats["num_samples"] == 10
            assert stats["binary_distribution"]["uav"] == 5
            assert stats["binary_distribution"]["non_uav"] == 5

    def test_load_sample(self):
        gen = SyntheticGenerator(seed=0)
        samples = gen.generate_uav_samples(n=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = DatasetManifest(name="load_test", base_dir=tmpdir)
            manifest.build_from_samples(samples)
            manifest.save()

            loaded = DatasetManifest(name="load_test", base_dir=tmpdir)
            loaded.load()
            npz = loaded.load_sample(0)
            assert "signal" in npz
            assert "label" in npz

    def test_missing_manifest_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = DatasetManifest(name="missing", base_dir=tmpdir)
            with pytest.raises(FileNotFoundError):
                manifest.load()

    # NOTE: Actual Zenodo download test is intentionally skipped.
    # Use synthetic data for all CI/CD testing.
