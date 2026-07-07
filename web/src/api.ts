import axios from 'axios';

const client = axios.create({
  baseURL: '/radar-viz/api',
  timeout: 30000,
});

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DatasetStatus {
  name: string;
  downloaded: boolean;
  sample_count: number;
  class_distribution: Record<string, number>;
  path: string;
  size_mb: number;
}

export interface Sample {
  sample_id: string;
  label: string;
  label_binary: number;
  radar_type: string;
  carrier_frequency_hz: number;
  raw_shape: number[];
  metadata: Record<string, unknown>;
}

export interface SampleList {
  samples: Sample[];
  total: number;
  page: number;
  page_size: number;
}

export interface MetricsSummary {
  method: string;
  dataset: string;
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  auc: number;
  eer: number;
  eer_threshold: number;
  far_at_frr_1: number;
  confusion_matrix: number[][];
  class_names: string[];
  roc_curve: { fpr: number[]; tpr: number[]; thresholds: number[] };
  det_curve: { fpr: number[]; fnr: number[]; thresholds: number[] };
  timestamp: string;
}

export interface InferenceResult {
  sample_id: string;
  prediction: string;
  confidence: number;
  scores: Record<string, number>;
  method: string;
  latency_ms: number;
}

export interface HardwareStatus {
  connected: boolean;
  device_type: string;
  device_info: Record<string, unknown>;
  frame_rate: number;
  dropped_frames: number;
  timestamp_drift_ms: number;
  last_frame_time: string | null;
}

export interface HardwareFrame {
  frame_id: number;
  timestamp: string;
  data_shape: number[];
  spectrogram_b64: string | null;
  prediction: InferenceResult | null;
}

export interface MethodComparison {
  method: string;
  feature: string;
  classifier: string;
  dataset: string;
  eer: number;
  far_at_frr_1: number;
  notes: string;
}

export interface AirspaceTarget {
  track_id: string;
  x: number;
  y: number;
  range_m: number;
  azimuth_deg: number;
  velocity_mps: number;
  heading_deg?: number;
  classification: string;
  confidence: number;
  rcs_dbsm: number | null;
  trail?: { range_m: number; azimuth_deg: number }[];
  micro_doppler_hz?: number;
  flock_id?: string | null;
  label?: string;
  altitude_m?: number;
  elevation_deg?: number;
  timestamp: string;
}

export interface FeatureDimResult {
  dimension: number;
  eer: number;
  far_at_frr_1: number;
}

// ─── Dataset API ─────────────────────────────────────────────────────────────

export async function getDatasets(): Promise<DatasetStatus[]> {
  const { data } = await client.get('/datasets');
  // Map backend field names to frontend interface
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return data.map((d: any) => ({
    name: d.name ?? '',
    downloaded: Number(d.num_samples ?? d.sample_count ?? 0) > 0,
    sample_count: Number(d.num_samples ?? d.sample_count ?? 0),
    class_distribution: d.classes ?? d.class_distribution ?? {},
    path: d.path ?? '',
    size_mb: d.size_mb ?? 0,
  }));
}

export async function getSamples(
  dataset: string = 'zenodo_77ghz',
  page: number = 1,
  pageSize: number = 20,
  label?: string
): Promise<SampleList> {
  const params: Record<string, unknown> = { dataset, page, page_size: pageSize };
  if (label) params.label = label;
  const { data } = await client.get('/samples', { params });
  return data;
}

export async function getSample(sampleId: string): Promise<Sample> {
  const { data } = await client.get(`/samples/${sampleId}`);
  return data;
}

export async function getSampleSpectrogram(sampleId: string): Promise<string> {
  const { data } = await client.get(`/samples/${sampleId}/spectrogram`);
  // Backend returns JSON with a "data" field containing base64
  if (typeof data === 'object' && data.data) {
    return `data:image/png;base64,${data.data}`;
  }
  return data; // fallback: raw string
}

export async function getSampleRangeDoppler(sampleId: string): Promise<string> {
  const { data } = await client.get(`/samples/${sampleId}/range_doppler`, {
    responseType: 'text',
  });
  return data;
}

