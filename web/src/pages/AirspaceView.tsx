import { useState, useRef, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getAirspaceTargets, getLiveReplay, setUavMode, getUavMode, type AirspaceTarget, type LiveReplayResponse, type UavFlightMode } from '../api';
import AirspaceCanvas from '../components/AirspaceCanvas';
import RhiCanvas from '../components/RhiCanvas';

type RadarMode = 'fmcw' | 'aesa' | 'multifunction';

const RADAR_OPTIONS: { value: RadarMode; label: string; desc: string }[] = [
  { value: 'fmcw', label: 'SAAB SIRS-1600', desc: '77GHz FMCW 旋轉雷達 · 120° 扇形' },
  { value: 'aesa', label: 'AN/SPY-6(V)1', desc: 'S-Band 有源相控陣 · 360° 全向' },
  { value: 'multifunction', label: 'EL/M-2084', desc: 'S-Band 多功能雷達 · 360° 電子掃描' },
];

const UAV_MODE_OPTIONS: { value: UavFlightMode; label: string; desc: string }[] = [
  { value: 'outbound',  label: '從雷達站出發', desc: '由中心向外飛出' },
  { value: 'inbound',   label: '從外圍入侵',   desc: '由邊緣向中心逼近' },
  { value: 'swarm',     label: '群飛編隊',     desc: '密集 Boid 群飛行' },
  { value: 'orbit',     label: '巡邏軌道',     desc: '各自繞圓軌道飛行' },
  { value: 'hover',     label: '懸停偵察',     desc: '原地微漂偵察' },
  { value: 'transit',   label: '高速穿越',     desc: '高速直線穿越扇區' },
];

