# radar-drone-vision：雷達 Micro-Doppler UAV / Bird 辨識與硬體驗證平台實作指示

> 給 Claude Code：請依照本檔案一次性建立完整 Python / PyTorch / Docker 專案。此專案目標不是單純做學術 Demo，而是把 Pattern Recognition 論文「Regularized 2-D Complex-Log Spectral Analysis and Subspace Reliability Analysis of Micro-Doppler Signature for UAV Detection」工程化，先用公開資料集反覆驗證，再保留硬體接入介面，後續可接 77GHz FMCW 雷達、X-band CW 雷達或其他雷達前端。

---

## 0. 專案定位

專案目錄名稱：

```bash
radar-drone-vision
```

產品定位：

```text
Low-altitude radar AI validation platform for UAV / bird discrimination
```

中文定位：

```text
低空小目標雷達 AI 驗證平台：以 micro-Doppler 訊號辨識無人機與鳥類，並提供空域視覺化、硬體接入、資料集管理與演算法評估。
```

核心目的：

1. 重現論文的傳統機器學習演算法：
   - 2-D regularized complex-log-Fourier transform
   - Subspace Reliability Analysis, SRA
   - Minimum Mahalanobis-distance / ratio decision classifier
2. 加上可比較的 baseline：
   - Spectrogram + PCA + Mahalanobis
   - Cepstrogram + PCA + Mahalanobis
   - Cadence Velocity Diagram, CVD + PCA + Mahalanobis
   - Proposed Feature + PCA
   - Proposed Feature + SRA
3. 加上 PyTorch 版本：
   - Spectrogram CNN
   - Proposed Feature CNN
   - Range-Doppler / micro-Doppler tensor CNN
   - 可選 Transformer / CRNN
4. 必須支援公開資料集反覆測試。
5. 必須支援未來硬體接入：
   - TI mmWave raw ADC / point cloud
   - Infineon radar raw / SDK output
   - generic I/Q stream
   - generic range-Doppler tensor
6. 必須可以畫出空域對應圖：
   - range-Doppler map
   - range-azimuth map
   - Doppler-time spectrogram
   - micro-Doppler signature
   - target track plot
   - 2D top-view radar sector
   - 若有 elevation 或多感測器資料，擴充為 3D airspace plot
7. 必須輸出正確性評估：
   - Confusion matrix
   - ROC curve
   - DET curve
   - EER
   - FAR at FRR=1%
   - Precision / Recall / F1
   - Threshold sweep
   - Eigen-spectrum reliability plot
   - Feature dimension vs error-rate plot
   - Dataset report
   - Hardware alignment report

---

## 1. 論文演算法摘要

論文要解決的是 UAV 和 bird 都是小型、慢速、低 RCS 目標，單靠運動速度與雷達截面積不容易分辨，因此改用 micro-Doppler signature。UAV 的旋翼旋轉與鳥類翅膀拍動都會產生 micro-Doppler，但兩者在頻譜的細節、週期、相位與穩定性不同。

論文兩個核心貢獻：

### 1.1 2-D Regularized Complex-Log-Fourier Transform

傳統 spectrogram 只使用第一段 FFT 的 magnitude，丟掉 phase。論文認為 phase 也可能帶有判別資訊，所以應保留。

原始訊號：

```text
s(t)
```

切成 M 個 overlapping frames：

```text
X = [x0, x1, ..., xM-1]
```

每個 frame 長度 N。

第一段 FFT：

```text
fi = F{xi}
fi = mi * exp(jθi)
```

傳統 spectrogram：

```text
S = |F{X}|^2
```

論文的 complex-log：

```text
log{fi} = log{mi} + j*w*θi
```

其中：

```text
w = 1 / π
```

為了抑制 log 後放大的噪聲，加入 median noise floor regularization：

```text
Ci = median(mi)
regularized_log{fi} = log(mi + Ci) + j*w*θi
```

接著沿 time axis 做第二段 FFT：

```text
F2{X} = Ft{ regularized_log{F{X}} }
```

最後把 complex matrix 轉成 feature vector。工程實作時必須提供以下選項：

```text
feature_mode:
  - real_imag_concat
  - magnitude_only
  - magnitude_phase_concat
  - complex_abs
```

預設使用：

```text
real_imag_concat
```

