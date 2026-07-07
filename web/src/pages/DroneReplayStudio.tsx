import { useState, useCallback, useRef } from 'react';

const API = '/radar-viz/api/drone-show';

interface Anomaly { drone_id: string; time: number; type: string; severity: string; description: string; }
interface FailureResult {
  scenario: { scenario_id: string; failure_type: string; target_drone: string; start_time: number; visual_effect: { drone_color: string; color_rgb: number[] } };
  replacement: { replacement_planned: boolean; replacement_drone?: string; transit_distance?: number; estimated_transit_time?: number };
}

const FAILURE_TYPES = [
  { value: 'GPS_DRIFT', label: 'GPS 漂移', color: '#fbbf24' },
  { value: 'IMU_ANOMALY', label: 'IMU 異常', color: '#f97316' },
  { value: 'LOW_BATTERY', label: '電池不足', color: '#9ca3af' },
  { value: 'LED_BLACKOUT', label: 'LED 熄滅', color: '#1e3a5f' },
  { value: 'COMM_LOST', label: '通訊失聯', color: '#ef4444' },
  { value: 'DRONE_MISSING', label: '節點遺失', color: '#7f1d1d' },
];

export default function DroneReplayStudio() {
  const [logId, setLogId] = useState<string | null>(null);
  const [droneCount, setDroneCount] = useState(0);
  const [totalFrames, setTotalFrames] = useState(0);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [failureResult, setFailureResult] = useState<FailureResult | null>(null);
  const [failType, setFailType] = useState('LOW_BATTERY');
  const [failDrone, setFailDrone] = useState('D0010');
  const [failTime, setFailTime] = useState(10);
  const [loading, setLoading] = useState('');
  const [planId, setPlanId] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUploadLog = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading('uploading');
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch(`${API}/replay/upload-log`, { method: 'POST', body: form });
      const d = await res.json();
      setLogId(d.log_id);
      setDroneCount(d.drone_count);
      setTotalFrames(d.total_frames);
      setAnomalies(d.anomalies_preview || []);
      setFailureResult(null);
    } catch (err) { console.error(err); }
    setLoading('');
  }, []);

  const handleFromPlan = useCallback(async () => {
    if (!planId) return;
    setLoading('reconstructing');
    try {
      const res = await fetch(`${API}/replay/from-plan/${planId}`, { method: 'POST' });
      const d = await res.json();
      setLogId(d.log_id);
      setDroneCount(d.drone_count);
      setTotalFrames(d.total_frames);
      setAnomalies([]);
      setFailureResult(null);
    } catch (err) { console.error(err); }
    setLoading('');
  }, [planId]);

  const handleSimulateFailure = useCallback(async () => {
    if (!logId) return;
    setLoading('simulating');
    try {
      const res = await fetch(`${API}/replay/simulate-failure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          log_id: logId, drone_id: failDrone,
          failure_type: failType, start_time: failTime,
          candidate_pool: ['D0045', 'D0046', 'D0047', 'D0048'],
        }),
      });
      const d = await res.json();
      setFailureResult(d);
    } catch (err) { console.error(err); }
    setLoading('');
  }, [logId, failDrone, failType, failTime]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-wide">REPLAY STUDIO</h2>
        <p className="text-sm text-slate-500 mt-1">
          SIMULATION ONLY — 飛行紀錄重建與失效節點模擬
        </p>
      </div>

      {/* Input section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="card-header">上傳飛行紀錄</h3>
          <input ref={fileRef} type="file" accept=".csv,.json" onChange={handleUploadLog} className="hidden" />
          <button onClick={() => fileRef.current?.click()}
            className="w-full py-6 border-2 border-dashed border-slate-700 rounded-lg text-slate-400 hover:border-cyan-600 hover:text-cyan-400 transition-all text-sm"
            disabled={loading === 'uploading'}>
            {loading === 'uploading' ? 'Parsing...' : 'Upload CSV / JSON Flight Log'}
          </button>
          <p className="text-[9px] text-slate-600 mt-2">Read-only parser. No mission upload capability.</p>
        </div>

        <div className="card">
          <h3 className="card-header">從 Timeline Plan 重建</h3>
          <div className="flex gap-2">
            <input type="text" value={planId} onChange={e => setPlanId(e.target.value)}
              placeholder="plan_xxxxxxxx"
              className="flex-1 bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-cyan-500" />
            <button onClick={handleFromPlan} disabled={!planId || loading !== ''}
              className="px-4 py-2 bg-cyan-600 text-white rounded text-sm hover:bg-cyan-500 disabled:opacity-40">
              {loading === 'reconstructing' ? '...' : 'Reconstruct'}
            </button>
          </div>
        </div>
      </div>

      {/* Status */}
      {logId && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="card text-center py-3">
            <p className="text-[10px] text-slate-500">Log ID</p>
            <p className="text-sm font-mono text-cyan-400 truncate">{logId}</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-[10px] text-slate-500">Drones</p>
            <p className="text-lg font-bold text-green-400">{droneCount}</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-[10px] text-slate-500">Frames</p>
            <p className="text-lg font-bold text-blue-400">{totalFrames.toLocaleString()}</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-[10px] text-slate-500">Anomalies</p>
            <p className={`text-lg font-bold ${anomalies.length > 0 ? 'text-red-400' : 'text-green-400'}`}>
              {anomalies.length}
            </p>
          </div>
        </div>
      )}

      {/* Anomalies */}
      {anomalies.length > 0 && (
        <div className="card">
          <h3 className="card-header">Detected Anomalies</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700/50">
                  <th className="text-left py-1.5 px-2 text-slate-400">Drone</th>
                  <th className="text-left py-1.5 px-2 text-slate-400">Time</th>
                  <th className="text-left py-1.5 px-2 text-slate-400">Type</th>
                  <th className="text-left py-1.5 px-2 text-slate-400">Severity</th>
                  <th className="text-left py-1.5 px-2 text-slate-400">Description</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.map((a, i) => (
                  <tr key={i} className="border-b border-slate-800/30">
                    <td className="py-1.5 px-2 text-slate-300 font-mono">{a.drone_id}</td>
                    <td className="py-1.5 px-2 text-slate-300">{a.time.toFixed(1)}s</td>
                    <td className="py-1.5 px-2"><span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-900/30 text-amber-400 border border-amber-700/30">{a.type}</span></td>
                    <td className="py-1.5 px-2"><span className={`text-${a.severity === 'high' ? 'red' : 'amber'}-400`}>{a.severity}</span></td>
                    <td className="py-1.5 px-2 text-slate-400">{a.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Failure Simulation */}
      {logId && (
        <div className="card">
          <h3 className="card-header">Failure Simulation</h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
            <div>
              <label className="text-[10px] text-slate-500 block mb-1">Drone ID</label>
              <input type="text" value={failDrone} onChange={e => setFailDrone(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-300 font-mono" />
            </div>
            <div>
              <label className="text-[10px] text-slate-500 block mb-1">Failure Type</label>
              <select value={failType} onChange={e => setFailType(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-300">
                {FAILURE_TYPES.map(ft => <option key={ft.value} value={ft.value}>{ft.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] text-slate-500 block mb-1">Start Time (s)</label>
              <input type="number" value={failTime} onChange={e => setFailTime(Number(e.target.value))}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-300" />
            </div>
            <div className="flex items-end">
              <button onClick={handleSimulateFailure} disabled={loading === 'simulating'}
                className="w-full py-1.5 bg-red-600 text-white rounded text-sm hover:bg-red-500 disabled:opacity-40">
                {loading === 'simulating' ? 'Simulating...' : 'Inject Failure'}
              </button>
            </div>
          </div>

          {/* Failure result */}
          {failureResult && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-lg border border-red-800/30 bg-red-900/10 p-4">
                <p className="text-sm font-semibold text-red-400 mb-2">Failure Scenario</p>
                <div className="text-xs text-slate-400 space-y-1">
                  <p>Target: <span className="text-white font-mono">{failureResult.scenario.target_drone}</span></p>
                  <p>Type: <span className="text-amber-400">{failureResult.scenario.failure_type}</span></p>
                  <p>Time: <span className="text-white">{failureResult.scenario.start_time}s</span></p>
                  <p>Visual: <span style={{ color: `rgb(${failureResult.scenario.visual_effect.color_rgb.join(',')})` }}>
                    {failureResult.scenario.visual_effect.drone_color}
                  </span></p>
                </div>
              </div>
              <div className={`rounded-lg border p-4 ${failureResult.replacement.replacement_planned
                ? 'border-green-800/30 bg-green-900/10' : 'border-slate-700/30 bg-slate-800/20'}`}>
                <p className={`text-sm font-semibold mb-2 ${failureResult.replacement.replacement_planned ? 'text-green-400' : 'text-slate-400'}`}>
                  {failureResult.replacement.replacement_planned ? 'Replacement Planned' : 'No Replacement Available'}
                </p>
                {failureResult.replacement.replacement_planned && (
                  <div className="text-xs text-slate-400 space-y-1">
                    <p>Replacement: <span className="text-green-300 font-mono">{failureResult.replacement.replacement_drone}</span></p>
                    <p>Transit: <span className="text-white">{failureResult.replacement.transit_distance?.toFixed(1)}m</span></p>
                    <p>ETA: <span className="text-white">{failureResult.replacement.estimated_transit_time?.toFixed(1)}s</span></p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="text-[10px] text-slate-600 text-center font-mono">
        SIMULATION_ONLY — All outputs are animation data. No real flight control.
      </div>
    </div>
  );
}
