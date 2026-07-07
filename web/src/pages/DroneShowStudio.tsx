import { useState, useRef, useCallback } from 'react';

const API_BASE = '/radar-viz/api/drone-show';

interface PointPreview {
  point_id: string;
  xyz: number[];
  rgb888: number[];
  importance: number;
}

interface PlanPreview {
  plan_id: string;
  drone_count: number;
  total_duration_sec: number;
  risk: {
    min_drone_distance: number;
    max_speed_index: number;
    warnings: string[];
  };
  drone_preview: { drone_id: string; ground: number[]; target: number[]; color: number[] }[];
}

interface SimReport {
  risk_level: string;
  inter_drone: { min_distance: number; close_approach_count: number };
  speed_summary: { max_speed: number; max_acceleration: number; total_violations: number };
  warnings: string[];
}

interface Obstacle {
  obstacle_id: string; name: string; type: string;
  center: number[]; size: number[]; z_min: number; z_max: number;
}

const OBS_PRESETS = [
  { name: '大型氣球 (左)', type: 'balloon', canvas_x: 0.2, canvas_y: 0.3, canvas_w: 0.12, canvas_h: 0.12, z_min: 40, z_max: 80, safety_buffer: 8 },
  { name: '高空建築 (右)', type: 'building', canvas_x: 0.8, canvas_y: 0.5, canvas_w: 0.08, canvas_h: 0.15, z_min: 0, z_max: 60, safety_buffer: 5 },
  { name: '舞台塔架 (中)', type: 'building', canvas_x: 0.5, canvas_y: 0.85, canvas_w: 0.06, canvas_h: 0.06, z_min: 0, z_max: 25, safety_buffer: 3 },
  { name: '禁飛區 (上方)', type: 'no_fly', canvas_x: 0.5, canvas_y: 0.1, canvas_w: 0.3, canvas_h: 0.08, z_min: 70, z_max: 120, safety_buffer: 10 },
];