因為可以完整保留 complex transform 後的資訊。

### 1.2 Subspace Reliability Analysis, SRA

傳統 PCA 在單一 subspace 中移除小 eigenvalue 對應的不可靠維度，但 UAV 和 non-UAV 的 covariance matrix 可能在不同方向不可靠。因此論文主張分別為兩類建立不同 subspace。

兩類：

```text
class 1 = UAV
class 2 = non-UAV, mainly bird
```

計算：

```text
μ1, Σ1
μ2, Σ2
Σb = between-class covariance
S1 = Σ1 + Σb
S2 = Σ2 + Σb
```

分別 eigen decomposition：

```text
S1 = Φ1 Λ1 Φ1^T
S2 = Φ2 Λ2 Φ2^T
```

取 leading eigenvectors：

```text
Φ1,m1
Φ2,m2
```

論文最佳維度：

```text
m1 = 10 for UAV
m2 = 100 for non-UAV
```

在兩個 subspace 中分別計算 Mahalanobis distance：

```text
g1,m1(h) = (h - μ1)^T Φ1,m1 (Φ1,m1^T Σ1 Φ1,m1)^-1 Φ1,m1^T (h - μ1)

g2,m2(h) = (h - μ2)^T Φ2,m2 (Φ2,m2^T Σ2 Φ2,m2)^-1 Φ2,m2^T (h - μ2)
```

融合 ratio：

```text
g(h) = g1,m1(h) / g2,m2(h)
```

決策：

```text
if g(h) < threshold:
    UAV
else:
    non-UAV
```

---

## 2. 資料集策略

### 2.1 必須支援的公開資料集

第一個公開資料集：

```text
Zenodo: Radar measurements on drones, birds and humans with a 77GHz FMCW sensor
DOI: 10.5281/zenodo.5845259
File: data_SAAB_SIRS_77GHz_FMCW.npy
ReadMe: ReadMe.txt
Size: about 1.6 GB
Classes: birds, humans, six different drones
Samples: 75868
Sensor: 77 GHz FMCW radar with mechanically scanning antenna
```

此資料集與論文原始 Thales X-band CW dataset 不同，所以不可假裝可以完全重現論文數字。系統要明確標示：

```text
Paper reproduction mode: approximate / algorithm reproduction
Public dataset validation mode: Zenodo 77GHz FMCW validation
Hardware validation mode: real sensor alignment
```

### 2.2 資料集下載器

建立：

```text
scripts/download_zenodo.py
```

功能：

1. 下載 ReadMe.txt。
2. 下載 data_SAAB_SIRS_77GHz_FMCW.npy。
3. 支援 resume。
4. 檢查 md5。
5. 下載完成後建立 dataset manifest。

指令：

```bash
python scripts/download_zenodo.py --out data/raw/zenodo_77ghz
```

### 2.3 資料集解析器

建立：

```text
src/radar_drone_vision/datasets/zenodo77.py
```

功能：

1. 讀取 `.npy`。
2. 讀取 ReadMe metadata。
3. 自動推斷 class label。
4. 支援 sample index 查詢。
5. 支援轉成統一格式：

```python
RadarSample(
    sample_id: str,
    signal: np.ndarray,
    label: str,
    label_binary: int,
    radar_type: str,
    carrier_frequency_hz: float,
    raw_shape: tuple,
    metadata: dict
)
```

### 2.4 統一資料格式

所有資料進入系統後都轉成：

```text
data/processed/{dataset_name}/samples/*.npz
data/processed/{dataset_name}/manifest.parquet
```

每個 npz 至少包含：

```text
iq: complex64 array, optional
adc: float32/complex64 array, optional
range_doppler: float32/complex64 array, optional
micro_doppler: float32 array, optional
label: int
label_name: str
timestamp: optional
range_m: optional
azimuth_deg: optional
elevation_deg: optional
velocity_mps: optional
track_id: optional
```

若資料集沒有 range / azimuth / elevation，空域圖要用 sample index / pseudo range / available sweep index 做替代視覺化，但 UI 必須標示「dataset does not provide full spatial coordinates」。

---

## 3. 專案結構

請建立以下目錄：

