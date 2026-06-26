# Radar Drone Vision

**Low-altitude radar AI validation platform for UAV / bird discrimination using micro-Doppler signatures.**

This project engineers the algorithms from the paper *"Regularized 2-D Complex-Log Spectral Analysis and Subspace Reliability Analysis of Micro-Doppler Signature for UAV Detection"* (Pattern Recognition) into a reproducible, extensible pipeline. It validates against a public 77 GHz FMCW dataset and provides hardware integration interfaces for real radar sensors.

---

## Paper Algorithm Overview

The paper addresses the challenge of distinguishing small UAVs from birds in radar returns. Both target types are slow, low-RCS, and low-altitude, making conventional kinematic discrimination unreliable. The key insight is that UAV rotor blades and bird wings produce distinct **micro-Doppler signatures**.

### 1. Regularized 2-D Complex-Log-Fourier Transform

The standard spectrogram discards phase information after the first FFT. This paper retains it:

```
1. Frame the signal:      X = [x₀, x₁, …, xₘ₋₁]
2. Per-frame FFT:         fᵢ = FFT(xᵢ) = mᵢ · exp(j·θᵢ)
3. Median regularisation: Cᵢ = median(mᵢ)
4. Complex log:           zᵢ = log(mᵢ + Cᵢ + ε) + j·(1/π)·θᵢ
5. Second FFT (time):     F₂ = FFT(z, axis=time)
```

The median regulariser suppresses noise amplification from the logarithm. The output is a 2-D complex feature matrix that preserves both magnitude and phase structure.

### 2. Subspace Reliability Analysis (SRA)

Instead of a single PCA subspace, SRA builds separate subspaces for UAV and non-UAV classes:

- Compute per-class covariance Σ₁, Σ₂ and between-class scatter Σ_b
- Form augmented matrices S₁ = Σ₁ + Σ_b, S₂ = Σ₂ + Σ_b
- Eigen-decompose each and retain leading eigenvectors (m₁=10 for UAV, m₂=100 for non-UAV)
- Score each sample by the Mahalanobis distance ratio g₁/g₂
- Classify as UAV if the ratio falls below a threshold

---

## Why Zenodo 77 GHz FMCW ≠ Paper's Thales X-band CW

The paper used a proprietary Thales Ground Master 60 X-band (9.5 GHz) CW radar. This project validates on a publicly available dataset:

| Aspect | Paper (Thales) | Public (Zenodo) |
|--------|---------------|-----------------|
| Frequency | 9.5 GHz (X-band) | 77 GHz (mmWave) |
| Waveform | CW | FMCW |
| Wavelength | ~32 mm | ~3.9 mm |
| Micro-Doppler scaling | Different | Different |
| Target set | Classified | Drones + birds + humans |
| DOI | N/A (proprietary) | 10.5281/zenodo.5845259 |

**Consequence**: Absolute metrics (EER values) will differ from the paper. This platform reproduces the *algorithm*, not the exact numbers. All reports clearly distinguish between:

- **Paper reproduction mode** — algorithm validation with approximate results
- **Public dataset mode** — Zenodo 77 GHz FMCW evaluation
- **Hardware mode** — real sensor alignment

---

## Quick Start

### Docker (recommended)

```bash
git clone <repo-url> && cd radar-drone-vision
docker compose up --build -d

# API:  http://localhost:8000
# Web:  http://localhost:5173
```

### Local installation

```bash
make install          # pip install -e ".[dev,notebook]"
```

---

## Dataset Download

```bash
make download
# Equivalent to:
# python scripts/download_zenodo.py --out data/raw/zenodo_77ghz
```

This downloads two files from Zenodo (DOI: 10.5281/zenodo.5845259):

- `ReadMe.txt` — dataset description and class labels
- `data_SAAB_SIRS_77GHz_FMCW.npy` — 75,868 radar samples (~1.6 GB)

After downloading, prepare the processed dataset:

```bash
make prepare
```

This creates `data/processed/zenodo_77ghz/manifest.parquet` and individual `.npz` sample files.

---

## Training

### SRA (paper algorithm)

```bash
make train-sra
# Or manually:
python scripts/train_sra.py \
    --config configs/models/sra.yaml \
    --dataset zenodo77 \
    --feature proposed_regularized_complex_log_fft \
    --repeat 20 \
    --split half
```

