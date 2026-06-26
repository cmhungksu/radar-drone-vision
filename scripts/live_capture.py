#!/usr/bin/env python3
"""Live capture and inference from radar hardware or dataset simulator.

Usage:
    python scripts/live_capture.py \
        --device simulator \
        --dataset zenodo77 \
        --speed 1.0
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):  # type: ignore[override]
        return it

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("live_capture")


# ------------------------------------------------------------------ #
# Simulator: replays dataset samples as if they were live frames
# ------------------------------------------------------------------ #

class DatasetSimulator:
    """Replay dataset samples as a simulated radar stream."""

    def __init__(self, dataset, speed: float = 1.0, loop: bool = True):
        self.dataset = dataset
        self.speed = max(speed, 0.01)
        self.loop = loop
        self._idx = 0
        self._n = len(dataset)
        self._frame_interval = 0.5 / self.speed  # assume 0.5s per sample at 1x

    def connect(self) -> None:
        logger.info(
            "Simulator connected — replaying %d samples at %.1fx speed",
            self._n, self.speed,
        )

    def read_frame(self) -> Optional[Dict[str, Any]]:
        """Read next frame. Returns None when finished (if not looping)."""
        if self._idx >= self._n:
            if self.loop:
                self._idx = 0
            else:
                return None

        sample = self.dataset[self._idx]
        frame = {
            "signal": sample.signal,
            "label": sample.label,
            "label_binary": sample.label_binary,
            "sample_id": sample.sample_id,
            "timestamp": time.time(),
            "frame_idx": self._idx,
        }
        self._idx += 1
        time.sleep(self._frame_interval)
        return frame

    def close(self) -> None:
        logger.info("Simulator closed after %d frames.", self._idx)


# ------------------------------------------------------------------ #
# Inference engine
# ------------------------------------------------------------------ #

class InferenceEngine:
    """Load a trained model and run inference on feature vectors."""

    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.model_type: Optional[str] = None
        self.feature_type: str = "proposed_regularized_complex_log_fft"

        if model_path is not None:
            self._load(Path(model_path))

    def _load(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Model file not found: %s — inference will return random scores.", path)
            return

        suffix = path.suffix.lower()
        if suffix == ".joblib":
            import joblib
            data = joblib.load(path)
            self.model = data.get("model")
            self.model_type = "sra"
            self.feature_type = data.get("feature_type", self.feature_type)
            logger.info("Loaded SRA model from %s", path)
        elif suffix in (".pt", ".pth"):
            import torch
            from radar_drone_vision.torch_models.cnn import SmallRadarCNN

            ckpt = torch.load(path, map_location="cpu", weights_only=False)
            mcfg = ckpt.get("model_config", {})
            model = SmallRadarCNN(
                in_channels=mcfg.get("in_channels", 2),
                num_classes=mcfg.get("num_classes", 2),
                dropout=mcfg.get("dropout", 0.3),
            )
            model.load_state_dict(ckpt["model_state_dict"])
            model.eval()
            self.model = model
            self.model_type = "cnn"
            self.feature_type = ckpt.get("feature_type", "proposed_complex_image")
            logger.info("Loaded CNN model from %s", path)
        else:
            logger.warning("Unknown model format: %s", suffix)

    def predict(self, signal: np.ndarray) -> Dict[str, Any]:
        """Run inference on a single signal.

        Returns dict with keys: prediction, confidence, label, inference_time_ms.
        """
        from radar_drone_vision.features.extractors import extract_features

        t0 = time.perf_counter()

        if self.model is None:
            # Fallback: random prediction
            pred = int(np.random.randint(0, 2))
            conf = float(np.random.uniform(0.4, 0.6))
            dt = (time.perf_counter() - t0) * 1000
            return {
                "prediction": pred,
                "confidence": conf,
                "label": "UAV" if pred == 1 else "non-UAV",
                "inference_time_ms": dt,
                "note": "No model loaded — random prediction",
            }

        if self.model_type == "sra":
            X = extract_features([signal], self.feature_type, {"flatten": True})
            score = float(self.model.decision_function(X)[0])
            pred = int(score > 0)
            # Map score to a pseudo-confidence in [0, 1]
            conf = float(1.0 / (1.0 + np.exp(-score * 0.01)))
        elif self.model_type == "cnn":
            import torch

            X = extract_features([signal], self.feature_type, {"flatten": False})
            if X.ndim == 3 and "complex_image" in self.feature_type:
                n, h, w = X.shape
                half_w = w // 2
                X = np.stack([X[:, :, :half_w], X[:, :, half_w:]], axis=1)
            elif X.ndim == 3:
                X = X[:, np.newaxis, :, :]
            xt = torch.from_numpy(X.astype(np.float32))
            with torch.no_grad():
                logits = self.model(xt)
                probs = torch.softmax(logits, dim=1)
            pred = int(logits.argmax(dim=1).item())
            conf = float(probs[0, pred].item())
        else:
            pred, conf = 0, 0.5

        dt = (time.perf_counter() - t0) * 1000
        return {
            "prediction": pred,
            "confidence": conf,
            "label": "UAV" if pred == 1 else "non-UAV",
            "inference_time_ms": dt,
        }


# ------------------------------------------------------------------ #
# Live capture loop
# ------------------------------------------------------------------ #

def run_live_capture(args: argparse.Namespace) -> None:
    # Load dataset for simulator
    dataset = None
    if args.device == "simulator":
        if args.dataset in ("zenodo77", "zenodo_77ghz_fmcw"):
            from radar_drone_vision.datasets.zenodo77 import Zenodo77Dataset

            data_dir = _PROJECT_ROOT / "data" / "processed" / "zenodo_77ghz_fmcw"
            if not data_dir.exists():
                data_dir = _PROJECT_ROOT / "data" / "raw" / "zenodo_77ghz_fmcw"
            if not data_dir.exists():
                print(
                    f"\n[ERROR] Dataset not found: {data_dir}\n"
                    "  Run: python scripts/download_zenodo.py --out data/raw/zenodo_77ghz_fmcw\n"
                )
                sys.exit(1)
            dataset = Zenodo77Dataset(data_dir)
        else:
            # Use synthetic data as fallback
            from radar_drone_vision.datasets.synthetic import SyntheticGenerator

            logger.info("Using synthetic data for simulation (dataset=%s not found).", args.dataset)
            gen = SyntheticGenerator(seed=args.seed)
            samples = gen.generate_balanced_dataset(n_per_class=50)

            # Wrap in a simple list-like object
            class _ListDataset:
                def __init__(self, items):
                    self._items = items
                def __len__(self):
                    return len(self._items)
                def __getitem__(self, idx):
                    return self._items[idx]

            dataset = _ListDataset(samples)
    else:
        print(f"\n[ERROR] Device '{args.device}' is not supported yet.")
        print("  Supported devices: simulator")
        print("  For real hardware, implement the device driver in src/radar_drone_vision/hardware/")
        sys.exit(1)

    # Create simulator
    sim = DatasetSimulator(dataset, speed=args.speed, loop=not args.no_loop)
    sim.connect()

    # Create inference engine
    model_path = args.model
    if model_path is None:
        # Try to find a model automatically
        for candidate in ["models/sra_model.joblib", "models/cnn_best.pt"]:
            p = _PROJECT_ROOT / candidate
            if p.exists():
                model_path = str(p)
                break
    engine = InferenceEngine(model_path)

    # Stats
    timestamps = []
    inference_times = []
    correct = 0
    total = 0
    n_frames = args.n_frames

    print("\n" + "=" * 70)
    print(f"  Live Capture — device={args.device}  speed={args.speed}x  model={model_path or 'none'}")
    print("=" * 70)
    print(f"  {'Frame':>6s} | {'Prediction':>10s} | {'Conf':>6s} | {'GT':>10s} | {'Match':>5s} | {'Latency':>8s}")
    print("-" * 60)

    try:
        for i in range(n_frames):
            frame = sim.read_frame()
            if frame is None:
                logger.info("No more frames.")
                break

            result = engine.predict(frame["signal"])
            timestamps.append(frame["timestamp"])
            inference_times.append(result["inference_time_ms"])

            gt_label = frame.get("label", "?")
            gt_binary = frame.get("label_binary", -1)
            match = result["prediction"] == gt_binary if gt_binary >= 0 else None

            if match is not None:
                total += 1
                correct += int(match)

            match_str = "OK" if match else ("MISS" if match is not None else "?")

            if i < 30 or i % 50 == 0 or i == n_frames - 1:
                print(
                    f"  {i:>6d} | {result['label']:>10s} | {result['confidence']:>6.3f} | "
                    f"{gt_label:>10s} | {match_str:>5s} | {result['inference_time_ms']:>6.1f}ms"
                )

    except KeyboardInterrupt:
        print("\n  [Ctrl+C] Stopping capture...")
    finally:
        sim.close()

    # Summary
    if timestamps:
        dt_arr = np.array(inference_times)
        print("\n" + "=" * 70)
        print("  Capture Statistics")
        print("=" * 70)
        print(f"  Total frames:      {len(timestamps)}")
        if total > 0:
            print(f"  Accuracy:          {correct / total:.4f} ({correct}/{total})")
        print(f"  Inference latency: mean={dt_arr.mean():.1f}ms  "
              f"std={dt_arr.std():.1f}ms  "
              f"p95={np.percentile(dt_arr, 95):.1f}ms  "
              f"max={dt_arr.max():.1f}ms")
        if len(timestamps) > 1:
            intervals = np.diff(timestamps)
            print(f"  Frame interval:    mean={intervals.mean():.3f}s  "
                  f"std={intervals.std():.3f}s")
        print("=" * 70)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live capture and inference from radar or simulator."
    )
    parser.add_argument(
        "--device", type=str, default="simulator",
        help="Device type: simulator (default), or hardware driver name",
    )
    parser.add_argument("--dataset", type=str, default="zenodo77", help="Dataset for simulator replay")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier (default: 1.0)")
    parser.add_argument("--model", type=str, default=None, help="Path to model file for inference")
    parser.add_argument("--n-frames", type=int, default=100, help="Max frames to capture (default: 100)")
    parser.add_argument("--no-loop", action="store_true", help="Do not loop dataset")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser.parse_args()


if __name__ == "__main__":
    run_live_capture(parse_args())