```text
radar-drone-vision/
  README.md
  docker-compose.yml
  Dockerfile
  pyproject.toml
  requirements.txt
  .env.example
  Makefile

  configs/
    default.yaml
    datasets/zenodo77.yaml
    models/sra.yaml
    models/cnn.yaml
    hardware/ti_mmwave.yaml
    hardware/infineon.yaml
    hardware/generic_iq.yaml

  data/
    raw/
    processed/
    external/
    reports/
    cache/

  notebooks/
    01_dataset_exploration.ipynb
    02_micro_doppler_visualization.ipynb
    03_sra_reproduction.ipynb
    04_hardware_alignment.ipynb

  scripts/
    download_zenodo.py
    prepare_dataset.py
    train_sra.py
    train_cnn.py
    evaluate.py
    live_capture.py
    render_airspace.py
    export_report.py

  src/
    radar_drone_vision/
      __init__.py

      datasets/
        __init__.py
        base.py
        zenodo77.py
        synthetic.py
        manifest.py

      signal/
        __init__.py
        framing.py
        fft.py
        spectrogram.py
        cepstrogram.py
        cvd.py
        complex_log_fft.py
        clutter_removal.py
        normalization.py

      features/
        __init__.py
        extractors.py
        vectorize.py
        feature_store.py

      classical/
        __init__.py
        pca.py
        sra.py
        mahalanobis.py
        thresholds.py

      torch_models/
        __init__.py
        datasets.py
        cnn.py
        crnn.py
        transformer.py
        trainer.py

      eval/
        __init__.py
        metrics.py
        eer.py
        det_curve.py
        confusion.py
        reliability.py
        benchmark.py

      viz/
        __init__.py
        spectrogram_plot.py
        range_doppler_plot.py
        airspace_plot.py
        eigen_plot.py
        roc_det_plot.py
        dashboard_assets.py

      hardware/
        __init__.py
        base.py
        generic_iq.py
        ti_mmwave.py
        infineon.py
        simulator.py
        timestamp_sync.py

      api/
        __init__.py
        main.py
        schemas.py
        routes_dataset.py
        routes_inference.py
        routes_hardware.py
        routes_reports.py

      utils/
        __init__.py
        config.py
        logging.py
        seed.py
        io.py
        math.py

  tests/
    test_complex_log_fft.py
    test_sra.py
    test_metrics.py
    test_dataset_loader.py
    test_hardware_simulator.py

  web/
    package.json
    src/
      App.tsx
      pages/
        Dashboard.tsx
        DatasetExplorer.tsx
        AirspaceView.tsx
        ModelEvaluation.tsx
        HardwareAlignment.tsx
      components/
        SpectrogramPanel.tsx
        RangeDopplerPanel.tsx
        AirspaceCanvas.tsx
        ConfusionMatrix.tsx
        RocDetChart.tsx
```

---

## 4. Docker 要求

Docker 必須提供三個服務：

```yaml
services:
  api:
    FastAPI backend
  web:
    React/Vite frontend
  worker:
    training/evaluation worker
```

可以加上：

```yaml
  mlflow:
    experiment tracking
  postgres:
    metadata
```

基本啟動：

```bash
docker compose up --build
```

API：

```text
http://localhost:8000
```

Web：

```text
http://localhost:5173
```

MLflow：

```text
http://localhost:5000
```

---

## 5. 訊號處理實作要求

### 5.1 Framing

檔案：

```text
src/radar_drone_vision/signal/framing.py
```

函式：

```python
frame_signal(signal, frame_size=256, hop_size=128, window="hann")
```

需求：

1. 預設 256 points。
2. 預設 50% overlap。
3. 支援 real / complex signal。
4. 輸出 shape：

```text
num_frames x frame_size
```

論文設定：

```text
sampling_rate = 96000
frame_size = 256
overlap = 50%
sample_duration = 50 ms
feature_dim_after_filter = 201 x 36 = 7236
```

注意：公開 Zenodo 77GHz FMCW 資料與論文原始 X-band CW 不同，必須透過 config 分別調參。

### 5.2 Spectrogram

```python
compute_spectrogram(frames, n_fft=256, power=True)
```

輸出：

```text
M x N_freq
```

### 5.3 Cepstrogram

```python
compute_cepstrogram(frames, n_fft=256)
```

步驟：

```text
FFT -> |FFT|^2 -> log -> IFFT -> |IFFT|^2
```