The training runs 20 random 50/50 splits (matching the paper's protocol) and saves the best model to `models/sra_model.joblib`.

### CNN (PyTorch baseline)

```bash
make train-cnn
# Or manually:
python scripts/train_cnn.py \
    --config configs/models/cnn.yaml \
    --dataset zenodo77 \
    --feature proposed_complex_image \
    --epochs 50
```

Saves the best checkpoint to `models/cnn_best.pt` with ONNX export.

---

## Evaluation and Metrics

```bash
make eval-sra       # Evaluate SRA model
make eval-cnn       # Evaluate CNN model
make eval-all       # Full comparison report
```

### Metrics Explained

| Metric | Definition | Relevance |
|--------|-----------|-----------|
| **EER** | Equal Error Rate — the operating point where FAR = FRR | Single-number summary of detection performance |
| **FAR** | False Acceptance Rate — non-UAV misclassified as UAV (false alarm) | Critical for operational deployment |
| **FRR** | False Rejection Rate — UAV misclassified as non-UAV (missed detection) | Safety-critical metric |
| **FAR@FRR=1%** | FAR when FRR is held at 1% | Measures false alarm burden at high detection sensitivity |
| **AUC** | Area Under the ROC Curve | Threshold-independent discrimination ability |

Evaluation outputs are saved to `reports/` and include:
- Confusion matrices
- ROC and DET curves
- Threshold sweep tables
- Paper comparison table (`reports/paper_comparison.md`)

---

## Airspace Visualization

```bash
make airspace-demo
```

Generates 2-D radar sector plots, range-time and Doppler-time waterfalls, and target track visualisations. If the dataset provides range/azimuth/elevation coordinates, a 3-D airspace view is also produced. Outputs go to `reports/airspace_demo/`.

For datasets without full spatial coordinates, the visualisation uses available metadata and clearly labels any missing dimensions.

---

## Hardware Integration Guide

The platform is designed for future connection to real radar sensors. Hardware modules live in `src/radar_drone_vision/hardware/`.

### Supported interfaces

| Interface | Module | Status |
|-----------|--------|--------|
| Generic I/Q stream (UDP/TCP/serial/file) | `generic_iq.py` | Skeleton |
| TI mmWave (raw ADC, range-Doppler, point cloud) | `ti_mmwave.py` | Skeleton |
| Infineon radar SDK | `infineon.py` | Skeleton |
| Simulator (dataset replay) | `simulator.py` | Planned |

### Hardware device API

All devices implement a common interface:

```python
class RadarDevice:
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def read_frame(self) -> RadarFrame: ...
    def get_metadata(self) -> dict: ...
```

### Quick test with simulator

```bash
python scripts/live_capture.py --device simulator --dataset zenodo77 --speed 1.0
```

### Connecting real hardware

1. Create a new device class inheriting from `RadarDevice`
2. Implement `connect()`, `read_frame()`, `disconnect()`
3. Add a hardware config in `configs/hardware/`
4. The processing pipeline and inference work identically regardless of data source

---

## Project Structure

```
radar-drone-vision/
├── configs/                    # YAML configurations
│   ├── default.yaml
│   ├── datasets/zenodo77.yaml
│   ├── models/sra.yaml, cnn.yaml
│   └── hardware/ti_mmwave.yaml, infineon.yaml, generic_iq.yaml
├── data/                       # Raw, processed, and cached data
├── models/                     # Saved model checkpoints
├── notebooks/                  # Jupyter notebooks
│   ├── 01_dataset_exploration.ipynb
│   ├── 02_micro_doppler_visualization.ipynb
│   ├── 03_sra_reproduction.ipynb
│   └── 04_hardware_alignment.ipynb
├── reports/                    # Generated reports and figures
├── scripts/                    # CLI entry points
│   └── download_zenodo.py, train_sra.py, evaluate.py, ...
├── src/radar_drone_vision/     # Main Python package
│   ├── signal/                 # Signal processing (FFT, spectrogram, complex-log)
│   ├── datasets/               # Dataset loaders, synthetic generator, manifest
│   ├── classical/              # SRA, PCA, Mahalanobis
│   ├── torch_models/           # PyTorch CNN, CRNN, Transformer
│   ├── eval/                   # Metrics, EER, DET, confusion
│   ├── viz/                    # Plotting utilities
│   ├── hardware/               # Radar device interfaces
│   ├── api/                    # FastAPI backend
│   └── utils/                  # Config, logging, I/O
├── tests/                      # pytest test suite
├── web/                        # React/Vite frontend
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
└── requirements.txt
```

---

## How to Extend with Real Radar Hardware

1. **Define the data format**: Determine whether your sensor outputs raw ADC, I/Q samples, range-Doppler maps, or point clouds.

2. **Create a device driver**: Implement a subclass of `RadarDevice` in `src/radar_drone_vision/hardware/`. At minimum, provide `connect()`, `read_frame()`, and `disconnect()`.

3. **Add a hardware config**: Create a YAML file in `configs/hardware/` specifying carrier frequency, sample rate, frame size, and any sensor-specific parameters.

4. **Validate with the simulator first**: Use `scripts/live_capture.py --device simulator` to verify the processing pipeline end-to-end before connecting real hardware.

5. **Run hardware alignment**: Use `notebooks/04_hardware_alignment.ipynb` or the Hardware Alignment web page to monitor timestamp drift, frame drops, inference latency, and classification confidence in real time.

6. **Retrain if needed**: If the radar parameters differ significantly from the training data (different frequency band, waveform, or target set), retrain the SRA or CNN model on data collected from the new sensor.

---

## License

MIT

## References

- *Regularized 2-D Complex-Log Spectral Analysis and Subspace Reliability Analysis of Micro-Doppler Signature for UAV Detection*, Pattern Recognition.
- Zenodo 77 GHz FMCW dataset: [DOI 10.5281/zenodo.5845259](https://doi.org/10.5281/zenodo.5845259)
