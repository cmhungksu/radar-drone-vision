import { useRef, useEffect, useCallback, useState } from 'react';

interface DroneFlightAnimationProps {
  planId: string;
  mode: '2d' | '3d';
}

interface DroneState {
  drone_id: string;
  x: number; y: number; z: number;
  rgb: number[];
  segment_id: string;
}

// Cubic Bezier with Catmull-Rom smoothing for smooth continuous curves
function catmullRomToBezier(
  p0: number[], p1: number[], p2: number[], p3: number[]
): number[][] {
  const alpha = 0.5; // centripetal
  return [
    p1,
    [
      p1[0] + (p2[0] - p0[0]) / (6 * alpha),
      p1[1] + (p2[1] - p0[1]) / (6 * alpha),
      p1[2] + (p2[2] - p0[2]) / (6 * alpha),
    ],
    [
      p2[0] - (p3[0] - p1[0]) / (6 * alpha),
      p2[1] - (p3[1] - p1[1]) / (6 * alpha),
      p2[2] - (p3[2] - p1[2]) / (6 * alpha),
    ],
    p2,
  ];
}

// High-precision Bezier evaluation using De Casteljau's algorithm
function bezierEval(points: number[][], t: number): number[] {
  let pts = points.map(p => [...p]);
  while (pts.length > 1) {
    const next: number[][] = [];
    for (let i = 0; i < pts.length - 1; i++) {
      next.push(pts[i].map((v, k) => (1 - t) * v + t * pts[i + 1][k]));
    }
    pts = next;
  }
  return pts[0];
}

// Smooth path: ensure C1 continuity by inserting Catmull-Rom intermediate points
function smoothPath(controlPoints: number[][], numSamples: number): number[][] {
  if (controlPoints.length < 2) return controlPoints;

  // Pad endpoints for Catmull-Rom
  const pts = [
    controlPoints[0],
    ...controlPoints,
    controlPoints[controlPoints.length - 1],
  ];

  const result: number[][] = [];
  for (let seg = 1; seg < pts.length - 2; seg++) {
    const bezPts = catmullRomToBezier(pts[seg - 1], pts[seg], pts[seg + 1], pts[seg + 2]);
    const segSamples = Math.max(2, Math.floor(numSamples / (pts.length - 3)));
    for (let i = 0; i < segSamples; i++) {
      const t = i / segSamples;
      result.push(bezierEval(bezPts, t));
    }
  }
  // Add final point
  result.push(controlPoints[controlPoints.length - 1]);
  return result;
}

const API = '/radar-viz/api/drone-show';

