import { useRef, useEffect, useCallback } from 'react';
import { type AirspaceTarget } from '../api';

interface RhiCanvasProps {
  targets: AirspaceTarget[];
  maxRange?: number;
  maxAltitude?: number;
  /** When true, X-axis uses the target's Cartesian x-position (matches PPI left/right).
   *  When false (default), X-axis uses range_m. */
  alignWithPpi?: boolean;
}

// Per-target sweep state tracked independently from PPI
interface TargetSweepState {
  track_id: string;
  lastSweepTime: number; // ms timestamp when sweep last crossed this target's range position
}

// Canvas constants
const W = 700;
const H = 250;

// Padding / plot area
const PAD_LEFT = 48;   // space for Y-axis labels
const PAD_RIGHT = 16;
const PAD_TOP = 14;
const PAD_BOTTOM = 32; // space for X-axis labels

const PLOT_W = W - PAD_LEFT - PAD_RIGHT;
const PLOT_H = H - PAD_TOP - PAD_BOTTOM;

// Timing constants — same feel as PPI
const FLASH_DURATION_MS = 200;
const FADE_DURATION_MS = 4000;
const SWEEP_PERIOD_MS = 4000;

// Phosphor green
const PHOSPHOR: [number, number, number] = [34, 197, 94];

// Classification colors [r, g, b]
function classColor(classification: string): [number, number, number] {
  const c = classification.toLowerCase();
  if (c.includes('uav') || c.includes('drone')) return [239, 68, 68];   // red
  if (c.includes('bird')) return [59, 130, 246];                         // blue
  if (c.includes('human') || c.includes('person')) return [245, 158, 11]; // amber
  return [59, 130, 246]; // default blue
}

// Parse hex color → [r, g, b]
function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return null;
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
}

function targetColor(t: AirspaceTarget): [number, number, number] {
  const pc = (t as unknown as Record<string, unknown>).pixel_color;
  if (typeof pc === 'string') {
    const rgb = hexToRgb(pc);
    if (rgb) return rgb;
  }
  return classColor(t.classification);
}

// Map rcs_dbsm (-30 to 0) to dot radius (2 to 7) — identical to PPI
function rcsToRadius(rcs: number | null): number {
  if (rcs === null) return 3;
  const clamped = Math.max(-30, Math.min(0, rcs));
  return 2 + ((clamped + 30) / 30) * 5;
}

// Convert range_m → canvas X (range mode: 0 to maxRange left-to-right)
function rangeToX(range_m: number, maxRange: number): number {
  return PAD_LEFT + Math.min(range_m / maxRange, 1) * PLOT_W;
}

// Convert Cartesian x-position → canvas X (PPI-aligned: -maxRange to +maxRange)
function cartesianXToCanvasX(x: number, maxRange: number): number {
  // Map x from [-maxRange, +maxRange] to [PAD_LEFT, PAD_LEFT + PLOT_W]
  const normalized = (x + maxRange) / (2 * maxRange); // 0..1
  return PAD_LEFT + Math.max(0, Math.min(1, normalized)) * PLOT_W;
}

// Convert altitude_m → canvas Y (Y=0 is top, altitude=0 is bottom)
function altToY(altitude_m: number, maxAltitude: number): number {
  return PAD_TOP + PLOT_H - Math.min(altitude_m / maxAltitude, 1) * PLOT_H;
}

