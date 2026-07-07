import { useRef, useEffect, useCallback, useState } from 'react';
import { type AirspaceTarget } from '../api';

interface AirspaceCanvasProps {
  targets: AirspaceTarget[];
  maxRange?: number;
  sectorAngle?: number;
  radarMode?: 'fmcw' | 'aesa' | 'multifunction';
  onEngage?: (trackId: string) => void;
}

// Per-target sweep state tracked in the animation loop
interface TargetSweepState {
  track_id: string;
  lastSweepTime: number; // ms timestamp when sweep last crossed this target
}

// Intercept system state
interface InterceptState {
  mode: 'ready' | 'locked' | 'missile' | 'debris';
  lockedTrackId: string | null;
  missilePos: { range_m: number; azimuth_deg: number } | null;
  missileStartTime: number | null;
  missileTargetRange: number;
  missileTargetAzimuth: number;
  debrisParticles: DebrisParticle[];
  destroyedIds: Set<string>;
  kills: number;
  statusText: string;
  statusColor: string;
  statusTimeout: number | null;
  autoEngage: boolean;          // 禁空令：自動攔截所有 UAV
  autoEngageCooldown: number;   // 上次自動發射時間（避免同時多發）
}

interface DebrisParticle {
  range_m: number;
  azimuth_deg: number;
  altitude_m: number;
  vr: number; // radial velocity m/s
  vaz: number; // azimuthal velocity deg/s
  rcs: number;
  birth: number; // timestamp
  sweepCount: number; // how many sweeps have crossed this
  lastSweepTime: number;
}

// Radar model definitions
const RADAR_MODELS = {
  fmcw: {
    name: 'SAAB SIRS-1600',
    band: '77GHz FMCW',
    sectorAngle: 120,   // degrees
    hasSweepLine: true,
    sweepPeriodMs: 4000,
    targetPersistent: false, // targets only visible when swept
  },
  aesa: {
    name: 'AN/SPY-6(V)1',
    band: 'S-Band AESA',
    sectorAngle: 360,
    hasSweepLine: false,  // electronically scanned, no mechanical sweep
    sweepPeriodMs: 0,
    targetPersistent: true, // all targets always visible (phased array)
  },
  multifunction: {
    name: 'EL/M-2084',
    band: 'S-Band MF',
    sectorAngle: 360,
    hasSweepLine: true,   // fast electronic rotation
    sweepPeriodMs: 2000,  // much faster sweep (electronic)
    targetPersistent: false,
  },
};

// Canvas constants (module-level to avoid hook dependency churn)
const W = 700;
const H = 520;
const CX = W / 2;
const CY = H - 50;
const RADIUS = H - 90;

// Timing constants
const FLASH_DURATION_MS = 200;   // bright classification color
const FADE_DURATION_MS = 4000;   // fade from flash to nearly invisible
const SWEEP_PERIOD_MS = 4000;    // full sector sweep duration (FMCW default)

// Missile constants
const MISSILE_SPEED_MPS = 800;
const MISSILE_DOT_RADIUS = 8;
const MISSILE_STREAK_COUNT = 6;

// Classification colors [r, g, b]
function classColor(classification: string): [number, number, number] {
  const c = classification.toLowerCase();
  if (c.includes('uav') || c.includes('drone')) return [239, 68, 68];   // red
  if (c.includes('bird')) return [59, 130, 246];                         // blue
  if (c.includes('human') || c.includes('person')) return [245, 158, 11]; // amber
  return [59, 130, 246]; // default blue
}

// Parse hex color "#rrggbb" → [r, g, b]
function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return null;
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
}

// Get target color: pixel_color (swarm light show) > classification color
function targetColor(t: AirspaceTarget): [number, number, number] {
  const pc = (t as unknown as Record<string, unknown>).pixel_color;
  if (typeof pc === 'string') {
    const rgb = hexToRgb(pc);
    if (rgb) return rgb;
  }
  return classColor(t.classification);
}

// Phosphor green
const PHOSPHOR: [number, number, number] = [34, 197, 94];

function polarToXY(
  range_m: number,
  azimuth_deg: number,
  maxRange: number,
  rcx: number = CX,
  rcy: number = CY,
  rRadius: number = RADIUS,
): { x: number; y: number } {
  const norm = Math.min(range_m / maxRange, 1);
  const r = norm * rRadius;
  const azRad = (azimuth_deg * Math.PI) / 180 - Math.PI / 2;
  return { x: rcx + r * Math.cos(azRad), y: rcy + r * Math.sin(azRad) };
}

// Map rcs_dbsm (-30 to 0) to dot radius (2 to 7)
function rcsToRadius(rcs: number | null): number {
  if (rcs === null) return 3;
  const clamped = Math.max(-30, Math.min(0, rcs));
  return 2 + ((clamped + 30) / 30) * 5;
}

// Wrap azimuth angle to sector
function azimuthToAngle(azimuth_deg: number): number {
  return (azimuth_deg * Math.PI) / 180 - Math.PI / 2;
}

// Shortest angular difference in degrees
function angleDiffDeg(from: number, to: number): number {
  let diff = to - from;
  while (diff > 180) diff -= 360;
  while (diff < -180) diff += 360;
  return diff;
}

// Normalize radian angle to [-PI, PI]
function normalizeAngle(a: number): number {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
}

// Check if sweep (going from prevSweep to sweep) crossed tgtAngle
// Works for both sector and full-circle modes
function sweepCrossed(prevSweep: number, currentSweep: number, tgtAngle: number, is360: boolean): boolean {
  if (is360) {
    // For 360° mode, sweep wraps around. Normalize everything.
    const prev = normalizeAngle(prevSweep);
    const curr = normalizeAngle(currentSweep);
    const tgt = normalizeAngle(tgtAngle);

    // Did we wrap around?
    if (curr >= prev) {
      // No wrap: simple range check
      return prev <= tgt && tgt <= curr;
    } else {
      // Wrapped: target is crossed if it's >= prev OR <= curr
      return tgt >= prev || tgt <= curr;
    }
  } else {
    // Sector mode: simple range check
    return prevSweep <= tgtAngle && tgtAngle <= currentSweep;
  }
}

// ─── Audio Engine (Web Audio API — cinematic sound for presentation) ────────
class RadarAudio {
  private ctx: AudioContext | null = null;
  private _muted = false;
  private lockNodes: AudioNode[] = [];

  get muted() { return this._muted; }
  set muted(v: boolean) { this._muted = v; if (v) this.stopLockAlarm(); }

