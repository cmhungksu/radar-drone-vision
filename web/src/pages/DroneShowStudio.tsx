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

export default function DroneShowStudio() {
  const [assetId, setAssetId] = useState<string | null>(null);
  const [thumbnail, setThumbnail] = useState<string | null>(null);
  const [droneCount, setDroneCount] = useState(50);
  const [points, setPoints] = useState<PointPreview[]>([]);
  const [frameId, setFrameId] = useState<string | null>(null);
  const [detailScore, setDetailScore] = useState(0);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [plan, setPlan] = useState<PlanPreview | null>(null);
  const [renderImages, setRenderImages] = useState<string[]>([]);
  const [loading, setLoading] = useState('');
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
          <label className="text-xs text-slate-400 block mb-2">無人機數量</label>
          <div className="flex gap-2 mb-4">
            {[20, 50, 100, 200].map(n => (
              <button key={n} onClick={() => setDroneCount(n)}
                className={`flex-1 py-2 rounded-md text-sm font-mono border transition-all ${
                  droneCount === n
                    ? 'bg-green-900/50 border-green-500 text-green-400'
                    : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-500'
                }`}>{n}</button>
            ))}
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
    </div>
  );
}