export default function RhiCanvas({
  targets,
  maxRange = 500,
  maxAltitude = 400,
  alignWithPpi = true,
}: RhiCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const targetsRef = useRef<AirspaceTarget[]>(targets);
  const sweepStateRef = useRef<Map<string, TargetSweepState>>(new Map());
  const animRef = useRef<number>(0);
  const prevTimestampRef = useRef<number | null>(null);

  // RHI sweep: fraction 0→1 moving left to right across the range axis
  const sweepFracRef = useRef<number>(0);

  // Keep targets ref in sync without restarting animation
  useEffect(() => {
    targetsRef.current = targets;
  }, [targets]);

  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, timestamp: number) => {
      // Delta time capped at 100ms (handles tab-switch stutter)
      const prev = prevTimestampRef.current ?? timestamp;
      const dtSec = Math.min((timestamp - prev) / 1000, 0.1);
      prevTimestampRef.current = timestamp;

      // Advance sweep fraction
      const sweepSpeed = 1 / (SWEEP_PERIOD_MS / 1000); // fraction per second
      let sweepFrac = sweepFracRef.current + sweepSpeed * dtSec;
      if (sweepFrac > 1) {
        sweepFrac -= 1; // wrap around
      }
      sweepFracRef.current = sweepFrac;

      // Current sweep X position in canvas coords
      const sweepX = PAD_LEFT + sweepFrac * PLOT_W;

      // Sync with PPI: use same 4-second rotation period
      // Map sweep fraction to azimuth angle (-180° to 180°)
      // When sweep "passes" a target's azimuth, that target lights up in RHI
      const sweepAzimuth = -180 + sweepFrac * 360; // -180° to +180°
      const prevSweepAzimuth = sweepAzimuth - sweepSpeed * dtSec * 360;
      const now = timestamp;
      const tgts = targetsRef.current;

      for (const t of tgts) {
        const tgtAz = t.azimuth_deg ?? 0;
        // Check if sweep just passed this target's azimuth
        const justPassed =
          (prevSweepAzimuth <= tgtAz && tgtAz <= sweepAzimuth) ||
          // Handle wrap-around (-180 → +180)
          (sweepFrac < sweepSpeed * dtSec * 2 && tgtAz > 150);

        if (justPassed) {
          sweepStateRef.current.set(t.track_id, {
            track_id: t.track_id,
            lastSweepTime: now,
          });
        }
      }

      // ── Full clear ─────────────────────────────────────────────────────────
      ctx.fillStyle = '#0b0f19';
      ctx.fillRect(0, 0, W, H);

      // ── Plot area background ────────────────────────────────────────────────
      ctx.fillStyle = 'rgba(22, 163, 74, 0.025)';
      ctx.fillRect(PAD_LEFT, PAD_TOP, PLOT_W, PLOT_H);

      // ── Grid: horizontal altitude lines ────────────────────────────────────
      const altStep = 100; // m
      for (let alt = 0; alt <= maxAltitude; alt += altStep) {
        const y = altToY(alt, maxAltitude);
        ctx.beginPath();
        ctx.moveTo(PAD_LEFT, y);
        ctx.lineTo(PAD_LEFT + PLOT_W, y);
        ctx.strokeStyle = 'rgba(22, 163, 74, 0.15)';
        ctx.lineWidth = alt === 0 ? 1.5 : 0.5; // ground line slightly brighter
        ctx.setLineDash(alt === 0 ? [] : [3, 6]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Y-axis label
        if (alt > 0) {
          ctx.font = '8px monospace';
          ctx.fillStyle = '#475569';
          ctx.textAlign = 'right';
          ctx.fillText(`${alt}`, PAD_LEFT - 4, y + 3);
        }
      }

      // ── Grid: vertical position lines ─────────────────────────────────────
      if (alignWithPpi) {
        // PPI-aligned: X-axis = Cartesian x from -maxRange to +maxRange
        const posStep = 200; // m
        for (let pos = -maxRange; pos <= maxRange; pos += posStep) {
          const x = cartesianXToCanvasX(pos, maxRange);
          ctx.beginPath();
          ctx.moveTo(x, PAD_TOP);
          ctx.lineTo(x, PAD_TOP + PLOT_H);
          ctx.strokeStyle = 'rgba(22, 163, 74, 0.15)';
          ctx.lineWidth = pos === 0 ? 1.5 : 0.5;
          ctx.setLineDash(pos === 0 ? [] : [3, 6]);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.font = '8px monospace';
          ctx.fillStyle = '#475569';
          ctx.textAlign = 'center';
          ctx.fillText(`${pos}`, x, PAD_TOP + PLOT_H + 12);
        }
      } else {
        const rangeStep = 100; // m
        for (let rng = 0; rng <= maxRange; rng += rangeStep) {
          const x = rangeToX(rng, maxRange);
          ctx.beginPath();
          ctx.moveTo(x, PAD_TOP);
          ctx.lineTo(x, PAD_TOP + PLOT_H);
          ctx.strokeStyle = 'rgba(22, 163, 74, 0.15)';
          ctx.lineWidth = rng === 0 ? 1 : 0.5;
          ctx.setLineDash(rng === 0 ? [] : [3, 6]);
          ctx.stroke();
          ctx.setLineDash([]);

        // X-axis label
        ctx.font = '8px monospace';
        ctx.fillStyle = '#475569';
        ctx.textAlign = 'center';
          ctx.fillText(`${rng}`, x, PAD_TOP + PLOT_H + 12);
        }
      }

      // ── Axis labels ─────────────────────────────────────────────────────────
      ctx.font = '9px monospace';
      ctx.fillStyle = '#64748b';
      ctx.textAlign = 'center';
      ctx.fillText(alignWithPpi ? 'POSITION (m)' : 'RANGE (m)', PAD_LEFT + PLOT_W / 2, H - 4);

      // Y-axis: "ALT (m)" rotated
      ctx.save();
      ctx.translate(10, PAD_TOP + PLOT_H / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.font = '9px monospace';
      ctx.fillStyle = '#64748b';
      ctx.textAlign = 'center';
      ctx.fillText('ALT (m)', 0, 0);
      ctx.restore();

      // ── Ground line (solid green at altitude=0) ──────────────────────────────
      const groundY = altToY(0, maxAltitude);
      ctx.beginPath();
      ctx.moveTo(PAD_LEFT, groundY);
      ctx.lineTo(PAD_LEFT + PLOT_W, groundY);
      ctx.strokeStyle = 'rgba(34, 197, 94, 0.55)';
      ctx.lineWidth = 1.5;
      ctx.shadowColor = '#22c55e';
      ctx.shadowBlur = 6;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Ground label
      ctx.font = '8px monospace';
      ctx.fillStyle = 'rgba(34, 197, 94, 0.45)';
      ctx.textAlign = 'left';
      ctx.fillText('GND', PAD_LEFT + 2, groundY - 3);

      // ── Sweep trail (gradient, drawn before targets) ─────────────────────────
      const TRAIL_PX = 80; // pixels of fading trail behind sweep line
      const trailSteps = 40;
      for (let i = 0; i < trailSteps; i++) {
        const frac = i / trailSteps;
        const trailX = sweepX - TRAIL_PX * frac;
        if (trailX < PAD_LEFT) continue;
        const alpha = 0.18 * (1 - frac) * (1 - frac);
        ctx.beginPath();
        ctx.moveTo(trailX, PAD_TOP);
        ctx.lineTo(trailX, PAD_TOP + PLOT_H);
        ctx.strokeStyle = `rgba(34, 197, 94, ${alpha})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // ── Targets (always visible — RHI shows all targets for altitude reference) ──
      for (const t of tgts) {
        const altitude = t.altitude_m ?? 0;
        // X-axis: use Cartesian x (aligned with PPI left/right) or range_m
        const cx = alignWithPpi
          ? cartesianXToCanvasX(t.x, maxRange)
          : rangeToX(t.range_m, maxRange);
        const cy = altToY(altitude, maxAltitude);

        const dotRadius = rcsToRadius(t.rcs_dbsm ?? null);
        const [cr, cg, cb] = targetColor(t);

        // Sweep flash effect (visual only, targets are always visible)
        const st = sweepStateRef.current.get(t.track_id);
        const timeSinceSweep = st ? now - st.lastSweepTime : Infinity;
        const isFlashing = timeSinceSweep < FLASH_DURATION_MS;
        const baseAlpha = 0.5 + 0.4 * t.confidence;
        const mainAlpha = isFlashing ? 1.0 : baseAlpha;

        // Glow halo
        const glowRadius = isFlashing ? dotRadius * 3 : dotRadius * 1.5;
        const glowAlpha = isFlashing ? 0.5 : baseAlpha * 0.15;
        const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowRadius);
        gradient.addColorStop(0, `rgba(${cr},${cg},${cb}, ${glowAlpha})`);
        gradient.addColorStop(1, `rgba(${cr},${cg},${cb}, 0)`);
        ctx.beginPath();
        ctx.arc(cx, cy, glowRadius, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();

        // Main dot
        ctx.beginPath();
        ctx.arc(cx, cy, dotRadius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${cr},${cg},${cb}, ${mainAlpha})`;
        ctx.shadowColor = `rgb(${cr},${cg},${cb})`;
        ctx.shadowBlur = isFlashing ? 10 : 3;
        ctx.fill();
        ctx.shadowBlur = 0;

        // Label
        const label = t.label ?? t.track_id;
        const altStr = typeof altitude === 'number' ? ` ${Math.round(altitude)}m` : '';
        ctx.font = 'bold 7px monospace';
        ctx.fillStyle = `rgba(${cr},${cg},${cb}, ${mainAlpha * 0.7})`;
        ctx.textAlign = 'left';
        const lx = Math.min(cx + dotRadius + 3, PAD_LEFT + PLOT_W - 60);
        const ly = Math.max(cy - dotRadius - 6, PAD_TOP + 8);
        ctx.fillText(`${label.toUpperCase()}${altStr}`, lx, ly);
      }

      // ── Main sweep line (vertical, bright green) ──────────────────────────────
      if (sweepX >= PAD_LEFT && sweepX <= PAD_LEFT + PLOT_W) {
        ctx.beginPath();
        ctx.moveTo(sweepX, PAD_TOP);
        ctx.lineTo(sweepX, PAD_TOP + PLOT_H);
        ctx.strokeStyle = 'rgba(34, 197, 94, 0.92)';
        ctx.lineWidth = 2;
        ctx.shadowColor = '#22c55e';
        ctx.shadowBlur = 14;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }

      // ── Plot border ───────────────────────────────────────────────────────────
      ctx.strokeStyle = 'rgba(22, 163, 74, 0.35)';
      ctx.lineWidth = 1;
      ctx.strokeRect(PAD_LEFT, PAD_TOP, PLOT_W, PLOT_H);

      // ── Header label ─────────────────────────────────────────────────────────
      ctx.font = 'bold 9px monospace';
      ctx.fillStyle = '#16a34a';
      ctx.textAlign = 'left';
      ctx.fillText('RHI — RANGE / HEIGHT INDICATOR', PAD_LEFT, PAD_TOP - 2);

      animRef.current = requestAnimationFrame((ts) => draw(ctx, ts));
    },
    [maxRange, maxAltitude, alignWithPpi]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.fillStyle = '#0b0f19';
    ctx.fillRect(0, 0, W, H);

    animRef.current = requestAnimationFrame((ts) => draw(ctx, ts));

    return () => {
      cancelAnimationFrame(animRef.current);
    };
  }, [draw]);

  return (
    <div className="flex justify-center">
      <canvas
        ref={canvasRef}
        width={W}
        height={H}
        className="w-full max-w-[700px] rounded-lg"
        style={{ filter: 'drop-shadow(0 0 20px rgba(22, 163, 74, 0.2))' }}
      />
    </div>
  );
}