  private ensureCtx(): AudioContext {
    if (!this.ctx) this.ctx = new AudioContext();
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

  private makeNoise(ctx: AudioContext, duration: number, volume: number): AudioBufferSourceNode {
    const len = Math.floor(ctx.sampleRate * duration);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * volume;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    return src;
  }

  /** Crisp radar detection ping — dual-tone with metallic ring */
  beepDetection() {
    if (this._muted) return;
    const ctx = this.ensureCtx();
    const t = ctx.currentTime;
    // Primary ping
    const o1 = ctx.createOscillator();
    o1.type = 'sine'; o1.frequency.value = 1200;
    const g1 = ctx.createGain();
    g1.gain.setValueAtTime(0.2, t);
    g1.gain.exponentialRampToValueAtTime(0.001, t + 0.08);
    o1.connect(g1).connect(ctx.destination);
    o1.start(t); o1.stop(t + 0.08);
    // Metallic harmonic
    const o2 = ctx.createOscillator();
    o2.type = 'sine'; o2.frequency.value = 2400;
    const g2 = ctx.createGain();
    g2.gain.setValueAtTime(0.06, t);
    g2.gain.exponentialRampToValueAtTime(0.001, t + 0.06);
    o2.connect(g2).connect(ctx.destination);
    o2.start(t); o2.stop(t + 0.06);
  }

  /** Urgent lock alarm — rising two-tone siren with vibrato */
  startLockAlarm() {
    if (this._muted) return;
    this.stopLockAlarm();
    const ctx = this.ensureCtx();
    const duration = 8;

    // Tone 1: 900Hz square wave
    const o1 = ctx.createOscillator();
    o1.type = 'square'; o1.frequency.value = 900;
    // Tone 2: 1400Hz square wave
    const o2 = ctx.createOscillator();
    o2.type = 'square'; o2.frequency.value = 1400;
    // Vibrato LFO on both
    const lfo = ctx.createOscillator();
    lfo.type = 'sine'; lfo.frequency.value = 4; // 4Hz vibrato
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = 30; // ±30Hz wobble
    lfo.connect(lfoGain);
    lfoGain.connect(o1.frequency);
    lfoGain.connect(o2.frequency);

    // Alternating on/off gain — two-tone siren
    const masterGain = ctx.createGain();
    masterGain.gain.value = 0;
    const onTime = 0.12;
    const offTime = 0.08;
    const period = (onTime + offTime) * 2; // two tones per cycle
    for (let t = 0; t < duration; t += period) {
      // Tone 1 on
      masterGain.gain.setValueAtTime(0.18, ctx.currentTime + t);
      masterGain.gain.setValueAtTime(0, ctx.currentTime + t + onTime);
      // Tone 2 on (higher)
      masterGain.gain.setValueAtTime(0.22, ctx.currentTime + t + onTime + offTime);
      masterGain.gain.setValueAtTime(0, ctx.currentTime + t + onTime + offTime + onTime);
    }

    const filter = ctx.createBiquadFilter();
    filter.type = 'bandpass'; filter.frequency.value = 1200; filter.Q.value = 2;

    o1.connect(masterGain);
    o2.connect(masterGain);
    masterGain.connect(filter).connect(ctx.destination);
    lfo.start(ctx.currentTime);
    o1.start(ctx.currentTime); o1.stop(ctx.currentTime + duration);
    o2.start(ctx.currentTime); o2.stop(ctx.currentTime + duration);
    lfo.stop(ctx.currentTime + duration);

    this.lockNodes = [o1, o2, lfo, masterGain, filter, lfoGain];
  }

  stopLockAlarm() {
    for (const n of this.lockNodes) {
      try { if ('stop' in n && typeof n.stop === 'function') (n as OscillatorNode).stop(); } catch { /**/ }
      try { n.disconnect(); } catch { /**/ }
    }
    this.lockNodes = [];
  }

  /** Missile launch — deep bass rumble + rocket whoosh + sub-bass thud */
  playLaunch() {
    if (this._muted) return;
    const ctx = this.ensureCtx();
    const t = ctx.currentTime;

    // Layer 1: Sub-bass thud (60Hz)
    const sub = ctx.createOscillator();
    sub.type = 'sine'; sub.frequency.value = 60;
    sub.frequency.exponentialRampToValueAtTime(30, t + 0.8);
    const subG = ctx.createGain();
    subG.gain.setValueAtTime(0.4, t);
    subG.gain.exponentialRampToValueAtTime(0.001, t + 0.8);
    sub.connect(subG).connect(ctx.destination);
    sub.start(t); sub.stop(t + 0.8);

    // Layer 2: Mid rumble (150Hz sawtooth through lowpass)
    const mid = ctx.createOscillator();
    mid.type = 'sawtooth'; mid.frequency.value = 150;
    mid.frequency.exponentialRampToValueAtTime(80, t + 1.0);
    const midFilt = ctx.createBiquadFilter();
    midFilt.type = 'lowpass'; midFilt.frequency.value = 300;
    const midG = ctx.createGain();
    midG.gain.setValueAtTime(0.25, t);
    midG.gain.exponentialRampToValueAtTime(0.001, t + 1.0);
    mid.connect(midFilt).connect(midG).connect(ctx.destination);
    mid.start(t); mid.stop(t + 1.0);

    // Layer 3: Rocket whoosh (filtered noise, rising pitch)
    const whoosh = this.makeNoise(ctx, 1.2, 0.8);
    const whooshFilt = ctx.createBiquadFilter();
    whooshFilt.type = 'bandpass'; whooshFilt.frequency.value = 400;
    whooshFilt.frequency.exponentialRampToValueAtTime(2000, t + 0.6);
    whooshFilt.Q.value = 1.5;
    const whooshG = ctx.createGain();
    whooshG.gain.setValueAtTime(0, t);
    whooshG.gain.linearRampToValueAtTime(0.3, t + 0.15);
    whooshG.gain.exponentialRampToValueAtTime(0.001, t + 1.2);
    whoosh.connect(whooshFilt).connect(whooshG).connect(ctx.destination);
    whoosh.start(t);

    // Layer 4: Click/snap transient
    const snap = ctx.createOscillator();
    snap.type = 'square'; snap.frequency.value = 3000;
    const snapG = ctx.createGain();
    snapG.gain.setValueAtTime(0.15, t);
    snapG.gain.exponentialRampToValueAtTime(0.001, t + 0.02);
    snap.connect(snapG).connect(ctx.destination);
    snap.start(t); snap.stop(t + 0.02);
  }

  /** Impact explosion — layered boom + debris rattle + pressure wave */
  playImpact() {
    if (this._muted) return;
    const ctx = this.ensureCtx();
    const t = ctx.currentTime;

    // Layer 1: Pressure wave (very low freq sweep)
    const boom = ctx.createOscillator();
    boom.type = 'sine'; boom.frequency.value = 80;
    boom.frequency.exponentialRampToValueAtTime(20, t + 0.6);
    const boomG = ctx.createGain();
    boomG.gain.setValueAtTime(0.5, t);
    boomG.gain.exponentialRampToValueAtTime(0.001, t + 0.6);
    boom.connect(boomG).connect(ctx.destination);
    boom.start(t); boom.stop(t + 0.6);

    // Layer 2: Explosion noise burst (broadband)
    const explNoise = this.makeNoise(ctx, 0.4, 1.0);
    const explFilt = ctx.createBiquadFilter();
    explFilt.type = 'lowpass'; explFilt.frequency.value = 3000;
    explFilt.frequency.exponentialRampToValueAtTime(200, t + 0.4);
    const explG = ctx.createGain();
    explG.gain.setValueAtTime(0.35, t);
    explG.gain.exponentialRampToValueAtTime(0.001, t + 0.4);
    explNoise.connect(explFilt).connect(explG).connect(ctx.destination);
    explNoise.start(t);

    // Layer 3: Metallic debris rattle (delayed, higher freq noise bursts)
    for (let i = 0; i < 4; i++) {
      const delay = 0.1 + i * 0.08 + Math.random() * 0.05;
      const debrisNoise = this.makeNoise(ctx, 0.06, 0.5);
      const debrisFilt = ctx.createBiquadFilter();
      debrisFilt.type = 'bandpass';
      debrisFilt.frequency.value = 2000 + Math.random() * 3000;
      debrisFilt.Q.value = 5;
      const debrisG = ctx.createGain();
      debrisG.gain.setValueAtTime(0, t + delay);
      debrisG.gain.linearRampToValueAtTime(0.1, t + delay + 0.005);
      debrisG.gain.exponentialRampToValueAtTime(0.001, t + delay + 0.06);
      debrisNoise.connect(debrisFilt).connect(debrisG).connect(ctx.destination);
      debrisNoise.start(t + delay);
    }

    // Layer 4: Low crackle tail
    const tail = this.makeNoise(ctx, 0.8, 0.6);
    const tailFilt = ctx.createBiquadFilter();
    tailFilt.type = 'lowpass'; tailFilt.frequency.value = 800;
    const tailG = ctx.createGain();
    tailG.gain.setValueAtTime(0, t + 0.15);
    tailG.gain.linearRampToValueAtTime(0.12, t + 0.25);
    tailG.gain.exponentialRampToValueAtTime(0.001, t + 0.8);
    tail.connect(tailFilt).connect(tailG).connect(ctx.destination);
    tail.start(t + 0.15);
  }
}

export default function AirspaceCanvas({
  targets,
  maxRange = 500,
  sectorAngle = 120,
  radarMode = 'fmcw',
  onEngage,
}: AirspaceCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const targetsRef = useRef<AirspaceTarget[]>(targets);
  const sweepStateRef = useRef<Map<string, TargetSweepState>>(new Map());
  const animRef = useRef<number>(0);
  const prevTimestampRef = useRef<number | null>(null);
  // Track last beep time for AESA mode (beep on data update, not sweep)
  const lastBeepTimeRef = useRef<number>(0);

  // Intercept system state
  const interceptRef = useRef<InterceptState>({
    mode: 'ready',
    lockedTrackId: null,
    missilePos: null,
    missileStartTime: null,
    missileTargetRange: 0,
    missileTargetAzimuth: 0,
    debrisParticles: [],
    destroyedIds: new Set(),
    kills: 0,
    statusText: 'READY',
    statusColor: '#22c55e',
    statusTimeout: null,
    autoEngage: false,
    autoEngageCooldown: 0,
  });

  // Audio engine (single instance, created lazily on first interaction)
  const audioRef = useRef<RadarAudio | null>(null);
  const muteRef = useRef(false);
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [autoEngageOn, setAutoEngageOn] = useState(false);

  // Get radar model config
  const model = RADAR_MODELS[radarMode];
  const is360 = model.sectorAngle === 360;

  // Effective sector angle (use model's sector, not prop, for mode-specific rendering)
  const effectiveSectorAngle = is360 ? 360 : sectorAngle;

  // Sweep angle in radians, starts at left boundary
  const halfAngle = (effectiveSectorAngle / 2) * (Math.PI / 180);
  const leftAngle = is360 ? -Math.PI : -Math.PI / 2 - halfAngle;
  const rightAngle = is360 ? Math.PI : -Math.PI / 2 + halfAngle;
  const sweepAngleRef = useRef<number>(leftAngle);

  // Mode-aware fade duration
  const modeFadeDurationMs = model.sweepPeriodMs > 0 ? model.sweepPeriodMs : FADE_DURATION_MS;
  const modeSweepPeriodMs = model.sweepPeriodMs > 0 ? model.sweepPeriodMs : SWEEP_PERIOD_MS;

  // Keep targets ref in sync without restarting animation
  useEffect(() => {
    targetsRef.current = targets;
  }, [targets]);

  // ─── Click handler ──────────────────────────────────────────────────────────
  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      // Initialize audio on first click (browser autoplay policy)
      if (!audioRef.current) {
        audioRef.current = new RadarAudio();
      }

      // Compute mode-aware geometry for hit testing
      const rcx = is360 ? W / 2 : CX;
      const rcy = is360 ? H / 2 : CY;
      const rRadius = is360 ? Math.min(W, H) / 2 - 45 : RADIUS;

      // Map click pixel to canvas coords accounting for CSS scaling
      const rect = canvas.getBoundingClientRect();
      const scaleX = W / rect.width;
      const scaleY = H / rect.height;
      const cx = (e.clientX - rect.left) * scaleX;
      const cy = (e.clientY - rect.top) * scaleY;

      const state = interceptRef.current;
      const tgts = targetsRef.current;

      // Find nearest UAV target within 20px
      let nearestDist = Infinity;
      let nearestTarget: AirspaceTarget | null = null;
      for (const t of tgts) {
        // Skip destroyed targets
        if (state.destroyedIds.has(t.track_id)) continue;
        // Only engage UAV targets
        const c = t.classification.toLowerCase();
        if (!c.includes('uav') && !c.includes('drone')) continue;

        const pos = polarToXY(t.range_m, t.azimuth_deg, maxRange, rcx, rcy, rRadius);
        const dist = Math.sqrt((pos.x - cx) ** 2 + (pos.y - cy) ** 2);
        if (dist < 20 && dist < nearestDist) {
          nearestDist = dist;
          nearestTarget = t;
        }
      }

      if (state.mode === 'ready') {
        if (nearestTarget) {
          // Lock on
          state.mode = 'locked';
          state.lockedTrackId = nearestTarget.track_id;
          state.statusText = `LOCKED: ${nearestTarget.label ?? nearestTarget.track_id}`;
          state.statusColor = '#ef4444';
          state.statusTimeout = null;
          audioRef.current?.startLockAlarm();
        }
      } else if (state.mode === 'locked') {
        if (nearestTarget && nearestTarget.track_id === state.lockedTrackId) {
          // Second click on same target → fire missile
          audioRef.current?.stopLockAlarm();
          audioRef.current?.playLaunch();

          state.mode = 'missile';
          state.missilePos = { range_m: 0, azimuth_deg: nearestTarget.azimuth_deg };
          state.missileStartTime = performance.now();
          state.missileTargetRange = nearestTarget.range_m;
          state.missileTargetAzimuth = nearestTarget.azimuth_deg;
          state.statusText = 'MISSILE IN FLIGHT';
          state.statusColor = '#f59e0b';
          state.statusTimeout = null;

          onEngage?.(nearestTarget.track_id);
        } else {
          // Click elsewhere → cancel lock
          audioRef.current?.stopLockAlarm();
          state.mode = 'ready';
          state.lockedTrackId = null;
          state.statusText = 'READY';
          state.statusColor = '#22c55e';
          state.statusTimeout = null;
        }
      }
      // In missile or debris mode, clicks are ignored
    },
    [maxRange, onEngage, is360]
  );

  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, timestamp: number) => {
      // --- Mode-aware geometry ---
      const rcx = is360 ? W / 2 : CX;
      const rcy = is360 ? H / 2 : CY;
      const rRadius = is360 ? Math.min(W, H) / 2 - 45 : RADIUS;

      // --- Delta time (capped at 100ms to handle tab-switch stutter) ---
      const prev = prevTimestampRef.current ?? timestamp;
      const dtSec = Math.min((timestamp - prev) / 1000, 0.1);
      prevTimestampRef.current = timestamp;

      const state = interceptRef.current;
      const now = timestamp;
      const tgts = targetsRef.current.filter(t => !state.destroyedIds.has(t.track_id));

      // --- Advance sweep (only if this mode has a sweep line) ---
      if (model.hasSweepLine && modeSweepPeriodMs > 0) {
        const totalAngle = is360 ? 2 * Math.PI : 2 * halfAngle;
        const sweepSpeed = totalAngle / (modeSweepPeriodMs / 1000);
        let sweep = sweepAngleRef.current + sweepSpeed * dtSec;
        if (is360) {
          if (sweep > Math.PI) {
            sweep = -Math.PI;
          }
        } else {
          if (sweep > rightAngle) {
            sweep = leftAngle;
          }
        }
        sweepAngleRef.current = sweep;

        // --- Detect sweep crossing each target and record time ---
        const prevSweep = sweep - sweepSpeed * dtSec;
        for (const t of tgts) {
          const tgtAngle = azimuthToAngle(t.azimuth_deg);
          if (sweepCrossed(prevSweep, sweep, tgtAngle, is360)) {
            sweepStateRef.current.set(t.track_id, {
              track_id: t.track_id,
              lastSweepTime: now,
            });
            // Audio: beep for UAV targets
            const c = t.classification.toLowerCase();
            if (c.includes('uav') || c.includes('drone')) {
              audioRef.current?.beepDetection();
              // 禁空令：自動攔截 — sweep 偵測到 UAV 時自動鎖定+發射
              if (state.autoEngage && state.mode === 'ready'
                  && !state.destroyedIds.has(t.track_id)
                  && now - state.autoEngageCooldown > 2000) {
                state.mode = 'missile';
                state.lockedTrackId = t.track_id;
                state.missilePos = { range_m: 0, azimuth_deg: t.azimuth_deg };
                state.missileStartTime = now;
                state.missileTargetRange = t.range_m;
                state.missileTargetAzimuth = t.azimuth_deg;
                state.autoEngageCooldown = now;
                state.statusText = `AUTO ENGAGE: ${t.label ?? t.track_id}`;
                state.statusColor = '#ef4444';
                audioRef.current?.playLaunch();
              }
            }
          }
        }

        // --- Sweep crossing for debris particles ---
        for (const dp of state.debrisParticles) {
          const dpAngle = azimuthToAngle(dp.azimuth_deg);
          if (sweepCrossed(prevSweep, sweep, dpAngle, is360)) {
            dp.lastSweepTime = now;
            dp.sweepCount++;
          }
        }
      } else if (model.targetPersistent) {
        // AESA mode: no sweep line, but we still need to update sweep states
        // for consistent rendering. Mark all targets as "always swept".
        for (const t of tgts) {
          sweepStateRef.current.set(t.track_id, {
            track_id: t.track_id,
            lastSweepTime: now,
          });
        }
        // Also mark debris as swept
        for (const dp of state.debrisParticles) {
          dp.lastSweepTime = now;
          // Don't increment sweepCount every frame; only periodically
          if (now - dp.birth > 500 * (dp.sweepCount + 1)) {
            dp.sweepCount++;
          }
        }

        // AESA beep: beep when UAV target data updates (throttled to every 500ms)
        if (now - lastBeepTimeRef.current > 500) {
          for (const t of tgts) {
            const c = t.classification.toLowerCase();
            if (c.includes('uav') || c.includes('drone')) {
              audioRef.current?.beepDetection();
              lastBeepTimeRef.current = now;
              break; // one beep per interval
            }
          }
        }
      }

      const sweep = sweepAngleRef.current;

      // --- Update missile position ---
      if (state.mode === 'missile' && state.missilePos && state.missileStartTime !== null) {
        const elapsed = (now - state.missileStartTime) / 1000; // seconds
        const missileRange = MISSILE_SPEED_MPS * elapsed;
        const flightFrac = Math.min(1, missileRange / state.missileTargetRange);

        // Interpolate azimuth toward target
        const startAz = state.missilePos.azimuth_deg;
        const targetAz = state.missileTargetAzimuth;

        // Update locked target position if target still exists
        const lockedTarget = targetsRef.current.find(t => t.track_id === state.lockedTrackId);
        if (lockedTarget) {
          state.missileTargetRange = lockedTarget.range_m;
          state.missileTargetAzimuth = lockedTarget.azimuth_deg;
        }

        const currentAz = startAz + angleDiffDeg(startAz, targetAz) * flightFrac;
        state.missilePos = { range_m: missileRange, azimuth_deg: currentAz };

        // Check impact
        const rangeToTarget = Math.abs(missileRange - state.missileTargetRange);
        if (rangeToTarget < 10 || flightFrac >= 1) {
          // IMPACT
          audioRef.current?.playImpact();

          const impactRange = state.missileTargetRange;
          const impactAz = state.missileTargetAzimuth;
          const impactAlt = lockedTarget?.altitude_m ?? 100;

          // Create debris
          const debrisCount = 5 + Math.floor(Math.random() * 4); // 5-8
          state.debrisParticles = [];
          for (let i = 0; i < debrisCount; i++) {
            state.debrisParticles.push({
              range_m: impactRange + (Math.random() - 0.5) * 20,
              azimuth_deg: impactAz + (Math.random() - 0.5) * 8,
              altitude_m: impactAlt,
              vr: (Math.random() - 0.5) * 30, // -15 to 15 m/s
              vaz: (Math.random() - 0.5) * 4, // deg/s scatter
              rcs: -25 + Math.random() * 10, // -25 to -15 dBsm
              birth: now,
              sweepCount: 0,
              lastSweepTime: 0,
            });
          }

          // Destroy original target
          if (state.lockedTrackId) {
            state.destroyedIds.add(state.lockedTrackId);
            state.kills++;
          }

          state.mode = 'debris';
          state.missilePos = null;
          state.missileStartTime = null;
          state.lockedTrackId = null;
          state.statusText = 'TARGET DESTROYED';
          state.statusColor = '#22c55e';
          // Revert to READY after 3 seconds
          state.statusTimeout = now + 3000;
        }
      }

      // --- Update debris particles ---
      if (state.mode === 'debris') {
        for (const dp of state.debrisParticles) {
          dp.range_m += dp.vr * dtSec;
          dp.azimuth_deg += dp.vaz * dtSec;
          dp.altitude_m -= 9.8 * dtSec * 3; // falling fast
        }
        // Remove debris that has been swept 4+ times or fallen below 0 altitude
        state.debrisParticles = state.debrisParticles.filter(
          dp => dp.sweepCount < 4 && dp.altitude_m > 0 && dp.range_m > 0
        );
        // If all debris gone, revert
        if (state.debrisParticles.length === 0) {
          if (state.statusTimeout === null) {
            state.statusTimeout = now + 1000;
          }
        }
        // Check status timeout
        if (state.statusTimeout !== null && now >= state.statusTimeout) {
          state.mode = 'ready';
          state.statusText = 'READY';
          state.statusColor = '#22c55e';
          state.statusTimeout = null;
        }
      }

      // Also check status timeout in any mode
      if (state.statusTimeout !== null && now >= state.statusTimeout && state.mode !== 'missile') {
        state.mode = 'ready';
        state.statusText = 'READY';
        state.statusColor = '#22c55e';
        state.statusTimeout = null;
      }

      // --- Full clear each frame ---
      ctx.fillStyle = '#0b0f19';
      ctx.fillRect(0, 0, W, H);

      // --- Sector / Circle background ---
      ctx.save();
      ctx.beginPath();
      if (is360) {
        ctx.arc(rcx, rcy, rRadius, 0, Math.PI * 2);
      } else {
        ctx.moveTo(rcx, rcy);
        ctx.arc(rcx, rcy, rRadius, leftAngle, rightAngle);
        ctx.closePath();
      }
      ctx.fillStyle = 'rgba(22, 163, 74, 0.03)';
      ctx.fill();
      ctx.restore();

      // --- Range rings ---
      const numRings = 5;
      for (let i = 1; i <= numRings; i++) {
        const r = (i / numRings) * rRadius;
        ctx.save();
        ctx.beginPath();
        if (is360) {
          ctx.arc(rcx, rcy, r, 0, Math.PI * 2);
        } else {
          ctx.arc(rcx, rcy, r, leftAngle, rightAngle);
        }
        ctx.strokeStyle = 'rgba(22, 163, 74, 0.15)';
        ctx.lineWidth = 0.5;
        ctx.stroke();
        // Range label
        if (is360) {
          // Place label at 0° (right side)
          const lx = rcx + r + 2;
          const ly = rcy + 3;
          ctx.font = '9px monospace';
          ctx.fillStyle = '#334155';
          ctx.textAlign = 'left';
          ctx.fillText(`${((i / numRings) * maxRange).toFixed(0)}m`, lx, ly);
        } else {
          const labelAngle = rightAngle + 0.06;
          const lx = rcx + r * Math.cos(labelAngle);
          const ly = rcy + r * Math.sin(labelAngle);
          ctx.font = '9px monospace';
          ctx.fillStyle = '#334155';
          ctx.textAlign = 'left';
          ctx.fillText(`${((i / numRings) * maxRange).toFixed(0)}m`, lx + 2, ly + 3);
        }
        ctx.restore();
      }

      // --- Azimuth spoke lines ---
      ctx.setLineDash([3, 5]);
      ctx.lineWidth = 0.5;
      if (is360) {
        // Full circle: every 30°
        for (let deg = 0; deg < 360; deg += 30) {
          const azRad = (deg * Math.PI) / 180 - Math.PI / 2;
          const ex = rcx + rRadius * Math.cos(azRad);
          const ey = rcy + rRadius * Math.sin(azRad);
          ctx.beginPath();
          ctx.moveTo(rcx, rcy);
          ctx.lineTo(ex, ey);
          ctx.strokeStyle = 'rgba(22, 163, 74, 0.08)';
          ctx.stroke();
          // Label
          ctx.font = '9px monospace';
          ctx.fillStyle = '#475569';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          const labelR = rRadius + 12;
          const llx = rcx + labelR * Math.cos(azRad);
          const lly = rcy + labelR * Math.sin(azRad);
          ctx.fillText(`${deg}°`, llx, lly);
        }
        ctx.textBaseline = 'alphabetic';
      } else {
        for (const deg of [-60, -30, 0, 30, 60]) {
          const azRad = (deg * Math.PI) / 180 - Math.PI / 2;
          const ex = rcx + rRadius * Math.cos(azRad);
          const ey = rcy + rRadius * Math.sin(azRad);
          ctx.beginPath();
          ctx.moveTo(rcx, rcy);
          ctx.lineTo(ex, ey);
          ctx.strokeStyle = 'rgba(22, 163, 74, 0.08)';
          ctx.stroke();
          // Label
          ctx.font = '9px monospace';
          ctx.fillStyle = '#475569';
          ctx.textAlign = 'center';
          const ox = deg < 0 ? -14 : deg > 0 ? 14 : 0;
          ctx.fillText(`${deg}°`, ex + ox, ey - 6);
        }
      }
      ctx.setLineDash([]);

      // --- Sector boundary lines (only for sector modes) ---
      if (!is360) {
        ctx.beginPath();
        ctx.moveTo(rcx, rcy);
        ctx.lineTo(rcx + rRadius * Math.cos(leftAngle), rcy + rRadius * Math.sin(leftAngle));
        ctx.strokeStyle = 'rgba(22, 163, 74, 0.35)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(rcx, rcy);
        ctx.lineTo(rcx + rRadius * Math.cos(rightAngle), rcy + rRadius * Math.sin(rightAngle));
        ctx.stroke();
      }

      // --- Flock connections (before targets, behind everything) ---
      const flockGroups = new Map<string, AirspaceTarget[]>();
      for (const t of tgts) {
        if (t.flock_id) {
          const g = flockGroups.get(t.flock_id) ?? [];
          g.push(t);
          flockGroups.set(t.flock_id, g);
        }
      }
      for (const [, members] of flockGroups) {
        if (members.length < 2) continue;
        let lineAlpha: number;
        if (model.targetPersistent) {
          // AESA: flock connections always visible
          lineAlpha = 0.3;
        } else {
          const anyRecent = members.some((m) => {
            const st = sweepStateRef.current.get(m.track_id);
            if (!st) return false;
            return now - st.lastSweepTime < modeFadeDurationMs;
          });
          if (!anyRecent) continue;

          const maxAge = Math.max(
            ...members.map((m) => {
              const st = sweepStateRef.current.get(m.track_id);
              return st ? now - st.lastSweepTime : Infinity;
            })
          );
          lineAlpha = Math.max(0, 1 - maxAge / modeFadeDurationMs) * 0.3;
        }

        for (let i = 0; i < members.length - 1; i++) {
          const a = polarToXY(members[i].range_m, members[i].azimuth_deg, maxRange, rcx, rcy, rRadius);
          const b = polarToXY(members[i + 1].range_m, members[i + 1].azimuth_deg, maxRange, rcx, rcy, rRadius);
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = `rgba(${PHOSPHOR.join(',')}, ${lineAlpha})`;
          ctx.lineWidth = 0.8;
          ctx.setLineDash([4, 4]);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }

      // --- Targets ---
      for (const t of tgts) {
        const pos = polarToXY(t.range_m, t.azimuth_deg, maxRange, rcx, rcy, rRadius);
        const st = sweepStateRef.current.get(t.track_id);
        const timeSinceSweep = st ? now - st.lastSweepTime : Infinity;

        const dotRadius = rcsToRadius(t.rcs_dbsm ?? null);
        const [cr, cg, cb] = targetColor(t);

        // --- Determine rendering mode based on radar model ---
        let mainColor: [number, number, number];
        let mainAlpha: number;
        let glowRadius: number;
        let glowAlpha: number;
        let showLabel: boolean;

        if (model.targetPersistent) {
          // AESA mode: targets always visible in classification color
          // Skip if never updated (shouldn't happen in AESA mode, but safety check)
          if (!st) continue;

          let pulseMod = 1;
          if (t.micro_doppler_hz && t.micro_doppler_hz > 0) {
            const pulseRate = t.micro_doppler_hz * 2 * Math.PI;
            pulseMod = 0.9 + 0.1 * Math.sin(now * pulseRate * 0.001);
          }

          // Steady glow in classification color
          mainColor = [cr, cg, cb];
          mainAlpha = 0.8 * t.confidence * pulseMod;
          glowRadius = dotRadius * 2.5;
          glowAlpha = 0.3 * t.confidence * pulseMod;
          showLabel = true;
        } else {
          // Sweep-based modes (FMCW, Multifunction): flash-on-sweep, then fade

          // Skip if never swept (completely invisible)
          if (!st) continue;

          if (timeSinceSweep < FLASH_DURATION_MS) {
            const flashFrac = timeSinceSweep / FLASH_DURATION_MS;
            const brightnessBoost = (1 - flashFrac) * t.confidence;

            let pulseMod = 1;
            if (t.micro_doppler_hz && t.micro_doppler_hz > 0) {
              const pulseRate = t.micro_doppler_hz * 2 * Math.PI;
              pulseMod = 0.75 + 0.25 * Math.sin(now * pulseRate * 0.001);
            }

            mainColor = [cr, cg, cb];
            mainAlpha = (0.7 + 0.3 * brightnessBoost) * pulseMod;
            glowRadius = dotRadius * 3.5;
            glowAlpha = 0.5 * brightnessBoost * pulseMod;
            showLabel = true;
          } else if (timeSinceSweep < modeFadeDurationMs) {
            const fadeFrac = (timeSinceSweep - FLASH_DURATION_MS) / (modeFadeDurationMs - FLASH_DURATION_MS);
            const t01 = Math.min(1, fadeFrac);

            const r2 = Math.round(cr + (PHOSPHOR[0] - cr) * t01);
            const g2 = Math.round(cg + (PHOSPHOR[1] - cg) * t01);
            const b2 = Math.round(cb + (PHOSPHOR[2] - cb) * t01);
            mainColor = [r2, g2, b2];

            mainAlpha = 0.8 * (1 - t01 * 0.94);
            glowRadius = dotRadius * 2;
            glowAlpha = mainAlpha * 0.3;
            showLabel = timeSinceSweep < 1000;
          } else {
            continue;
          }
        }

        // --- Trail ---
        if (t.trail && t.trail.length > 0) {
          let trailVisible: boolean;
          let trailFade: number;

          if (model.targetPersistent) {
            // AESA: trail always visible
            trailVisible = true;
            trailFade = 0.8;
          } else {
            trailVisible = timeSinceSweep < modeFadeDurationMs;
            trailFade = Math.max(0, 1 - timeSinceSweep / modeFadeDurationMs);
          }

          if (trailVisible && trailFade > 0.01) {
            const velocityScale = Math.min(1, t.velocity_mps / 20);
            const effectiveTrailCount = Math.max(
              1,
              Math.round(t.trail.length * (0.3 + velocityScale * 0.7))
            );
            const visibleTrail = t.trail.slice(-effectiveTrailCount);

            for (let i = 0; i < visibleTrail.length; i++) {
              const tp = polarToXY(visibleTrail[i].range_m, visibleTrail[i].azimuth_deg, maxRange, rcx, rcy, rRadius);
              const ageFrac = (i + 1) / visibleTrail.length;
              const dotAlpha = ageFrac * 0.4 * trailFade;
              if (dotAlpha < 0.01) continue;
              ctx.beginPath();
              ctx.arc(tp.x, tp.y, 1.2, 0, Math.PI * 2);
              ctx.fillStyle = `rgba(${PHOSPHOR.join(',')}, ${dotAlpha})`;
              ctx.fill();
            }
            if (visibleTrail.length > 1) {
              ctx.beginPath();
              const first = polarToXY(visibleTrail[0].range_m, visibleTrail[0].azimuth_deg, maxRange, rcx, rcy, rRadius);
              ctx.moveTo(first.x, first.y);
              for (let i = 1; i < visibleTrail.length; i++) {
                const tp = polarToXY(visibleTrail[i].range_m, visibleTrail[i].azimuth_deg, maxRange, rcx, rcy, rRadius);
                ctx.lineTo(tp.x, tp.y);
              }
              ctx.lineTo(pos.x, pos.y);
              ctx.strokeStyle = `rgba(${PHOSPHOR.join(',')}, ${0.15 * trailFade})`;
              ctx.lineWidth = 0.8;
              ctx.stroke();
            }
          }
        }

        // Glow halo
        if (glowAlpha > 0.01) {
          const gradient = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, glowRadius);
          gradient.addColorStop(0, `rgba(${mainColor.join(',')}, ${glowAlpha})`);
          gradient.addColorStop(1, `rgba(${mainColor.join(',')}, 0)`);
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, glowRadius, 0, Math.PI * 2);
          ctx.fillStyle = gradient;
          ctx.fill();
        }

        // Main dot
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, dotRadius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${mainColor.join(',')}, ${mainAlpha})`;
        ctx.shadowColor = `rgb(${mainColor.join(',')})`;
        ctx.shadowBlur = model.targetPersistent ? 6 : (timeSinceSweep < FLASH_DURATION_MS ? 12 : 4);
        ctx.fill();
        ctx.shadowBlur = 0;

        // Bright specular center
        if (model.targetPersistent) {
          // AESA: subtle steady specular
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, Math.max(1, dotRadius * 0.35), 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255, 255, 255, 0.3)`;
          ctx.fill();
        } else if (timeSinceSweep < FLASH_DURATION_MS + 100) {
          const specAlpha = Math.max(0, 1 - timeSinceSweep / (FLASH_DURATION_MS + 100));
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, Math.max(1, dotRadius * 0.35), 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255, 255, 255, ${specAlpha * 0.9})`;
          ctx.fill();
        }

        // --- Label with altitude ---
        if (showLabel) {
          let labelAlpha: number;
          if (model.targetPersistent) {
            labelAlpha = mainAlpha;
          } else {
            labelAlpha =
              timeSinceSweep < FLASH_DURATION_MS
                ? mainAlpha
                : Math.max(0, 1 - (timeSinceSweep - FLASH_DURATION_MS) / (1000 - FLASH_DURATION_MS));
          }

          if (labelAlpha > 0.05) {
            const label = t.label ?? t.track_id;
            const altStr = typeof t.altitude_m === 'number' ? ` ▲${Math.round(t.altitude_m)}m` : '';
            ctx.font = 'bold 8px monospace';
            ctx.fillStyle = `rgba(${mainColor.join(',')}, ${labelAlpha})`;
            ctx.textAlign = 'left';
            ctx.fillText(`${label.toUpperCase()}${altStr}`, pos.x + dotRadius + 4, pos.y - 3);
            ctx.font = '7px monospace';
            ctx.fillStyle = `rgba(100, 116, 139, ${labelAlpha * 0.85})`;
            ctx.fillText(`${t.velocity_mps.toFixed(1)} m/s`, pos.x + dotRadius + 4, pos.y + 7);
          }
        }

        // --- Targeting reticle for locked target ---
        if (state.mode === 'locked' && t.track_id === state.lockedTrackId) {
          drawTargetingReticle(ctx, pos, t, now, maxRange);
        }
      }

      // --- Missile rendering ---
      if (state.mode === 'missile' && state.missilePos) {
        drawMissile(ctx, state, now, maxRange, sweep, rcx, rcy, rRadius);
      }

      // --- Debris rendering ---
      if (state.debrisParticles.length > 0) {
        drawDebris(ctx, state, now, maxRange, model.targetPersistent, modeFadeDurationMs, rcx, rcy, rRadius);
      }

      // --- Sweep trail (rendered OVER targets, as the actual sweep line) ---
      if (model.hasSweepLine) {
        const isMF = radarMode === 'multifunction';
        const sweepColor = isMF ? [6, 182, 212] : [34, 197, 94]; // cyan for MF, green for FMCW
        const sweepLineWidth = isMF ? 1.5 : 2;
        const sweepShadowColor = isMF ? '#06b6d4' : '#22c55e';

        // Sweep gradient trail — wide, bright, unmistakable
        const trailSpanRad = (35 * Math.PI) / 180; // 35° wide trail
        const trailSteps = 60;

        // Draw as filled wedge slices for a solid glow effect
        for (let i = 0; i < trailSteps; i++) {
          const frac = i / trailSteps; // 0 = at sweep front, 1 = oldest
          const angle0 = sweep - trailSpanRad * frac;
          const angle1 = sweep - trailSpanRad * (frac + 1 / trailSteps);
          if (!is360 && angle1 < leftAngle) continue;
          // Cubic falloff for more dramatic gradient
          const alpha = 0.32 * (1 - frac) * (1 - frac) * (1 - frac);
          if (alpha < 0.003) continue;
          ctx.beginPath();
          ctx.moveTo(rcx, rcy);
          ctx.arc(rcx, rcy, rRadius, angle1, angle0);
          ctx.closePath();
          ctx.fillStyle = `rgba(${sweepColor.join(',')}, ${alpha})`;
          ctx.fill();
        }

        // Bright inner glow near sweep line (narrower, brighter)
        for (let i = 0; i < 12; i++) {
          const frac = i / 12;
          const angle0 = sweep - (8 * Math.PI / 180) * frac;
          const angle1 = sweep - (8 * Math.PI / 180) * (frac + 1 / 12);
          if (!is360 && angle1 < leftAngle) continue;
          const alpha = 0.15 * (1 - frac);
          ctx.beginPath();
          ctx.moveTo(rcx, rcy);
          ctx.arc(rcx, rcy, rRadius, angle1, angle0);
          ctx.closePath();
          ctx.fillStyle = `rgba(${sweepColor.join(',')}, ${alpha})`;
          ctx.fill();
        }

        // Main sweep line — thick, glowing
        const sweepEndX = rcx + rRadius * Math.cos(sweep);
        const sweepEndY = rcy + rRadius * Math.sin(sweep);
        ctx.beginPath();
        ctx.moveTo(rcx, rcy);
        ctx.lineTo(sweepEndX, sweepEndY);
        ctx.strokeStyle = `rgba(${sweepColor.join(',')}, 0.95)`;
        ctx.lineWidth = sweepLineWidth + 1;
        ctx.shadowColor = sweepShadowColor;
        ctx.shadowBlur = 20;
        ctx.stroke();
        // Second pass for extra glow
        ctx.lineWidth = sweepLineWidth;
        ctx.strokeStyle = `rgba(255, 255, 255, 0.4)`;
        ctx.shadowBlur = 8;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }

      // --- Radar origin dot ---
      ctx.beginPath();
      ctx.arc(rcx, rcy, 5, 0, Math.PI * 2);
      ctx.fillStyle = '#16a34a';
      ctx.shadowColor = '#22c55e';
      ctx.shadowBlur = 10;
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.beginPath();
      ctx.arc(rcx, rcy, 2, 0, Math.PI * 2);
      ctx.fillStyle = '#22c55e';
      ctx.fill();
      ctx.font = '9px monospace';
      ctx.fillStyle = '#16a34a';
      ctx.textAlign = 'center';
      ctx.fillText('RADAR', rcx, rcy + 18);

      // --- Radar model label (top-left corner) ---
      {
        const mlx = 12;
        const mly = 12;
        const modelName = model.name;
        const bandAngle = `${model.band}  ${model.sectorAngle}°`;

        // Measure text to size the box
        ctx.font = 'bold 11px monospace';
        const nameWidth = ctx.measureText(modelName).width;
        ctx.font = '9px monospace';
        const bandWidth = ctx.measureText(bandAngle).width;
        const boxW = Math.max(nameWidth, bandWidth) + 16;
        const boxH = 36;

        // Background
        ctx.fillStyle = 'rgba(11, 15, 25, 0.88)';
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(mlx, mly, boxW, boxH, 4);
        ctx.fill();
        ctx.stroke();

        // Model name (white, bold)
        ctx.font = 'bold 11px monospace';
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'left';
        ctx.fillText(modelName, mlx + 8, mly + 15);

        // Band + angle (green)
        ctx.font = '9px monospace';
        ctx.fillStyle = '#22c55e';
        ctx.fillText(bandAngle, mlx + 8, mly + 29);
      }

      // --- Legend ---
      const lx = W - 134;
      const ly = 12;
      ctx.fillStyle = 'rgba(11, 15, 25, 0.92)';
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(lx, ly, 122, 72, 4);
      ctx.fill();
      ctx.stroke();

      const legendEntries: [string, [number, number, number]][] = [
        ['UAV / Drone', [239, 68, 68]],
        ['Bird', [59, 130, 246]],
        ['Human', [245, 158, 11]],
      ];
      legendEntries.forEach(([label, color], idx) => {
        const ey2 = ly + 18 + idx * 18;
        ctx.beginPath();
        ctx.arc(lx + 14, ey2, 4, 0, Math.PI * 2);
        ctx.fillStyle = `rgb(${color.join(',')})`;
        ctx.shadowColor = `rgb(${color.join(',')})`;
        ctx.shadowBlur = 6;
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.font = '9px monospace';
        ctx.fillStyle = '#94a3b8';
        ctx.textAlign = 'left';
        ctx.fillText(label, lx + 26, ey2 + 4);
      });

      // --- Status HUD (bottom of canvas) ---
      drawStatusHUD(ctx, state, rcx);

      // --- Mute indicator ---
      if (muteRef.current) {
        ctx.font = '9px monospace';
        ctx.fillStyle = '#64748b';
        ctx.textAlign = 'left';
        ctx.fillText('🔇 MUTED', 12, 62);
      }

      animRef.current = requestAnimationFrame((ts) => draw(ctx, ts));
    },
    [halfAngle, leftAngle, rightAngle, maxRange, is360, model, modeFadeDurationMs, modeSweepPeriodMs, radarMode]
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
      audioRef.current?.stopLockAlarm();
    };
  }, [draw]);

  // Toggle mute with 'M' key
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'm' || e.key === 'M') {
        muteRef.current = !muteRef.current;
        if (audioRef.current) {
          audioRef.current.muted = muteRef.current;
        }
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  // Ensure audio is initialized on any interaction
  const initAudio = useCallback(() => {
    if (!audioRef.current) {
      audioRef.current = new RadarAudio();
      setAudioEnabled(true);
      // Play a test beep so user knows audio is working
      audioRef.current.beepDetection();
    }
  }, []);

  return (
    <div className="flex flex-col items-center gap-2">
      <canvas
        ref={canvasRef}
        width={W}
        height={H}
        onClick={handleCanvasClick}
        onPointerDown={initAudio}
        className="w-full max-w-[700px] rounded-lg cursor-crosshair"
        style={{ filter: 'drop-shadow(0 0 25px rgba(22, 163, 74, 0.2))' }}
      />
      <div className="flex items-center gap-3">
        {!audioEnabled && (
          <button
            onClick={initAudio}
            className="px-4 py-2 text-xs font-mono rounded-md border border-green-600 bg-green-900/40 text-green-400 hover:bg-green-800/50 hover:shadow-[0_0_15px_rgba(34,197,94,0.4)] transition-all animate-pulse"
          >
            🔊 啟用音效
          </button>
        )}
        <button
          onClick={() => {
            initAudio();
            const s = interceptRef.current;
            s.autoEngage = !s.autoEngage;
            setAutoEngageOn(s.autoEngage);
            if (s.autoEngage) {
              s.statusText = '⚠ 禁空令生效 — AUTO ENGAGE';
              s.statusColor = '#ef4444';
            } else {
              s.statusText = 'READY';
              s.statusColor = '#22c55e';
            }
          }}
          className={`px-4 py-2 text-xs font-mono font-bold rounded-md border transition-all ${
            autoEngageOn
              ? 'border-red-500 bg-red-900/60 text-red-300 shadow-[0_0_20px_rgba(239,68,68,0.5)] animate-pulse'
              : 'border-red-800 bg-red-950/30 text-red-500 hover:border-red-600 hover:bg-red-900/40'
          }`}
        >
          {autoEngageOn ? '🚨 禁空令執行中 — 點擊解除' : '🚀 發布禁空令'}
        </button>
      </div>
      <div className="flex gap-4 text-[10px] font-mono text-slate-600">
        <span>CLICK UAV to lock → CLICK again to fire</span>
        <span>禁空令 = 掃到 UAV 自動攔截</span>
        <span>M = mute</span>
      </div>
    </div>
  );
}

// ─── Drawing helpers (outside component to keep draw() cleaner) ─────────────

function drawTargetingReticle(
  ctx: CanvasRenderingContext2D,
  pos: { x: number; y: number },
  target: AirspaceTarget,
  now: number,
  _maxRange: number
) {
  const pulse = 0.5 + 0.5 * Math.sin(now * 0.008); // pulsing 0-1
  const size = 18 + pulse * 6;
  const alpha = 0.6 + pulse * 0.4;

  ctx.save();
  ctx.strokeStyle = `rgba(239, 68, 68, ${alpha})`;
  ctx.lineWidth = 1.5;

  // Corner brackets
  const half = size;
  const arm = size * 0.35;
  // Top-left
  ctx.beginPath();
  ctx.moveTo(pos.x - half, pos.y - half + arm);
  ctx.lineTo(pos.x - half, pos.y - half);
  ctx.lineTo(pos.x - half + arm, pos.y - half);
  ctx.stroke();
  // Top-right
  ctx.beginPath();
  ctx.moveTo(pos.x + half - arm, pos.y - half);
  ctx.lineTo(pos.x + half, pos.y - half);
  ctx.lineTo(pos.x + half, pos.y - half + arm);
  ctx.stroke();
  // Bottom-right
  ctx.beginPath();
  ctx.moveTo(pos.x + half, pos.y + half - arm);
  ctx.lineTo(pos.x + half, pos.y + half);
  ctx.lineTo(pos.x + half - arm, pos.y + half);
  ctx.stroke();
  // Bottom-left
  ctx.beginPath();
  ctx.moveTo(pos.x - half + arm, pos.y + half);
  ctx.lineTo(pos.x - half, pos.y + half);
  ctx.lineTo(pos.x - half, pos.y + half - arm);
  ctx.stroke();

  // Crosshair lines
  ctx.setLineDash([3, 3]);
  ctx.lineWidth = 0.8;
  ctx.strokeStyle = `rgba(239, 68, 68, ${alpha * 0.5})`;
  // Horizontal
  ctx.beginPath();
  ctx.moveTo(pos.x - half - 4, pos.y);
  ctx.lineTo(pos.x - 4, pos.y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(pos.x + 4, pos.y);
  ctx.lineTo(pos.x + half + 4, pos.y);
  ctx.stroke();
  // Vertical
  ctx.beginPath();
  ctx.moveTo(pos.x, pos.y - half - 4);
  ctx.lineTo(pos.x, pos.y - 4);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(pos.x, pos.y + 4);
  ctx.lineTo(pos.x, pos.y + half + 4);
  ctx.stroke();
  ctx.setLineDash([]);

  // Info panel to the right of reticle
  const panelX = pos.x + half + 10;
  const panelY = pos.y - 40;
  const panelW = 130;
  const panelH = 80;

  // Clamp panel position to stay within canvas
  const clampedX = Math.min(panelX, W - panelW - 5);
  const clampedY = Math.max(5, Math.min(panelY, H - panelH - 5));

  ctx.fillStyle = 'rgba(11, 15, 25, 0.9)';
  ctx.strokeStyle = `rgba(239, 68, 68, ${alpha * 0.6})`;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(clampedX, clampedY, panelW, panelH, 3);
  ctx.fill();
  ctx.stroke();

  ctx.font = 'bold 9px monospace';
  ctx.fillStyle = '#ef4444';
  ctx.textAlign = 'left';
  ctx.fillText(`TGT: ${(target.label ?? target.track_id).toUpperCase()}`, clampedX + 6, clampedY + 14);

  ctx.font = '8px monospace';
  ctx.fillStyle = '#94a3b8';
  const altStr = typeof target.altitude_m === 'number' ? `${Math.round(target.altitude_m)}m` : '---';
  const rcsStr = target.rcs_dbsm !== null ? `${target.rcs_dbsm.toFixed(1)} dBsm` : '---';
  ctx.fillText(`RNG: ${target.range_m.toFixed(0)}m`, clampedX + 6, clampedY + 28);
  ctx.fillText(`SPD: ${target.velocity_mps.toFixed(1)} m/s`, clampedX + 6, clampedY + 40);
  ctx.fillText(`ALT: ${altStr}`, clampedX + 6, clampedY + 52);
  ctx.fillText(`RCS: ${rcsStr}`, clampedX + 6, clampedY + 64);
  ctx.fillText(`CNF: ${(target.confidence * 100).toFixed(0)}%`, clampedX + 6, clampedY + 76);

  ctx.restore();
}

function drawMissile(
  ctx: CanvasRenderingContext2D,
  state: InterceptState,
  now: number,
  maxRange: number,
  sweep: number,
  rcx: number,
  rcy: number,
  rRadius: number,
) {
  if (!state.missilePos) return;

  const missileAngle = azimuthToAngle(state.missilePos.azimuth_deg);

  // Missile streak: render multiple positions along the flight path
  const elapsed = state.missileStartTime ? (now - state.missileStartTime) / 1000 : 0;

  for (let s = 0; s < MISSILE_STREAK_COUNT; s++) {
    const streakTime = elapsed - s * 0.03; // 30ms between streak dots
    if (streakTime < 0) continue;
    const streakRange = MISSILE_SPEED_MPS * streakTime;
    if (streakRange > maxRange) continue;

    const streakAz = state.missilePos.azimuth_deg;

    const pos = polarToXY(streakRange, streakAz, maxRange, rcx, rcy, rRadius);

    // Streak dot visibility
    const streakAlpha = (1 - s / MISSILE_STREAK_COUNT) * 0.9;

    const sweepDist = Math.abs(missileAngle - sweep);
    const recentlySwept = sweepDist < 0.3 || elapsed < 0.5;

    if (!recentlySwept && s > 0) continue;

    // Bright return
    const gradient = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, MISSILE_DOT_RADIUS * 2);
    gradient.addColorStop(0, `rgba(255, 200, 50, ${streakAlpha * 0.5})`);
    gradient.addColorStop(1, `rgba(255, 100, 0, 0)`);
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, MISSILE_DOT_RADIUS * 2, 0, Math.PI * 2);
    ctx.fillStyle = gradient;
    ctx.fill();

    // Core dot
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, MISSILE_DOT_RADIUS * (1 - s * 0.1), 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 220, 100, ${streakAlpha})`;
    ctx.shadowColor = '#ffcc00';
    ctx.shadowBlur = 15;
    ctx.fill();
    ctx.shadowBlur = 0;

    // White specular on head
    if (s === 0) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255, 255, 255, 0.95)`;
      ctx.fill();
    }
  }
}

function drawDebris(
  ctx: CanvasRenderingContext2D,
  state: InterceptState,
  now: number,
  maxRange: number,
  targetPersistent: boolean,
  fadeDurationMs: number,
  rcx: number,
  rcy: number,
  rRadius: number,
) {
  for (const dp of state.debrisParticles) {
    const pos = polarToXY(dp.range_m, dp.azimuth_deg, maxRange, rcx, rcy, rRadius);
    const timeSinceSweep = dp.lastSweepTime > 0 ? now - dp.lastSweepTime : Infinity;

    if (!targetPersistent) {
      // Only visible if swept
      if (dp.lastSweepTime === 0) continue;
      if (timeSinceSweep > fadeDurationMs) continue;
    }

    // Small dots, fading with sweep count
    const sweepFade = Math.max(0, 1 - dp.sweepCount / 4);
    const timeFade = targetPersistent ? sweepFade : Math.max(0, 1 - timeSinceSweep / fadeDurationMs);
    const alpha = sweepFade * timeFade * 0.7;

    if (alpha < 0.02) continue;

    const dotR = rcsToRadius(dp.rcs) * 0.8;

    // Orange-red flash on first sweep, then fading phosphor
    const isFlash = targetPersistent ? (now - dp.birth < 300) : (timeSinceSweep < FLASH_DURATION_MS);
    const color = isFlash ? [255, 150, 50] : PHOSPHOR;

    ctx.beginPath();
    ctx.arc(pos.x, pos.y, dotR, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${color.join(',')}, ${alpha})`;
    ctx.shadowColor = isFlash ? '#ff9900' : `rgb(${PHOSPHOR.join(',')})`;
    ctx.shadowBlur = isFlash ? 8 : 3;
    ctx.fill();
    ctx.shadowBlur = 0;
  }
}