### 5.4 CVD

```python
compute_cvd(spectrogram)
```

步驟：

```text
FFT along time axis
```

### 5.5 Proposed Regularized Complex-Log-Fourier Transform

檔案：

```text
src/radar_drone_vision/signal/complex_log_fft.py
```

核心函式：

```python
def regularized_complex_log_fft(
    frames: np.ndarray,
    n_fft: int = 256,
    phase_weight: float = 1 / np.pi,
    regularizer: str = "median",
    second_fft_axis: int = 0,
    eps: float = 1e-8,
) -> np.ndarray:
    """
    Implements:
      fi = FFT(xi)
      mi = abs(fi)
      theta_i = angle(fi)
      Ci = median(mi)
      z_i = log(mi + Ci + eps) + 1j * phase_weight * theta_i
      F2 = FFT(z, axis=time_axis)
    """
```

注意：

1. `Ci` 應該可以 per-frame median，也可以 global median；預設 per-frame median。
2. 需保留 phase。
3. 需避免 log(0)。
4. 需提供 ablation：
   - no_regularization
   - median_regularization
   - mean_regularization
   - percentile_regularization
   - magnitude_only
   - phase_weight sweep

### 5.6 Clutter removal

建立：

```text
src/radar_drone_vision/signal/clutter_removal.py
```

功能：

1. 移除 DC / main body Doppler 可設定。
2. 支援 frequency bin mask。
3. 支援 high-frequency unreliable bins removal。
4. 支援 config：

```yaml
clutter:
  remove_dc: true
  dc_bins: 3
  keep_bins: [start, end]
  normalize_each_sample: true
```

---

## 6. Classical ML：PCA / SRA / Mahalanobis

### 6.1 PCA baseline

```text
src/radar_drone_vision/classical/pca.py
```

功能：

```python
fit_pca(X_train, n_components)
transform_pca(X, model)
```

### 6.2 SRA

```text
src/radar_drone_vision/classical/sra.py
```

Class：

```python
class SubspaceReliabilityAnalysis:
    def __init__(self, m_uav=10, m_non_uav=100, ridge=1e-5):
        ...

    def fit(self, X, y):
        """
        y=1 UAV
        y=0 non-UAV
        compute μ1, μ2, Σ1, Σ2, Σb
        compute S1 = Σ1 + Σb
        compute S2 = Σ2 + Σb
        eigen-decompose S1/S2
        store Φ1,m1 and Φ2,m2
        """

    def score_ratio(self, X):
        """
        return g1/g2
        lower score => more UAV-like
        """

    def predict(self, X, threshold):
        ...
```

工程細節：

1. covariance 必須加 ridge，避免 singular matrix。
2. 使用 `np.linalg.eigh`，並按 eigenvalue descending 排序。
3. Mahalanobis 子空間 inverse 使用 `np.linalg.pinv` 或 ridge inverse。
4. 支援 GPU 不必強制，SRA 用 numpy/sklearn 即可。
5. 提供 model save/load：

```text
models/sra_model.joblib
```

### 6.3 Threshold search

```text
src/radar_drone_vision/classical/thresholds.py
```

功能：

1. 依 score sweep threshold。
2. 找 EER threshold。
3. 找 FRR=1% 時的 FAR。
4. 輸出所有 threshold 對應 FAR/FRR。

---

## 7. PyTorch 模型

雖然論文是 classical ML，本專案必須加 PyTorch 模型，方便未來硬體與大量資料擴展。

### 7.1 CNN baseline

輸入：

```text
1-channel or 2-channel micro-Doppler image
```

若使用 proposed complex feature：

```text
channel 1 = real
channel 2 = imag
```

模型：

```python
SmallRadarCNN
```

需提供：

1. train loop
2. validation loop
3. early stopping
4. class imbalance weighting
5. confusion matrix
6. checkpoint
7. ONNX export

### 7.2 CRNN / Transformer optional

建立 skeleton 即可，但 CNN 必須可跑。

---

## 8. 評估指標

### 8.1 必備指標

檔案：

```text
src/radar_drone_vision/eval/metrics.py
```

輸出：

```text
accuracy
precision
recall
f1
auc
eer
far_at_frr_1
confusion_matrix
classification_report
```

### 8.2 EER

檔案：