export default function DroneShowStudio() {
  const [assetId, setAssetId] = useState<string | null>(null);
  const [thumbnail, setThumbnail] = useState<string | null>(null);
  const [droneCount, setDroneCount] = useState(50);
  const [customCount, setCustomCount] = useState('');
  const [points, setPoints] = useState<PointPreview[]>([]);
  const [frameId, setFrameId] = useState<string | null>(null);
  const [detailScore, setDetailScore] = useState(0);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [plan, setPlan] = useState<PlanPreview | null>(null);
  const [renderImages, setRenderImages] = useState<string[]>([]);
  const [simReport, setSimReport] = useState<SimReport | null>(null);
  const [obstacles, setObstacles] = useState<Obstacle[]>([]);
  const [loading, setLoading] = useState('');
  const [dslYaml, setDslYaml] = useState(`scene:
  title: "Demo Show"
  drones: 50
  safety_profile: "safety_first"
  frames:
    - id: "takeoff"
      type: "takeoff_blue"
      duration: 8
    - id: "logo"
      type: "image_formation"
      asset: "logo.png"
      hold: 6
      scale: 1.0
    - id: "expand"
      type: "transform"
      instruction: "放大 20%"
      duration: 5
    - id: "landing"
      type: "landing_blue"
      duration: 8`);
  const [dslResult, setDslResult] = useState<Record<string, unknown> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Upload image
  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading('uploading');
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/assets/upload`, { method: 'POST', body: form });
      const data = await res.json();
      setAssetId(data.asset_id);
      // Get thumbnail
      const thumbRes = await fetch(`${API_BASE}/assets/${data.asset_id}/thumbnail`);
      const thumbData = await thumbRes.json();
      setThumbnail(thumbData.thumbnail);
      setPoints([]);
      setFrameId(null);
      setPlan(null);
      setRenderImages([]);
    } catch (err) {
      console.error('Upload failed:', err);
    }
    setLoading('');
  }, []);

  // Generate points
  const handleGenerate = useCallback(async () => {
    if (!assetId) return;
    setLoading('generating');
    try {
      const res = await fetch(`${API_BASE}/generate-points`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_id: assetId, drone_count: droneCount }),
      });
      const data = await res.json();
      setPoints(data.points_preview || []);
      setFrameId(data.frame_id);
      setDetailScore(data.detail_score);
      setWarnings(data.warnings || []);
      setPlan(null);
      setRenderImages([]);
      // Draw points on canvas
      drawFormation(data.points_preview || []);
    } catch (err) {
      console.error('Generation failed:', err);
    }
    setLoading('');
  }, [assetId, droneCount]);

  // Create plan
  const handlePlan = useCallback(async () => {
    if (!frameId) return;
    setLoading('planning');
    try {
      const res = await fetch(`${API_BASE}/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frame_id: frameId }),
      });
      const data = await res.json();
      setPlan(data);
      setRenderImages([]);
      // Draw paths
      drawPaths(data.drone_preview || []);
    } catch (err) {
      console.error('Planning failed:', err);
    }
    setLoading('');
  }, [frameId]);

  // Render
  const handleRender = useCallback(async () => {
    if (!plan) return;
    setLoading('rendering');
    try {
      const res = await fetch(`${API_BASE}/render/${plan.plan_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (data.render_id) {
        const filesRes = await fetch(`${API_BASE}/render/${data.render_id}/files`);
        const filesData = await filesRes.json();
        setRenderImages((filesData.files || []).map((f: { url: string }) => `/radar-viz/api${f.url}`));
      }
    } catch (err) {
      console.error('Render failed:', err);
    }
    setLoading('');
  }, [plan]);

  // Compile & execute DSL
  const handleCompileDsl = useCallback(async () => {
    setLoading('compiling');
    try {
      const compileRes = await fetch(`${API_BASE}/dsl/compile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaml: dslYaml }),
      });
      const compiled = await compileRes.json();
      if (compiled.errors) {
        setDslResult({ success: false, errors: compiled.errors || compiled.detail?.errors });
        setLoading('');
        return;
      }
      // Execute
      const execRes = await fetch(`${API_BASE}/dsl/execute/${compiled.job_id}`, { method: 'POST' });
      const execData = await execRes.json();
      setDslResult(execData);

      // Update plan if available
      if (execData.plan?.plan_id) {
        setPlan({
          plan_id: execData.plan.plan_id,
          drone_count: execData.plan.drone_count,
          total_duration_sec: execData.plan.total_duration_sec,
          risk: execData.plan.risk,
          drone_preview: [],
        });
      }
    } catch (err) {
      console.error(err);
      setDslResult({ success: false, errors: [String(err)] });
    }
    setLoading('');
  }, [dslYaml]);

  // Add obstacle preset
  const handleAddObstacle = useCallback(async (preset: typeof OBS_PRESETS[0]) => {
    try {
      const res = await fetch(`${API_BASE}/obstacles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(preset),
      });
      const obs = await res.json();
      setObstacles(prev => [...prev, obs]);
    } catch (err) { console.error(err); }
  }, []);

  // Remove obstacle
  const handleRemoveObstacle = useCallback(async (id: string) => {
    try {
      await fetch(`${API_BASE}/obstacles/${id}`, { method: 'DELETE' });
      setObstacles(prev => prev.filter(o => o.obstacle_id !== id));
    } catch (err) { console.error(err); }
  }, []);

  // Run simulation
  const handleSimulate = useCallback(async () => {
    if (!plan) return;
    setLoading('simulating');
    try {
      const res = await fetch(`${API_BASE}/simulate/${plan.plan_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      setSimReport(await res.json());
    } catch (err) { console.error(err); }
    setLoading('');
  }, [plan]);

  // Draw formation on canvas
  const drawFormation = useCallback((pts: PointPreview[]) => {
    const canvas = canvasRef.current;
    if (!canvas || pts.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;
    ctx.fillStyle = '#0b0f19';
    ctx.fillRect(0, 0, W, H);

    // Find bounds
    const xs = pts.map(p => p.xyz[0]);
    const ys = pts.map(p => p.xyz[1]);
    const xMin = Math.min(...xs) - 5;
    const xMax = Math.max(...xs) + 5;
    const yMin = Math.min(...ys) - 5;
    const yMax = Math.max(...ys) + 5;
    const scale = Math.min((W - 40) / (xMax - xMin), (H - 40) / (yMax - yMin));
    const cx = W / 2;
    const cy = H / 2;
    const midX = (xMin + xMax) / 2;
    const midY = (yMin + yMax) / 2;

    for (const p of pts) {
      const sx = cx + (p.xyz[0] - midX) * scale;
      const sy = cy - (p.xyz[1] - midY) * scale;
      const [r, g, b] = p.rgb888;
      const radius = 2 + p.importance * 3;

      // Glow
      const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, radius * 3);
      grad.addColorStop(0, `rgba(${r},${g},${b},0.4)`);
      grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
      ctx.beginPath();
      ctx.arc(sx, sy, radius * 3, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      // Dot
      ctx.beginPath();
      ctx.arc(sx, sy, radius, 0, Math.PI * 2);
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fill();
    }

    // Label
    ctx.font = 'bold 10px monospace';
    ctx.fillStyle = '#64748b';
    ctx.textAlign = 'center';
    ctx.fillText(`${pts.length} DRONES · SIMULATION ONLY`, W / 2, H - 8);
  }, []);

  // Draw paths on canvas
  const drawPaths = useCallback((dronePreviews: PlanPreview['drone_preview']) => {
    const canvas = canvasRef.current;
    if (!canvas || dronePreviews.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;
    ctx.fillStyle = '#0b0f19';
    ctx.fillRect(0, 0, W, H);

    const allX = dronePreviews.flatMap(d => [d.ground[0], d.target[0]]);
    const allY = dronePreviews.flatMap(d => [d.ground[1], d.target[1]]);
    const xMin = Math.min(...allX) - 5;
    const xMax = Math.max(...allX) + 5;
    const yMin = Math.min(...allY) - 5;
    const yMax = Math.max(...allY) + 5;
    const scale = Math.min((W - 40) / (xMax - xMin), (H - 40) / (yMax - yMin));
    const cx = W / 2;
    const cy = H / 2;
    const midX = (xMin + xMax) / 2;
    const midY = (yMin + yMax) / 2;

    for (const d of dronePreviews) {
      const gx = cx + (d.ground[0] - midX) * scale;
      const gy = cy - (d.ground[1] - midY) * scale;
      const tx = cx + (d.target[0] - midX) * scale;
      const ty = cy - (d.target[1] - midY) * scale;
      const [r, g, b] = d.color;

      // Path line
      ctx.beginPath();
      ctx.moveTo(gx, gy);
      ctx.lineTo(tx, ty);
      ctx.strokeStyle = `rgba(${r},${g},${b},0.25)`;
      ctx.lineWidth = 0.5;
      ctx.stroke();

      // Ground point
      ctx.beginPath();
      ctx.arc(gx, gy, 2, 0, Math.PI * 2);
      ctx.fillStyle = '#1e40af';
      ctx.fill();

      // Target point
      ctx.beginPath();
      ctx.arc(tx, ty, 3, 0, Math.PI * 2);
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fill();
    }

    ctx.font = 'bold 10px monospace';
    ctx.fillStyle = '#64748b';
    ctx.textAlign = 'center';
    ctx.fillText(`FLIGHT PATHS · ${dronePreviews.length} DRONES`, W / 2, H - 8);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-wide">DRONE SHOW STUDIO</h2>
        <p className="text-sm text-slate-500 mt-1">
          SIMULATION ONLY — 無人機群飛展演動畫與可行性模擬平台
        </p>
      </div>

      {/* Step 1: Upload + Config */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card">
          <h3 className="card-header">1. 上傳素材</h3>
          <input ref={fileRef} type="file" accept="image/*" onChange={handleUpload}
            className="hidden" />
          <button onClick={() => fileRef.current?.click()}
            className="w-full py-8 border-2 border-dashed border-slate-700 rounded-lg text-slate-400 hover:border-green-600 hover:text-green-400 transition-all text-sm"
            disabled={loading === 'uploading'}>
            {loading === 'uploading' ? 'Uploading...' : thumbnail ? 'Change Image' : 'Click to Upload PNG/JPG/SVG'}
          </button>
          {thumbnail && (
            <img src={thumbnail} alt="preview" className="mt-3 mx-auto rounded-lg max-h-32 border border-slate-700" />
          )}
          {assetId && <p className="text-[10px] text-slate-600 font-mono mt-1">ID: {assetId}</p>}
        </div>

        <div className="card">
          <h3 className="card-header">2. 設定參數</h3>
          <label className="text-xs text-slate-400 block mb-2">無人機數量 (5 ~ 10,000)</label>
          <div className="flex gap-2 mb-2">
            {[20, 50, 100, 200].map(n => (
              <button key={n} onClick={() => { setDroneCount(n); setCustomCount(''); }}
                className={`flex-1 py-2 rounded-md text-sm font-mono border transition-all ${
                  droneCount === n && !customCount
                    ? 'bg-green-900/50 border-green-500 text-green-400'
                    : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-500'
                }`}>{n}</button>
            ))}
          </div>
          <div className="flex gap-2 mb-4">
            <input
              type="number" min={5} max={10000} step={10}
              value={customCount}
              onChange={e => {
                setCustomCount(e.target.value);
                const v = parseInt(e.target.value);
                if (v >= 5 && v <= 10000) setDroneCount(v);
              }}
              placeholder="自訂數量 (200+)"
              className={`flex-1 bg-slate-800 border rounded-md px-3 py-2 text-sm font-mono focus:outline-none transition-all ${
                customCount ? 'border-green-500 text-green-400' : 'border-slate-700 text-slate-400'
              }`}
            />
            {customCount && (
              <span className="flex items-center text-xs text-green-400 font-mono">
                {droneCount.toLocaleString()} 台
              </span>
            )}
          </div>
          <button onClick={handleGenerate} disabled={!assetId || loading !== ''}
            className="w-full py-2.5 rounded-md bg-green-600 text-white font-medium text-sm hover:bg-green-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
            {loading === 'generating' ? 'Generating...' : 'Generate Formation Points'}
          </button>
        </div>

        <div className="card">
          <h3 className="card-header">3. 規劃與渲染</h3>
          <button onClick={handlePlan} disabled={!frameId || loading !== ''}
            className="w-full py-2.5 rounded-md bg-blue-600 text-white font-medium text-sm hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all mb-2">
            {loading === 'planning' ? 'Planning...' : 'Plan Animation'}
          </button>
          <button onClick={handleRender} disabled={!plan || loading !== ''}
            className="w-full py-2.5 rounded-md bg-amber-600 text-white font-medium text-sm hover:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
            {loading === 'rendering' ? 'Rendering...' : 'Render Preview'}
          </button>
        </div>
      </div>

      {/* Status cards */}
      {(points.length > 0 || plan) && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="card text-center py-3">
            <p className="text-[10px] text-slate-500">Drones</p>
            <p className="text-lg font-bold text-green-400">{points.length || droneCount}</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-[10px] text-slate-500">Detail Score</p>
            <p className="text-lg font-bold text-cyan-400">{(detailScore * 100).toFixed(0)}%</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-[10px] text-slate-500">Min Distance</p>
            <p className="text-lg font-bold text-amber-400">
              {plan ? `${plan.risk.min_drone_distance.toFixed(1)}m` : '--'}
            </p>
          </div>
          <div className="card text-center py-3">
            <p className="text-[10px] text-slate-500">Duration</p>
            <p className="text-lg font-bold text-blue-400">
              {plan ? `${plan.total_duration_sec}s` : '--'}
            </p>
          </div>
          <div className="card text-center py-3">
            <p className="text-[10px] text-slate-500">Warnings</p>
            <p className={`text-lg font-bold ${warnings.length > 0 ? 'text-red-400' : 'text-green-400'}`}>
              {warnings.length + (plan?.risk.warnings.length || 0)}
            </p>
          </div>
        </div>
      )}

      {/* Canvas preview */}
      <div className="card">
        <h3 className="card-header">Formation Preview</h3>
        <div className="flex justify-center">
          <canvas ref={canvasRef} width={700} height={500}
            className="rounded-lg border border-slate-800 w-full max-w-[700px]"
            style={{ filter: 'drop-shadow(0 0 20px rgba(22, 163, 74, 0.15))' }} />
        </div>
      </div>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="card">
          <h3 className="card-header">Warnings</h3>
          <div className="space-y-1">
            {warnings.map((w, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className="text-amber-400 mt-0.5">&#9888;</span>
                <span className="text-slate-400">{w}</span>
              </div>
            ))}
            {plan?.risk.warnings.map((w, i) => (
              <div key={`r${i}`} className="flex items-start gap-2 text-xs">
                <span className="text-red-400 mt-0.5">&#9888;</span>
                <span className="text-slate-400">{w}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Render outputs */}
      {renderImages.length > 0 && (
        <div className="card">
          <h3 className="card-header">Render Output</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {renderImages.map((url, i) => (
              <a key={i} href={url} target="_blank" rel="noopener noreferrer">
                <img src={url} alt={`render-${i}`}
                  className="rounded-lg border border-slate-700 hover:border-green-500 transition-all" />
              </a>
            ))}
          </div>
        </div>
      )}

      {/* ═══ Obstacles ═══ */}
      <div className="card">
        <h3 className="card-header">
          Canvas 禁飛區 / 障礙物
          <span className="text-slate-500 font-normal text-xs ml-2">畫出不可穿越的 3D 體積</span>
        </h3>
        <div className="flex flex-wrap gap-2 mb-3">
          {OBS_PRESETS.map((preset, i) => (
            <button key={i} onClick={() => handleAddObstacle(preset)}
              className="px-3 py-1.5 text-xs rounded-md border border-slate-700 bg-slate-800/50 text-slate-400 hover:border-amber-600 hover:text-amber-400 transition-all">
              + {preset.name}
            </button>
          ))}
        </div>
        {obstacles.length > 0 && (
          <div className="space-y-1">
            {obstacles.map(obs => (
              <div key={obs.obstacle_id} className="flex items-center justify-between px-3 py-2 rounded bg-slate-800/50 border border-slate-700/50">
                <div className="flex items-center gap-3">
                  <span className={`w-3 h-3 rounded ${obs.type === 'sphere_volume' ? 'bg-amber-500' : obs.type === 'cylinder_volume' ? 'bg-red-500' : 'bg-blue-500'}`} />
                  <span className="text-sm text-slate-300">{obs.name}</span>
                  <span className="text-[10px] text-slate-500 font-mono">{obs.type}</span>
                  <span className="text-[10px] text-slate-500">z: {obs.z_min}-{obs.z_max}m</span>
                </div>
                <button onClick={() => handleRemoveObstacle(obs.obstacle_id)}
                  className="text-xs text-red-400 hover:text-red-300 px-2">Remove</button>
              </div>
            ))}
          </div>
        )}
        {obstacles.length === 0 && (
          <p className="text-xs text-slate-500">尚未新增障礙物。點擊上方按鈕新增預設障礙，或使用 API 自定義。</p>
        )}
      </div>

      {/* ═══ LLM Scene DSL ═══ */}
      <div className="card">
        <h3 className="card-header">
          Scene DSL 編輯器
          <span className="text-slate-500 font-normal text-xs ml-2">YAML 動畫腳本 — LLM 可直接產生</span>
        </h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <textarea
              value={dslYaml}
              onChange={e => setDslYaml(e.target.value)}
              rows={16}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-xs font-mono text-green-300 focus:outline-none focus:border-green-500 resize-y"
              spellCheck={false}
            />
            <button onClick={handleCompileDsl} disabled={loading === 'compiling'}
              className="mt-2 w-full py-2.5 rounded-md bg-purple-600 text-white font-medium text-sm hover:bg-purple-500 disabled:opacity-40 transition-all">
              {loading === 'compiling' ? 'Compiling & Executing...' : 'Compile & Execute DSL'}
            </button>
          </div>
          <div className="text-xs">
            {dslResult && (
              <div className="space-y-2">
                {(dslResult as any).success === false ? (
                  <div className="rounded-lg bg-red-900/20 border border-red-800/30 p-3">
                    <p className="text-red-400 font-semibold mb-1">Compilation Errors</p>
                    {((dslResult as any).errors || []).map((e: string, i: number) => (
                      <p key={i} className="text-red-300">{e}</p>
                    ))}
                  </div>
                ) : (
                  <>
                    <div className="rounded-lg bg-green-900/20 border border-green-800/30 p-3">
                      <p className="text-green-400 font-semibold mb-1">Execution Complete</p>
                      <p className="text-slate-400">Job: <span className="text-white font-mono">{(dslResult as any).job_id}</span></p>
                      <p className="text-slate-400">Frames generated: <span className="text-white">{((dslResult as any).generated_frame_ids || []).length}</span></p>
                    </div>
                    {(dslResult as any).executed_frames?.map((f: any, i: number) => (
                      <div key={i} className={`rounded px-3 py-2 border ${f.error ? 'bg-red-900/10 border-red-800/20' : f.skipped ? 'bg-slate-800/50 border-slate-700/30' : 'bg-cyan-900/10 border-cyan-800/20'}`}>
                        <span className={`font-mono ${f.error ? 'text-red-400' : f.skipped ? 'text-slate-500' : 'text-cyan-400'}`}>{f.type}</span>
                        {f.frame_id && <span className="ml-2 text-slate-400">→ {f.frame_id}</span>}
                        {f.points && <span className="ml-2 text-green-400">{f.points} pts</span>}
                        {f.ops && <span className="ml-2 text-amber-400">[{f.ops.join(', ')}]</span>}
                        {f.error && <span className="ml-2 text-red-300">{f.error}</span>}
                        {f.skipped && <span className="ml-2 text-slate-500">(skipped)</span>}
                      </div>
                    ))}
                    {(dslResult as any).plan && (
                      <div className="rounded-lg bg-blue-900/20 border border-blue-800/30 p-3 mt-2">
                        <p className="text-blue-400 font-semibold mb-1">Timeline Plan</p>
                        <p className="text-slate-400">Plan: <span className="text-white font-mono">{(dslResult as any).plan.plan_id}</span></p>
                        <p className="text-slate-400">Duration: <span className="text-white">{(dslResult as any).plan.total_duration_sec}s</span></p>
                        <p className="text-slate-400">Min dist: <span className="text-white">{(dslResult as any).plan.risk?.min_drone_distance?.toFixed(2)}m</span></p>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
            {!dslResult && (
              <div className="text-slate-500 p-4 space-y-2">
                <p className="font-semibold text-slate-400">支援的 Frame Types:</p>
                <p><span className="text-cyan-400 font-mono">takeoff_blue</span> — 藍色起飛</p>
                <p><span className="text-cyan-400 font-mono">image_formation</span> — 圖片→隊形</p>
                <p><span className="text-cyan-400 font-mono">transform</span> — 幾何變換（放大/縮小/旋轉/平移）</p>
                <p><span className="text-cyan-400 font-mono">color_change</span> — LED 顏色切換</p>
                <p><span className="text-cyan-400 font-mono">hold</span> — 定點停留</p>
                <p><span className="text-cyan-400 font-mono">landing_blue</span> — 藍色降落</p>
                <p className="mt-3 font-semibold text-slate-400">Transform 指令範例:</p>
                <p className="text-slate-500">「放大 20%」「往上移動 10m」「順時針旋轉 30 度」</p>
                <p className="text-slate-500">「左右展開 15%」「縮小到一半」「升高 20 公尺」</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══ Simulation ═══ */}
      {plan && (
        <div className="card">
          <h3 className="card-header">
            碰撞 / 速度模擬
            <span className="text-slate-500 font-normal text-xs ml-2">高頻取樣路徑檢查</span>
          </h3>
          <button onClick={handleSimulate} disabled={loading === 'simulating'}
            className="px-6 py-2 bg-purple-600 text-white rounded-md text-sm hover:bg-purple-500 disabled:opacity-40 transition-all mb-4">
            {loading === 'simulating' ? 'Running Simulation...' : 'Run Full Simulation'}
          </button>

          {simReport && (
            <div className="space-y-4">
              {/* Risk level badge */}
              <div className="flex items-center gap-3">
                <span className={`px-3 py-1 rounded-full text-sm font-bold uppercase ${
                  simReport.risk_level === 'critical' ? 'bg-red-900/50 text-red-400 border border-red-600' :
                  simReport.risk_level === 'high' ? 'bg-amber-900/50 text-amber-400 border border-amber-600' :
                  simReport.risk_level === 'moderate' ? 'bg-yellow-900/50 text-yellow-400 border border-yellow-600' :
                  'bg-green-900/50 text-green-400 border border-green-600'
                }`}>{simReport.risk_level} RISK</span>
                <span className="text-xs text-slate-500">SIMULATION_ONLY</span>
              </div>

              {/* Metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="rounded-lg bg-slate-800/50 border border-slate-700/50 p-3 text-center">
                  <p className="text-[10px] text-slate-500">Min Distance</p>
                  <p className={`text-lg font-bold ${simReport.inter_drone.min_distance < 2 ? 'text-red-400' : simReport.inter_drone.min_distance < 3 ? 'text-amber-400' : 'text-green-400'}`}>
                    {simReport.inter_drone.min_distance.toFixed(2)}m
                  </p>
                </div>
                <div className="rounded-lg bg-slate-800/50 border border-slate-700/50 p-3 text-center">
                  <p className="text-[10px] text-slate-500">Close Approaches</p>
                  <p className={`text-lg font-bold ${simReport.inter_drone.close_approach_count > 0 ? 'text-amber-400' : 'text-green-400'}`}>
                    {simReport.inter_drone.close_approach_count}
                  </p>
                </div>
                <div className="rounded-lg bg-slate-800/50 border border-slate-700/50 p-3 text-center">
                  <p className="text-[10px] text-slate-500">Max Speed</p>
                  <p className={`text-lg font-bold ${simReport.speed_summary.max_speed > 15 ? 'text-red-400' : 'text-green-400'}`}>
                    {simReport.speed_summary.max_speed.toFixed(1)} m/s
                  </p>
                </div>
                <div className="rounded-lg bg-slate-800/50 border border-slate-700/50 p-3 text-center">
                  <p className="text-[10px] text-slate-500">Speed Violations</p>
                  <p className={`text-lg font-bold ${simReport.speed_summary.total_violations > 0 ? 'text-red-400' : 'text-green-400'}`}>
                    {simReport.speed_summary.total_violations}
                  </p>
                </div>
              </div>

              {/* Warnings */}
              {simReport.warnings.length > 0 && (
                <div className="space-y-1">
                  {simReport.warnings.map((w, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs px-3 py-1.5 rounded bg-red-900/10 border border-red-800/20">
                      <span className="text-red-400 mt-0.5">&#9888;</span>
                      <span className="text-slate-300">{w}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="text-[10px] text-slate-600 text-center font-mono">
        SIMULATION_ONLY — 所有輸出僅供動畫與可行性模擬，不輸出實機飛控指令
      </div>
    </div>
  );
}