function drawStatusHUD(ctx: CanvasRenderingContext2D, state: InterceptState, rcx: number) {
  const hudY = H - 22;
  const hudH = 22;

  // Background bar
  ctx.fillStyle = 'rgba(11, 15, 25, 0.85)';
  ctx.fillRect(0, hudY, W, hudH);
  ctx.strokeStyle = '#1e293b';
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  ctx.moveTo(0, hudY);
  ctx.lineTo(W, hudY);
  ctx.stroke();

  // Left: status text
  ctx.font = 'bold 11px monospace';
  ctx.fillStyle = state.statusColor;
  ctx.textAlign = 'left';
  ctx.fillText(`● ${state.statusText}`, 12, hudY + 15);

  // Right: kill counter + auto-engage indicator
  ctx.font = 'bold 11px monospace';
  ctx.fillStyle = state.kills > 0 ? '#22c55e' : '#64748b';
  ctx.textAlign = 'right';
  const killText = `KILLS: ${state.kills}`;
  const autoText = state.autoEngage ? '  ⚠ 禁空令' : '';
  if (state.autoEngage) {
    // Flashing red "禁空令" text
    const flash = Math.sin(Date.now() * 0.006) > 0;
    ctx.fillText(killText, W - 100, hudY + 15);
    ctx.fillStyle = flash ? '#ef4444' : '#991b1b';
    ctx.fillText('⚠ 禁空令', W - 12, hudY + 15);
  } else {
    ctx.fillText(killText + autoText, W - 12, hudY + 15);
  }

  // Center: instructions
  const hudCx = W / 2;
  ctx.font = '9px monospace';
  ctx.fillStyle = '#475569';
  ctx.textAlign = 'center';
  if (state.autoEngage) {
    ctx.fillStyle = '#ef4444';
    ctx.fillText('AUTO ENGAGE — ALL UAV TARGETS WILL BE DESTROYED', hudCx, hudY + 15);
  } else if (state.mode === 'ready') {
    ctx.fillText('CLICK UAV TO LOCK', hudCx, hudY + 15);
  } else if (state.mode === 'locked') {
    ctx.fillText('CLICK AGAIN TO FIRE | CLICK ELSEWHERE TO CANCEL', hudCx, hudY + 15);
  } else if (state.mode === 'missile') {
    ctx.fillText('TRACKING...', hudCx, hudY + 15);
  }
}
