import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getHardwareStatus,
  getHardwareFrame,
  connectHardware,
  disconnectHardware,
  type HardwareStatus,
  type HardwareFrame,
} from '../api';
import SpectrogramPanel from '../components/SpectrogramPanel';

export default function HardwareAlignment() {
  const queryClient = useQueryClient();
  const [deviceType, setDeviceType] = useState('simulator');

  const { data: status } = useQuery<HardwareStatus>({
    queryKey: ['hardwareStatus'],
    queryFn: getHardwareStatus,
    refetchInterval: 3000,
  });

  const { data: frame } = useQuery<HardwareFrame | null>({
    queryKey: ['hardwareFrame'],
    queryFn: getHardwareFrame,
    refetchInterval: status?.connected ? 1000 : false,
    enabled: status?.connected ?? false,
  });

  const connectMut = useMutation({
    mutationFn: () => connectHardware(deviceType),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hardwareStatus'] }),
  });

  const disconnectMut = useMutation({
    mutationFn: disconnectHardware,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hardwareStatus'] }),
  });

  const connected = status?.connected ?? false;
  const prediction = frame?.prediction;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-wide">HARDWARE ALIGNMENT</h2>
        <p className="text-sm text-slate-500 mt-1">
          Live radar sensor connection, frame preview, and inference validation
        </p>
      </div>

      {/* Connection controls */}
      <div className="card">
        <h3 className="card-header">Device Connection</h3>
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span
              className={`w-3 h-3 rounded-full ${
                connected ? 'bg-green-500 animate-pulse-green' : 'bg-slate-600'
              }`}
            />
            <span className={`text-sm font-medium ${connected ? 'text-green-400' : 'text-slate-400'}`}>
              {connected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>

          <select
            value={deviceType}
            onChange={(e) => setDeviceType(e.target.value)}
            disabled={connected}
            className="bg-slate-800 border border-slate-700 rounded-md text-sm text-slate-300 px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-green-500 disabled:opacity-50"
          >
            <option value="simulator">Simulator</option>
            <option value="ti_mmwave">TI mmWave</option>
            <option value="infineon">Infineon Radar</option>
            <option value="generic_iq">Generic I/Q Stream</option>
          </select>

          {!connected ? (
            <button
              className="btn-primary"
              onClick={() => connectMut.mutate()}
              disabled={connectMut.isPending}
            >
              {connectMut.isPending ? 'Connecting...' : 'Connect'}
            </button>
          ) : (
            <button
              className="btn-danger"
              onClick={() => disconnectMut.mutate()}
              disabled={disconnectMut.isPending}
            >
              {disconnectMut.isPending ? 'Disconnecting...' : 'Disconnect'}
            </button>
          )}

          {connectMut.isError && (
            <span className="text-xs text-red-400 font-mono">Connection failed</span>
          )}
        </div>

        {connected && status && (
          <div className="mt-4 pt-3 border-t border-slate-800/50">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-slate-500 text-xs block">Device Type</span>
                <span className="font-mono text-slate-300">{status.device_type}</span>
              </div>
              <div>
                <span className="text-slate-500 text-xs block">Frame Rate</span>
                <span className="font-mono text-green-400">{status.frame_rate.toFixed(1)} fps</span>
              </div>
              <div>
                <span className="text-slate-500 text-xs block">Device Info</span>
                <span className="font-mono text-slate-400 text-xs">
                  {Object.entries(status.device_info || {})
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(', ') || '--'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 text-xs block">Last Frame</span>
                <span className="font-mono text-slate-400 text-xs">
                  {status.last_frame_time ?? '--'}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Live frame preview */}
        <div className="card">
          <h3 className="card-header">Live Sensor Frame</h3>
          {connected && frame?.spectrogram_b64 ? (
            <SpectrogramPanel imageData={frame.spectrogram_b64} title="Live Micro-Doppler" />
          ) : (
            <div className="h-64 flex items-center justify-center border border-dashed border-slate-700 rounded-lg">
              <div className="text-center">
                <svg className="w-10 h-10 text-slate-600 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.288 15.038a5.25 5.25 0 017.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12.53 18.22l-.53.53-.53-.53a.75.75 0 011.06 0z" />
                </svg>
                <p className="text-sm text-slate-500">
                  {connected ? 'Waiting for frames...' : 'Connect a device to see live data'}
                </p>
              </div>
            </div>
          )}
          {frame && (
            <div className="mt-3 flex items-center gap-4 text-xs text-slate-500 font-mono">
              <span>Frame #{frame.frame_id}</span>
              <span>Shape: {frame.data_shape?.join('x') ?? '--'}</span>
              <span>{frame.timestamp}</span>
            </div>
          )}
        </div>

        {/* Prediction result */}
        <div className="card">
          <h3 className="card-header">Live Prediction</h3>
          {connected && prediction ? (
            <div className="space-y-4">
              <div className="text-center py-4">
                <p
                  className={`text-4xl font-bold font-mono ${
                    prediction.prediction.toLowerCase().includes('uav') ||
                    prediction.prediction.toLowerCase().includes('drone')
                      ? 'text-red-400'
                      : 'text-blue-400'
                  }`}
                >
                  {prediction.prediction.toUpperCase()}
                </p>
                <p className="text-sm text-slate-400 mt-2">
                  Confidence:{' '}
                  <span className="text-green-400 font-mono">
                    {(prediction.confidence * 100).toFixed(1)}%
                  </span>
                </p>
              </div>

              {/* Score bars */}
              <div className="space-y-2">
                {Object.entries(prediction.scores || {}).map(([cls, score]) => {
                  const pct = (score as number) * 100;
                  const isUAV = cls.toLowerCase().includes('uav') || cls.toLowerCase().includes('drone');
                  return (
                    <div key={cls}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-slate-400">{cls}</span>
                        <span className="font-mono text-slate-300">{pct.toFixed(1)}%</span>
                      </div>
                      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${isUAV ? 'bg-red-500' : 'bg-blue-500'}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="pt-3 border-t border-slate-800/50 space-y-1 text-xs text-slate-500">
                <div className="flex justify-between">
                  <span>Latency</span>
                  <span className="font-mono text-slate-300">{prediction.latency_ms.toFixed(1)} ms</span>
                </div>
                <div className="flex justify-between">
                  <span>Method</span>
                  <span className="font-mono text-slate-300">{prediction.method}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
              {connected ? 'Waiting for prediction...' : 'No device connected'}
            </div>
          )}
        </div>
      </div>

      {/* Hardware telemetry */}
      <div className="card">
        <h3 className="card-header">Telemetry</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <p className="stat-label">Latency</p>
            <p className="stat-value text-white">
              {prediction?.latency_ms != null ? `${prediction.latency_ms.toFixed(1)}` : '--'}
              <span className="text-sm text-slate-500 ml-1">ms</span>
            </p>
          </div>
          <div>
            <p className="stat-label">Dropped Frames</p>
            <p className={`stat-value ${(status?.dropped_frames ?? 0) > 0 ? 'text-red-400' : 'text-green-400'}`}>
              {status?.dropped_frames ?? 0}
            </p>
          </div>
          <div>
            <p className="stat-label">Timestamp Drift</p>
            <p className={`stat-value ${Math.abs(status?.timestamp_drift_ms ?? 0) > 10 ? 'text-amber-400' : 'text-green-400'}`}>
              {status?.timestamp_drift_ms != null ? `${status.timestamp_drift_ms.toFixed(1)}` : '--'}
              <span className="text-sm text-slate-500 ml-1">ms</span>
            </p>
          </div>
          <div>
            <p className="stat-label">Frame Rate</p>
            <p className="stat-value text-cyan-400">
              {status?.frame_rate != null ? status.frame_rate.toFixed(1) : '--'}
              <span className="text-sm text-slate-500 ml-1">fps</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