```text
src/radar_drone_vision/eval/eer.py
```

注意：

```text
FRR = UAV 被判成 non-UAV
FAR = non-UAV 被判成 UAV
```

UAV 是 positive class。

### 8.3 論文對照表

evaluation report 要產生：

```text
reports/paper_comparison.md
```

欄位：

```text
Method
Feature
Classifier
Dataset
EER
FAR@FRR=1%
Notes
```

預設列出：

```text
DTW [paper reference target]
Robust PCA [paper reference target]
Spectrogram + PCA
CVD + PCA
Cepstrogram + PCA
Proposed Feature + PCA
Proposed Feature + SRA
CNN Proposed Feature
```

其中 paper target value 可放論文數值，但不得宣稱公開資料集會完全重現。

---

## 9. 視覺化要求

### 9.1 Micro-Doppler Spectrogram

```text
src/radar_drone_vision/viz/spectrogram_plot.py
```

輸出：

```text
reports/figures/sample_{id}_spectrogram.png
reports/figures/sample_{id}_proposed_feature_real.png
reports/figures/sample_{id}_proposed_feature_imag.png
reports/figures/sample_{id}_regularized_log.png
```

### 9.2 Range-Doppler Map

若資料有 FMCW sweep，產生：

```text
range_doppler_map
```

若資料不含完整 raw ADC，則標示 unavailable。

### 9.3 空域對應圖

建立：

```text
src/radar_drone_vision/viz/airspace_plot.py
```

支援：

1. 2D top-view radar sector：
   - radar at origin
   - range rings
   - azimuth fan
   - target dots
   - classification color
   - confidence score
2. Doppler-time waterfall：
   - time x velocity
3. Range-time plot：
   - time x range
4. Track plot：
   - track_id
   - predicted label
   - confidence over time
5. 3D airspace plot：
   - 若有 range / azimuth / elevation
   - x/y/z conversion

### 9.4 Hardware alignment visualization

建立頁面：

```text
HardwareAlignment.tsx
```

顯示：

```text
Raw sensor frame
Processed feature
Predicted class
Confidence score
Latency
Dropped frames
Timestamp drift
Range-Doppler map
Airspace map
```

---

## 10. API 需求

使用 FastAPI。

### 10.1 endpoints

```text
GET /health
GET /datasets
POST /datasets/prepare
GET /samples/{sample_id}
GET /samples/{sample_id}/spectrogram
POST /features/extract
POST /models/sra/train
POST /models/cnn/train
POST /models/evaluate
POST /inference/sample
POST /hardware/connect
POST /hardware/disconnect
GET /hardware/status
GET /hardware/live-frame
GET /reports/latest
```

---

## 11. Web UI 需求

頁面：

1. Dashboard
   - dataset status
   - latest metrics
   - latest inference
2. Dataset Explorer
   - class distribution
   - sample browser
   - spectrogram preview
3. Airspace View
   - 2D radar sector
   - track table
   - confidence
4. Model Evaluation
   - confusion matrix
   - ROC / DET
   - EER
   - FAR@FRR=1%
   - feature dimension sweep
   - eigen-spectrum plot
5. Hardware Alignment
   - live sensor status
   - timestamp sync
   - sensor frame preview
   - prediction latency

---

## 12. 硬體接入設計

### 12.1 抽象介面

```text
src/radar_drone_vision/hardware/base.py
```

```python
class RadarDevice:
    def connect(self): ...
    def disconnect(self): ...
    def read_frame(self) -> RadarFrame: ...
    def get_metadata(self) -> dict: ...
```

```python
class RadarFrame:
    timestamp_ns: int
    frame_id: int
    iq: Optional[np.ndarray]
    adc: Optional[np.ndarray]
    range_doppler: Optional[np.ndarray]
    point_cloud: Optional[np.ndarray]
    metadata: dict
```

### 12.2 generic I/Q stream

支援：

1. UDP
2. TCP
3. serial
4. file replay

### 12.3 TI mmWave skeleton

建立但不需要完全依賴 SDK：

```text
hardware/ti_mmwave.py
```

支援未來解析：

```text
raw ADC
range profile
range-Doppler heatmap
point cloud TLV
```

### 12.4 Simulator

```text
hardware/simulator.py
```

必須可以從 processed dataset replay：