export default function DroneFlightAnimation({ planId, mode }: DroneFlightAnimationProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1.0);
  const [progress, setProgress] = useState(0);
  const planRef = useRef<Record<string, unknown> | null>(null);
  const pathCacheRef = useRef<Map<string, number[][]>>(new Map());
  const startTimeRef = useRef(0);
  const pauseTimeRef = useRef(0);

  // Load plan data
  useEffect(() => {
    if (!planId) return;
    fetch(`${API}/plan/${planId}`)
      .then(r => r.json())
      .then(data => {
        // Need full plan for path data - fetch the private plan file
        // For now we'll use the preview data and generate smooth paths
        planRef.current = data;
      })
      .catch(console.error);
  }, [planId]);

  // Fetch full plan with segments for animation
  useEffect(() => {
    if (!planId) return;
    fetch(`${API}/simulate/${planId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sample_rate: 20 }),
    })
      .then(r => r.json())
      .then(simData => {
        // Store simulation data for animation
        (planRef.current as any)._simData = simData;
      })
      .catch(() => {});
  }, [planId]);

  const draw2D = useCallback((ctx: CanvasRenderingContext2D, t: number, W: number, H: number) => {
    const plan = planRef.current as any;
    if (!plan?.drone_preview) return;

    ctx.fillStyle = '#0b0f19';
    ctx.fillRect(0, 0, W, H);

    const drones = plan.drone_preview || [];
    const totalDur = plan.total_duration_sec || 22;
    const phase = t / totalDur; // 0 → 1
    const takeoffPhase = 8 / totalDur;
    const holdEnd = (8 + 6) / totalDur;
    const landingStart = 1 - 8 / totalDur;

    // Find bounds
    const allX = drones.flatMap((d: any) => [d.ground[0], d.target[0]]);
    const allY = drones.flatMap((d: any) => [d.ground[1], d.target[1]]);
    const xMin = Math.min(...allX) - 10;
    const xMax = Math.max(...allX) + 10;
    const yMin = Math.min(...allY) - 10;
    const yMax = Math.max(...allY) + 10;
    const scale = Math.min((W - 60) / (xMax - xMin), (H - 60) / (yMax - yMin));
    const cx = W / 2, cy = H / 2;
    const midX = (xMin + xMax) / 2, midY = (yMin + yMax) / 2;

    const toScreen = (x: number, y: number) => [
      cx + (x - midX) * scale,
      cy - (y - midY) * scale,
    ];

    // Grid
    ctx.strokeStyle = 'rgba(22, 163, 74, 0.08)';
    ctx.lineWidth = 0.5;
    for (let gx = Math.floor(xMin / 10) * 10; gx <= xMax; gx += 10) {
      const [sx] = toScreen(gx, 0);
      ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, H); ctx.stroke();
    }
    for (let gy = Math.floor(yMin / 10) * 10; gy <= yMax; gy += 10) {
      const [, sy] = toScreen(0, gy);
      ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(W, sy); ctx.stroke();
    }

    // Draw each drone
    for (const d of drones) {
      const gx = d.ground[0], gy = d.ground[1];
      const tx = d.target[0], ty = d.target[1];
      const [r, g, b] = d.color;

      // Smooth Bezier interpolation with high precision
      const controlPts = [
        [gx, gy, 0],
        [gx, gy, 30],                          // rise up
        [(gx + tx) / 2, (gy + ty) / 2, 55],    // mid transit
        [tx, ty, 50],                           // target
      ];

      // Compute smooth path using Catmull-Rom
      const smoothPts = smoothPath(controlPts, 60);

      // Current position based on phase
      let px: number, py: number;

      if (phase < takeoffPhase) {
        // Takeoff: ground → target via smooth path
        const f = phase / takeoffPhase;
        const idx = Math.min(Math.floor(f * (smoothPts.length - 1)), smoothPts.length - 1);
        [px, py] = [smoothPts[idx][0], smoothPts[idx][1]];
      } else if (phase < holdEnd) {
        // Hold at target
        px = tx; py = ty;
      } else if (phase < landingStart) {
        // Hold at target (if single frame)
        px = tx; py = ty;
      } else {
        // Landing: target → ground (reverse)
        const f = (phase - landingStart) / (1 - landingStart);
        const idx = Math.min(Math.floor((1 - f) * (smoothPts.length - 1)), smoothPts.length - 1);
        [px, py] = [smoothPts[idx][0], smoothPts[idx][1]];
      }

      const [sx, sy] = toScreen(px, py);

      // LED color: blue during takeoff/landing, target color during hold
      let cr = r, cg = g, cb = b;
      if (phase < takeoffPhase * 0.8 || phase > landingStart + (1 - landingStart) * 0.2) {
        cr = 0; cg = 60; cb = 200; // takeoff blue
      }

      // Trail (last few positions)
      if (phase > 0.01) {
        ctx.globalAlpha = 0.15;
        for (let trail = 1; trail <= 5; trail++) {
          const tp = Math.max(0, phase - trail * 0.01);
          let trx: number, try_: number;
          if (tp < takeoffPhase) {
            const f = tp / takeoffPhase;
            const idx = Math.min(Math.floor(f * (smoothPts.length - 1)), smoothPts.length - 1);
            [trx, try_] = [smoothPts[idx][0], smoothPts[idx][1]];
          } else {
            trx = tx; try_ = ty;
          }
          const [tsx, tsy] = toScreen(trx, try_);
          ctx.beginPath();
          ctx.arc(tsx, tsy, 2, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${cr},${cg},${cb},${0.3 - trail * 0.05})`;
          ctx.fill();
        }
        ctx.globalAlpha = 1;
      }

      // Glow
      const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, 12);
      grad.addColorStop(0, `rgba(${cr},${cg},${cb},0.4)`);
      grad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
      ctx.beginPath();
      ctx.arc(sx, sy, 12, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      // Dot
      ctx.beginPath();
      ctx.arc(sx, sy, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = `rgb(${cr},${cg},${cb})`;
      ctx.shadowColor = `rgb(${cr},${cg},${cb})`;
      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    // HUD
    ctx.font = 'bold 11px monospace';
    ctx.fillStyle = '#16a34a';
    ctx.textAlign = 'left';
    ctx.fillText(`DRONE SHOW · ${drones.length} DRONES · ${mode.toUpperCase()}`, 10, 18);
    ctx.fillStyle = '#64748b';
    ctx.fillText(`t = ${t.toFixed(1)}s / ${totalDur.toFixed(0)}s`, 10, 34);
    ctx.fillText(`Phase: ${phase < takeoffPhase ? 'TAKEOFF' : phase < holdEnd ? 'FORMATION' : phase < landingStart ? 'HOLD' : 'LANDING'}`, 10, 50);

    // Progress bar
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(10, H - 16, W - 20, 6);
    ctx.fillStyle = '#22c55e';
    ctx.fillRect(10, H - 16, (W - 20) * phase, 6);

    ctx.font = '8px monospace';
    ctx.fillStyle = '#475569';
    ctx.textAlign = 'center';
    ctx.fillText('SIMULATION ONLY', W / 2, H - 4);
  }, [mode]);

  const draw3D = useCallback((ctx: CanvasRenderingContext2D, t: number, W: number, H: number) => {
    const plan = planRef.current as any;
    if (!plan?.drone_preview) return;

    ctx.fillStyle = '#0b0f19';
    ctx.fillRect(0, 0, W, H);

    const drones = plan.drone_preview || [];
    const totalDur = plan.total_duration_sec || 22;
    const phase = t / totalDur;
    const takeoffPhase = 8 / totalDur;

    // 3D isometric projection
    const isoX = (x: number, y: number, z: number) => W / 2 + (x - y) * 0.7 * 4;
    const isoY = (x: number, y: number, z: number) => H * 0.7 - z * 3 + (x + y) * 0.35 * 4;

    // Ground grid
    ctx.strokeStyle = 'rgba(22, 163, 74, 0.1)';
    ctx.lineWidth = 0.5;
    for (let i = -50; i <= 50; i += 10) {
      ctx.beginPath();
      ctx.moveTo(isoX(i, -50, 0), isoY(i, -50, 0));
      ctx.lineTo(isoX(i, 50, 0), isoY(i, 50, 0));
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(isoX(-50, i, 0), isoY(-50, i, 0));
      ctx.lineTo(isoX(50, i, 0), isoY(50, i, 0));
      ctx.stroke();
    }

    // Sort drones by depth for proper 3D rendering
    const droneStates = drones.map((d: any) => {
      const gx = d.ground[0], gy = d.ground[1];
      const tx = d.target[0], ty = d.target[1];

      const controlPts = [[gx, gy, 0], [gx, gy, 30], [(gx+tx)/2, (gy+ty)/2, 55], [tx, ty, 50]];
      const smoothPts = smoothPath(controlPts, 40);

      let px: number, py: number, pz: number;
      const holdEnd = (8 + 6) / totalDur;
      const landingStart = 1 - 8 / totalDur;

      if (phase < takeoffPhase) {
        const f = phase / takeoffPhase;
        const idx = Math.min(Math.floor(f * (smoothPts.length - 1)), smoothPts.length - 1);
        [px, py, pz] = smoothPts[idx];
      } else if (phase < landingStart) {
        px = tx; py = ty; pz = 50;
      } else {
        const f = (phase - landingStart) / (1 - landingStart);
        const idx = Math.min(Math.floor((1 - f) * (smoothPts.length - 1)), smoothPts.length - 1);
        [px, py, pz] = smoothPts[idx];
      }

      let cr = d.color[0], cg = d.color[1], cb = d.color[2];
      if (phase < takeoffPhase * 0.8 || phase > landingStart + (1 - landingStart) * 0.2) {
        cr = 0; cg = 60; cb = 200;
      }

      return { px, py, pz, cr, cg, cb, depth: px + py };
    });

    // Sort by depth (far first)
    droneStates.sort((a: any, b: any) => a.depth - b.depth);

    for (const d of droneStates) {
      const sx = isoX(d.px, d.py, d.pz);
      const sy = isoY(d.px, d.py, d.pz);

      // Shadow on ground
      const gsx = isoX(d.px, d.py, 0);
      const gsy = isoY(d.px, d.py, 0);
      ctx.beginPath();
      ctx.ellipse(gsx, gsy, 3, 1.5, 0, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(0,0,0,0.2)';
      ctx.fill();

      // Altitude line
      ctx.beginPath();
      ctx.moveTo(gsx, gsy);
      ctx.lineTo(sx, sy);
      ctx.strokeStyle = `rgba(${d.cr},${d.cg},${d.cb},0.1)`;
      ctx.lineWidth = 0.5;
      ctx.stroke();

      // Glow
      const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, 10);
      grad.addColorStop(0, `rgba(${d.cr},${d.cg},${d.cb},0.5)`);
      grad.addColorStop(1, `rgba(${d.cr},${d.cg},${d.cb},0)`);
      ctx.beginPath();
      ctx.arc(sx, sy, 10, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      // Dot
      ctx.beginPath();
      ctx.arc(sx, sy, 3, 0, Math.PI * 2);
      ctx.fillStyle = `rgb(${d.cr},${d.cg},${d.cb})`;
      ctx.shadowColor = `rgb(${d.cr},${d.cg},${d.cb})`;
      ctx.shadowBlur = 6;
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    // HUD
    ctx.font = 'bold 11px monospace';
    ctx.fillStyle = '#16a34a';
    ctx.textAlign = 'left';
    ctx.fillText(`DRONE SHOW · ${drones.length} DRONES · 3D ISO`, 10, 18);
    ctx.fillStyle = '#64748b';
    ctx.fillText(`t = ${t.toFixed(1)}s / ${totalDur.toFixed(0)}s`, 10, 34);

    ctx.fillStyle = '#1e293b';
    ctx.fillRect(10, H - 16, W - 20, 6);
    ctx.fillStyle = '#22c55e';
    ctx.fillRect(10, H - 16, (W - 20) * phase, 6);

    ctx.font = '8px monospace';
    ctx.fillStyle = '#475569';
    ctx.textAlign = 'center';
    ctx.fillText('SIMULATION ONLY', W / 2, H - 4);
  }, []);

  // Animation loop
  useEffect(() => {
    if (!playing) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const totalDur = (planRef.current as any)?.total_duration_sec || 22;

    if (startTimeRef.current === 0) {
      startTimeRef.current = performance.now() - pauseTimeRef.current * 1000 / speed;
    }

    const animate = () => {
      const elapsed = (performance.now() - startTimeRef.current) / 1000 * speed;
      const t = elapsed % totalDur;
      setProgress(t / totalDur);

      if (mode === '2d') draw2D(ctx, t, W, H);
      else draw3D(ctx, t, W, H);

      if (playing) animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animRef.current);
  }, [playing, speed, mode, draw2D, draw3D]);

  const togglePlay = () => {
    if (playing) {
      pauseTimeRef.current = progress * ((planRef.current as any)?.total_duration_sec || 22);
      startTimeRef.current = 0;
    } else {
      startTimeRef.current = 0;
    }
    setPlaying(!playing);
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-center">
        <canvas ref={canvasRef} width={800} height={500}
          className="rounded-lg border border-slate-800 w-full max-w-[800px]"
          style={{ filter: 'drop-shadow(0 0 20px rgba(22, 163, 74, 0.15))' }} />
      </div>

      {/* Controls */}
      <div className="flex items-center justify-center gap-3">
        <button onClick={togglePlay}
          className={`px-4 py-2 rounded-md text-sm font-mono border transition-all ${
            playing ? 'bg-red-900/50 border-red-500 text-red-400' : 'bg-green-900/50 border-green-500 text-green-400'
          }`}>
          {playing ? '⏸ PAUSE' : '▶ PLAY'}
        </button>

        <div className="flex items-center gap-1">
          {[0.25, 0.5, 1, 2, 4].map(s => (
            <button key={s} onClick={() => setSpeed(s)}
              className={`px-2 py-1 rounded text-[10px] font-mono border transition-all ${
                speed === s ? 'bg-cyan-900/50 border-cyan-500 text-cyan-400' : 'bg-slate-800/50 border-slate-700 text-slate-500'
              }`}>{s}x</button>
          ))}
        </div>

        <span className="text-xs text-slate-500 font-mono">
          {Math.round(progress * 100)}%
        </span>
      </div>
    </div>
  );
}