export async function prepareDataset(dataset: string = 'zenodo_77ghz'): Promise<{ task_id: string }> {
  const { data } = await client.post('/datasets/prepare', { dataset });
  return data;
}

// ─── Inference API ───────────────────────────────────────────────────────────

export async function runInference(
  sampleId: string,
  method: string = 'sra'
): Promise<InferenceResult> {
  const { data } = await client.post('/inference', { sample_id: sampleId, method });
  return data;
}

export async function getLatestInference(): Promise<InferenceResult | null> {
  try {
    const { data } = await client.get('/inference/latest');
    return data;
  } catch {
    return null;
  }
}

// ─── Evaluation / Reports ────────────────────────────────────────────────────

export async function getMetrics(method?: string): Promise<MetricsSummary | null> {
  try {
    const params = method ? { method } : {};
    const { data } = await client.get('/reports/metrics', { params });
    return data;
  } catch {
    return null;
  }
}

export async function getMethodComparison(): Promise<MethodComparison[]> {
  try {
    const { data } = await client.get('/reports/comparison');
    return data;
  } catch {
    return [];
  }
}

export async function getFeatureDimSweep(): Promise<FeatureDimResult[]> {
  try {
    const { data } = await client.get('/reports/feature_dim_sweep');
    return data;
  } catch {
    return [];
  }
}

export async function triggerEvaluation(method: string = 'sra'): Promise<{ task_id: string }> {
  const { data } = await client.post('/reports/evaluate', { method });
  return data;
}

export async function triggerTraining(method: string = 'sra'): Promise<{ task_id: string }> {
  const { data } = await client.post('/training/start', { method });
  return data;
}

// ─── Airspace ────────────────────────────────────────────────────────────────

export async function getAirspaceTargets(): Promise<AirspaceTarget[]> {
  try {
    const { data } = await client.get('/airspace/targets');
    return data;
  } catch {
    return [];
  }
}

// ─── Live Replay (real inference) ────────────────────────────────────────────

export interface LiveReplaySample {
  sample_index: number;
  sample_id: string;
  true_label: string;
  true_is_uav: boolean;
  predicted: string;
  predicted_correct: boolean;
  confidence: number;
  sra_ratio: number;
  range_m: number;
  time_s: number;
  spectrogram_b64: string;
  timestamp: string;
}

export interface LiveReplayResponse {
  samples: LiveReplaySample[];
  stats: { total: number; correct: number; accuracy: number; cursor: number; dataset_size: number };
}

export async function getLiveReplay(count: number = 6): Promise<LiveReplayResponse | null> {
  try {
    const { data } = await client.get('/airspace/live-replay', { params: { count } });
    return data;
  } catch {
    return null;
  }
}

export async function getLiveStats(): Promise<{ total: number; correct: number; accuracy: number } | null> {
  try {
    const { data } = await client.get('/airspace/live-stats');
    return data;
  } catch {
    return null;
  }
}

// ─── UAV Flight Mode ─────────────────────────────────────────────────────────

export type UavFlightMode = 'outbound' | 'inbound' | 'swarm' | 'orbit' | 'hover' | 'transit';

export async function setUavMode(mode: UavFlightMode): Promise<{ mode: string }> {
  const { data } = await client.post('/airspace/uav-mode', { mode });
  return data;
}

export async function getUavMode(): Promise<{ mode: string }> {
  const { data } = await client.get('/airspace/uav-mode');
  return data;
}

// ─── Hardware ────────────────────────────────────────────────────────────────

export async function getHardwareStatus(): Promise<HardwareStatus> {
  const { data } = await client.get('/hardware/status');
  return data;
}

export async function connectHardware(
  deviceType: string = 'simulator'
): Promise<{ success: boolean; message: string }> {
  const { data } = await client.post('/hardware/connect', { device_type: deviceType });
  return data;
}

export async function disconnectHardware(): Promise<{ success: boolean }> {
  const { data } = await client.post('/hardware/disconnect');
  return data;
}

export async function getHardwareFrame(): Promise<HardwareFrame | null> {
  try {
    const { data } = await client.get('/hardware/frame');
    return data;
  } catch {
    return null;
  }
}