export default function AirspaceView() {
  const [radarMode, setRadarMode] = useState<RadarMode>('fmcw');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [liveEnabled, setLiveEnabled] = useState(true);
  const [uavModePending, setUavModePending] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  }, []);

  const handleUavModeChange = useCallback(async (mode: UavFlightMode) => {
    if (uavModePending) return;
    setUavModePending(true);
    try {
      await setUavMode(mode);
      // Invalidate the uavMode query so the active button reflects the new state
      queryClient.invalidateQueries({ queryKey: ['uavMode'] });
    } catch (err) {
      console.error('Failed to set UAV mode:', err);
    } finally {
      setUavModePending(false);
    }
  }, [uavModePending, queryClient]);

  // WebSocket 即時目標串流（WebSocket 失敗時自動 fallback 到 HTTP polling）
  const [wsTargets, setWsTargets] = useState<AirspaceTarget[]>([]);
  const [wsStats, setWsStats] = useState<{ total: number; uav: number; bird: number; other: number } | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const wsFailCount = useRef(0);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/radar-viz/api/airspace/ws`;

    const connect = () => {
      if (wsFailCount.current >= 3) return; // 3 次失敗後放棄 WS，改用 polling
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        wsFailCount.current = 0;
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string);
          setWsTargets(data.targets ?? []);
          if (data.stats) setWsStats(data.stats);
        } catch {
          // 解析錯誤靜默忽略
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        wsFailCount.current += 1;
        if (wsFailCount.current < 3) setTimeout(connect, 2000);
      };

      ws.onerror = () => { ws.close(); };
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, []);

  // HTTP polling fallback（WebSocket 不可用時啟用）
  const { data: polledTargets } = useQuery<AirspaceTarget[]>({
    queryKey: ['airspaceTargets'],
    queryFn: getAirspaceTargets,
    refetchInterval: 800,
    enabled: !wsConnected,
  });

  // Current UAV flight mode (sync with backend)
  const { data: uavModeData } = useQuery<{ mode: string }>({
    queryKey: ['uavMode'],
    queryFn: getUavMode,
    refetchInterval: 3000,
  });
  const activeUavMode = (uavModeData?.mode ?? 'orbit') as UavFlightMode;

  // Live replay: real Zenodo data + SRA inference
  const { data: liveData } = useQuery<LiveReplayResponse | null>({
    queryKey: ['liveReplay'],
    queryFn: () => getLiveReplay(6),
    refetchInterval: liveEnabled ? 1500 : false,
    enabled: liveEnabled,
  });

  const targetList = wsConnected ? wsTargets : (polledTargets ?? []);
  const uavCount = targetList.filter(
    (t) => t.classification.toLowerCase().includes('uav') || t.classification.toLowerCase().includes('drone')
  ).length;
  const birdCount = targetList.filter((t) => t.classification.toLowerCase().includes('bird')).length;

  const currentRadar = RADAR_OPTIONS.find((r) => r.value === radarMode)!;

  return (
    <div ref={containerRef} className={`space-y-6 ${isFullscreen ? 'bg-[#0b0f19] p-4 overflow-auto' : ''}`}>
      {/* Header with radar selector + fullscreen */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">COMBAT INFORMATION CENTER</h2>
          <p className="text-sm text-slate-500 mt-1">
            {currentRadar.desc} — 點擊 UAV 目標鎖定攔截
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex gap-1">
            {RADAR_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setRadarMode(opt.value)}
                className={`px-3 py-1.5 text-xs font-mono rounded-md border transition-all ${
                  radarMode === opt.value
                    ? 'bg-green-900/50 border-green-500 text-green-400 shadow-[0_0_12px_rgba(34,197,94,0.3)]'
                    : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-500'
                }`}
              >
                {opt.label}
              </button>
            ))}
            <button
              onClick={toggleFullscreen}
              className="px-3 py-1.5 text-xs font-mono rounded-md border border-amber-700/60 bg-amber-900/30 text-amber-400 hover:border-amber-500 hover:shadow-[0_0_12px_rgba(245,158,11,0.3)] transition-all ml-2"
              title="全螢幕 (F11)"
            >
              {isFullscreen ? '✕ EXIT' : '⛶ FULL'}
            </button>
          </div>
          <span className="text-[10px] text-slate-600 font-mono">RADAR SELECT</span>
        </div>
      </div>

      {/* UAV Flight Mode Selector */}
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap gap-1">
          {UAV_MODE_OPTIONS.map((opt) => {
            const isActive = activeUavMode === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => handleUavModeChange(opt.value)}
                disabled={uavModePending}
                title={opt.desc}
                className={`px-3 py-1.5 text-xs font-mono rounded-md border transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                  isActive
                    ? 'bg-amber-900/50 border-amber-500 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.35)]'
                    : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:border-amber-700 hover:text-amber-400'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        <span className="text-[10px] text-slate-600 font-mono">UAV 飛行模式</span>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-5 gap-4">
        <div className="card text-center">
          <p className="stat-label">Total Tracks</p>
          <p className="stat-value text-white">{wsStats?.total ?? targetList.length}</p>
        </div>
        <div className="card text-center">
          <p className="stat-label">UAV Targets</p>
          <p className="stat-value text-red-400">{wsStats?.uav ?? uavCount}</p>
        </div>
        <div className="card text-center">
          <p className="stat-label">Bird Targets</p>
          <p className="stat-value text-blue-400">{wsStats?.bird ?? birdCount}</p>
        </div>
        <div className="card text-center">
          <p className="stat-label">Other</p>
          <p className="stat-value text-amber-400">{wsStats?.other ?? (targetList.length - uavCount - birdCount)}</p>
        </div>
        <div className="card text-center">
          <p className="stat-label">Radar</p>
          <p className="stat-value text-green-400 text-sm">{currentRadar.label}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Radar PPI + RHI stack */}
        <div className="lg:col-span-2 space-y-4">
          <div className="card">
            <h3 className="card-header">
              PPI — Plan Position Indicator
              <span className="text-slate-600 font-normal text-xs ml-2">
                {radarMode === 'fmcw' ? '120° 俯視' : '360° 俯視'}
              </span>
            </h3>
            <AirspaceCanvas
              targets={targetList}
              radarMode={radarMode}
            />
          </div>
          <div className="card">
            <h3 className="card-header">
              RHI — Range Height Indicator
              <span className="text-slate-600 font-normal text-xs ml-2">側視高度剖面</span>
            </h3>
            <RhiCanvas targets={targetList} />
          </div>
        </div>

        {/* Track table */}
        <div className="card lg:col-span-1">
          <h3 className="card-header">Track Table</h3>
          <div className="overflow-y-auto max-h-[780px] space-y-2">
            {targetList.length === 0 ? (
              <p className="text-sm text-slate-500">No active targets</p>
            ) : (
              targetList.map((t) => {
                const isUAV =
                  t.classification.toLowerCase().includes('uav') ||
                  t.classification.toLowerCase().includes('drone');
                const isBird = t.classification.toLowerCase().includes('bird');
                const borderCls = isUAV
                  ? 'border-red-700/40 bg-red-900/10'
                  : isBird
                    ? 'border-blue-700/40 bg-blue-900/10'
                    : 'border-amber-700/40 bg-amber-900/10';
                return (
                  <div key={t.track_id} className={`p-3 rounded-md border ${borderCls}`}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-mono text-xs text-slate-400">{t.track_id}</span>
                      <div className="flex items-center gap-2">
                        {t.label && (
                          <span className="text-xs text-slate-500">{t.label}</span>
                        )}
                        <span className={`badge ${isUAV ? 'badge-red' : isBird ? 'badge-blue' : 'badge-amber'}`}>
                          {t.classification}
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-1 text-xs">
                      <div className="flex justify-between">
                        <span className="text-slate-500">Range</span>
                        <span className="font-mono text-slate-300">{t.range_m.toFixed(0)}m</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Az</span>
                        <span className="font-mono text-slate-300">{t.azimuth_deg.toFixed(1)}°</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Alt</span>
                        <span className="font-mono text-cyan-400">
                          {typeof t.altitude_m === 'number' ? `${Math.round(t.altitude_m)}m` : '---'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Spd</span>
                        <span className="font-mono text-slate-300">{t.velocity_mps.toFixed(1)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">RCS</span>
                        <span className="font-mono text-slate-300">{t.rcs_dbsm?.toFixed(0) ?? '?'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Conf</span>
                        <span className="font-mono text-green-400">
                          {(t.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* ── Live Replay Panel: Real Zenodo Data + SRA Inference ─────────── */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="card-header mb-0">
              即時推論播放 — Zenodo 77GHz 真實資料
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              72,588 筆真實雷達 IQ 訊號 → Complex-Log-FFT 特徵提取 → SRA 分類推論
            </p>
          </div>
          <div className="flex items-center gap-3">
            {liveData?.stats && (
              <div className="flex gap-4 text-xs font-mono">
                <span className="text-slate-400">
                  樣本 {liveData.stats.cursor}/{liveData.stats.dataset_size}
                </span>
                <span className={liveData.stats.accuracy > 0.9 ? 'text-green-400' : 'text-amber-400'}>
                  準確率 {(liveData.stats.accuracy * 100).toFixed(1)}%
                </span>
                <span className="text-slate-400">
                  {liveData.stats.correct}/{liveData.stats.total} correct
                </span>
              </div>
            )}
            <button
              onClick={() => setLiveEnabled(!liveEnabled)}
              className={`px-4 py-2 text-xs font-mono font-bold rounded-md border transition-all ${
                liveEnabled
                  ? 'border-green-500 bg-green-900/50 text-green-400 shadow-[0_0_12px_rgba(34,197,94,0.3)] animate-pulse'
                  : 'border-slate-600 bg-slate-800/50 text-slate-400 hover:border-green-600'
              }`}
            >
              {liveEnabled ? '⏸ PAUSE' : '▶ START LIVE'}
            </button>
          </div>
        </div>

        {liveData?.samples && liveData.samples.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {liveData.samples.map((s) => (
              <div
                key={s.sample_id}
                className={`p-3 rounded-lg border ${
                  s.predicted_correct
                    ? 'border-green-800/50 bg-green-950/20'
                    : 'border-red-800/50 bg-red-950/20'
                }`}
              >
                {/* Spectrogram */}
                <div className="mb-2 rounded overflow-hidden bg-black">
                  <img
                    src={`data:image/png;base64,${s.spectrogram_b64}`}
                    alt={s.true_label}
                    className="w-full h-auto"
                  />
                </div>
                {/* Results */}
                <div className="space-y-1">
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-slate-500">真實</span>
                    <span className={`text-xs font-mono font-bold ${
                      s.true_is_uav ? 'text-red-400' : 'text-blue-400'
                    }`}>
                      {s.true_label}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-slate-500">推論</span>
                    <span className={`text-xs font-mono font-bold ${
                      s.predicted === 'UAV' ? 'text-red-400' : 'text-blue-400'
                    }`}>
                      {s.predicted}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-slate-500">信心</span>
                    <span className="text-xs font-mono text-green-400">
                      {(s.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-slate-500">距離</span>
                    <span className="text-xs font-mono text-slate-300">
                      {s.range_m.toFixed(0)}m
                    </span>
                  </div>
                  {/* Correct/Wrong badge */}
                  <div className={`text-center text-[10px] font-bold rounded px-1 py-0.5 ${
                    s.predicted_correct
                      ? 'bg-green-900/50 text-green-400'
                      : 'bg-red-900/50 text-red-400'
                  }`}>
                    {s.predicted_correct ? '✓ CORRECT' : '✗ WRONG'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="h-32 flex items-center justify-center text-slate-500 text-sm">
            {liveEnabled ? '載入真實雷達資料 + SRA 推論中...' : '點擊 START LIVE 開始播放 72,588 筆真實雷達訊號的即時推論'}
          </div>
        )}
      </div>
    </div>
  );
}