```bash
python scripts/live_capture.py --device simulator --dataset zenodo77 --speed 1.0
```

---

## 13. 合成資料產生器

因為公開資料不一定完全等於硬體未來場域，建立 synthetic generator：

```text
src/radar_drone_vision/datasets/synthetic.py
```

產生：

1. UAV rotor micro-Doppler：
   - 多條穩定 harmonic / parallel lines
   - rotor rate variation
2. Bird wingbeat micro-Doppler：
   - 較不穩定 sinusoidal modulation
   - wingbeat periodicity
3. noise floor
4. clutter
5. range / velocity / azimuth metadata

目的：

1. 測試 pipeline。
2. 測試空域視覺化。
3. 測試硬體接入格式。
4. 不得把 synthetic result 當成真實效能。

---

## 14. 訓練與驗證流程

### 14.1 prepare dataset

```bash
make download
make prepare
```

### 14.2 train SRA

```bash
python scripts/train_sra.py \
  --config configs/models/sra.yaml \
  --dataset zenodo77 \
  --feature proposed_regularized_complex_log_fft \
  --repeat 20 \
  --split half
```

### 14.3 evaluate

```bash
python scripts/evaluate.py \
  --model models/sra_model.joblib \
  --dataset zenodo77 \
  --out reports/sra_eval
```

### 14.4 train CNN

```bash
python scripts/train_cnn.py \
  --config configs/models/cnn.yaml \
  --dataset zenodo77 \
  --feature proposed_complex_image \
  --epochs 50
```

### 14.5 render airspace

```bash
python scripts/render_airspace.py \
  --dataset synthetic_airspace \
  --out reports/airspace_demo
```

---

## 15. 驗收條件

Claude Code 完成後，必須達到以下條件：

1. `docker compose up --build` 可啟動。
2. `make test` 全部通過。
3. `make download` 可下載 Zenodo dataset 或至少下載 ReadMe 並提示大檔案下載方式。
4. `make prepare` 可建立 processed dataset。
5. `make train-sra` 可訓練 SRA。
6. `make eval-sra` 可輸出：
   - confusion matrix
   - ROC
   - DET
   - EER
   - FAR@FRR=1%
   - threshold table
7. `make train-cnn` 可訓練 PyTorch CNN。
8. `make airspace-demo` 可畫出 2D radar sector 與 target tracks。
9. Web UI 可查看 dataset、sample spectrogram、model metrics、airspace view。
10. Hardware simulator 可 replay dataset 並產生即時推論。

---

## 16. README 必須清楚說明

README 必須包含：

1. 專案用途。
2. 論文演算法概要。
3. 公開資料集下載方式。
4. 為什麼 Zenodo 77GHz FMCW dataset 與論文 Thales X-band CW dataset 不完全相同。
5. 如何重現 approximate algorithm validation。
6. 如何接硬體。
7. 如何解讀 EER / FAR / FRR。
8. 如何看空域圖。
9. 如何延伸到真實反無人機硬體驗證。

---

## 17. 不可偷懶事項

1. 不可以只做假資料 demo。
2. 不可以只畫漂亮圖沒有 metrics。
3. 不可以把 synthetic dataset 當成真實驗證。
4. 不可以把公開 Zenodo 77GHz 結果說成論文原始 Thales X-band 結果。
5. 不可以省略 SRA。
6. 不可以只做 CNN，而不做論文演算法。
7. 不可以只做離線，不留硬體接口。
8. 不可以只有 notebook，必須有 CLI、API、Docker、測試。
9. 不可以只有 accuracy，必須有 EER 和 FAR@FRR=1%。
10. 不可以忽略 timestamp、latency、frame drop 等硬體對齊問題。

---

## 18. 最後交付

完成後交付：

```text
radar-drone-vision/
  可執行完整專案
reports/
  dataset_report.md
  paper_comparison.md
  sra_eval_report.md
  cnn_eval_report.md
  hardware_alignment_report.md
  figures/
models/
  sra_model.joblib
  cnn_best.pt
```

並在最後輸出：

```text
1. 已完成項目
2. 尚未完成項目
3. 如何下載資料集
4. 如何訓練
5. 如何評估
6. 如何接真實雷達硬體
7. 目前結果是否能支撐硬體驗證
```
