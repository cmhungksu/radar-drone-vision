import { useState, useCallback, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

const API = '/radar-viz/api/drone-show';

interface BayDrone {
  bay_id: string; drone_id: string; battery_percent: number;
  health: string; role: string; charging: boolean;
}

export default function CarrierStation() {
  const [launchResult, setLaunchResult] = useState<Record<string, unknown> | null>(null);
  const [recoveryResult, setRecoveryResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState('');
  const [droneCount, setDroneCount] = useState(50);

  const { data: inventory, refetch: refetchInventory } = useQuery({
    queryKey: ['carrierInventory'],
    queryFn: async () => {
      const res = await fetch(`${API}/carrier/inventory`);
      return res.json();
    },
    refetchInterval: 5000,
  });

  const handlePlanLaunch = useCallback(async () => {
    setLoading('launching');
    try {
      const res = await fetch(`${API}/carrier/plan-launch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ drone_count: droneCount }),
      });
      setLaunchResult(await res.json());
    } catch (err) { console.error(err); }
    setLoading('');
  }, [droneCount]);

  const handlePlanRecovery = useCallback(async () => {
    setLoading('recovering');
    try {
      const res = await fetch(`${API}/carrier/plan-recovery`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      setRecoveryResult(await res.json());
    } catch (err) { console.error(err); }
    setLoading('');
  }, []);

  const handleCharge = useCallback(async (minutes: number) => {
    setLoading('charging');
    try {
      await fetch(`${API}/carrier/simulate-charging`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes }),
      });
      refetchInventory();
    } catch (err) { console.error(err); }
    setLoading('');
  }, [refetchInventory]);

  const bays: BayDrone[] = inventory?.drones || [];
  const readyCount = inventory?.ready || 0;
  const launchedCount = inventory?.launched || 0;
  const chargingCount = inventory?.charging || 0;
  const reserveCount = inventory?.reserves || 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-wide">CARRIER LAUNCH STATION</h2>
        <p className="text-sm text-slate-500 mt-1">
          SIMULATION ONLY — 車載航母艙位管理、分批起降排程
        </p>
      </div>

      {/* Carrier status KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="card text-center py-3 glow-green">
          <p className="text-[10px] text-slate-500">Ready</p>
          <p className="text-xl font-bold text-green-400">{readyCount}</p>
        </div>
        <div className="card text-center py-3">
          <p className="text-[10px] text-slate-500">Launched</p>
          <p className="text-xl font-bold text-cyan-400">{launchedCount}</p>
        </div>
        <div className="card text-center py-3">
          <p className="text-[10px] text-slate-500">Charging</p>
          <p className="text-xl font-bold text-amber-400">{chargingCount}</p>
        </div>
        <div className="card text-center py-3">
          <p className="text-[10px] text-slate-500">Reserves</p>
          <p className="text-xl font-bold text-blue-400">{reserveCount}</p>
        </div>
        <div className="card text-center py-3">
          <p className="text-[10px] text-slate-500">Total Bays</p>
          <p className="text-xl font-bold text-slate-300">{bays.length}</p>
        </div>
      </div>

      {/* Bay grid visualization */}
      <div className="card">
        <h3 className="card-header">Bay Inventory ({bays.length} slots)</h3>
        <div className="grid gap-1" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(54px, 1fr))' }}>
          {bays.map(bay => {
            const colors: Record<string, string> = {
              ready: 'bg-green-900/40 border-green-700/40 text-green-400',
              launched: 'bg-cyan-900/40 border-cyan-700/40 text-cyan-400',
              charging: 'bg-amber-900/40 border-amber-700/40 text-amber-400',
              fault: 'bg-red-900/40 border-red-700/40 text-red-400',
              empty: 'bg-slate-800/40 border-slate-700/40 text-slate-500',
            };
            const cls = colors[bay.health] || colors.empty;
            return (
              <div key={bay.bay_id}
                className={`rounded border px-1 py-1.5 text-center text-[8px] font-mono ${cls}`}
                title={`${bay.bay_id}: ${bay.drone_id} (${bay.battery_percent}% ${bay.health})`}>
                <div className="truncate">{bay.drone_id?.slice(-3) || '--'}</div>
                <div className="mt-0.5">
                  <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all"
                      style={{
                        width: `${bay.battery_percent}%`,
                        backgroundColor: bay.battery_percent > 50 ? '#22c55e' : bay.battery_percent > 20 ? '#f59e0b' : '#ef4444',
                      }} />
                  </div>
                </div>
                {bay.role === 'reserve' && <div className="text-[7px] text-blue-400 mt-0.5">RSV</div>}
              </div>
            );
          })}
        </div>
        <div className="flex gap-4 mt-3 text-[9px] text-slate-500">
          <span><span className="inline-block w-2 h-2 rounded bg-green-600 mr-1" />Ready</span>
          <span><span className="inline-block w-2 h-2 rounded bg-cyan-600 mr-1" />Launched</span>
          <span><span className="inline-block w-2 h-2 rounded bg-amber-600 mr-1" />Charging</span>
          <span><span className="inline-block w-2 h-2 rounded bg-red-600 mr-1" />Fault</span>
        </div>
      </div>

      {/* Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card">
          <h3 className="card-header">Launch Planning</h3>
          <label className="text-[10px] text-slate-500 block mb-1">Drones to launch</label>
          <div className="flex gap-2 mb-3">
            {[20, 50, 60].map(n => (
              <button key={n} onClick={() => setDroneCount(n)}
                className={`flex-1 py-1.5 rounded text-xs font-mono border ${
                  droneCount === n ? 'bg-green-900/50 border-green-500 text-green-400' : 'bg-slate-800/50 border-slate-700 text-slate-400'}`}>
                {n}
              </button>
            ))}
          </div>
          <button onClick={handlePlanLaunch} disabled={loading !== ''}
            className="w-full py-2 bg-green-600 text-white rounded text-sm hover:bg-green-500 disabled:opacity-40">
            {loading === 'launching' ? 'Planning...' : 'Plan Launch Schedule'}
          </button>
        </div>

        <div className="card">
          <h3 className="card-header">Recovery</h3>
          <button onClick={handlePlanRecovery} disabled={loading !== ''}
            className="w-full py-2 bg-cyan-600 text-white rounded text-sm hover:bg-cyan-500 disabled:opacity-40 mb-2">
            {loading === 'recovering' ? 'Planning...' : 'Plan Recovery'}
          </button>
          <p className="text-[9px] text-slate-500">Reverse-order staggered landing</p>
        </div>

        <div className="card">
          <h3 className="card-header">Charging</h3>
          <div className="flex gap-2">
            {[10, 20, 30].map(m => (
              <button key={m} onClick={() => handleCharge(m)} disabled={loading === 'charging'}
                className="flex-1 py-2 bg-amber-600 text-white rounded text-sm hover:bg-amber-500 disabled:opacity-40">
                {m}min
              </button>
            ))}
          </div>
          <p className="text-[9px] text-slate-500 mt-1">Simulate battery charging cycle</p>
        </div>
      </div>

      {/* Launch schedule result */}
      {launchResult && (
        <div className="card">
          <h3 className="card-header">Launch Schedule</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
            <div className="text-center">
              <p className="text-[10px] text-slate-500">Drones</p>
              <p className="text-lg font-bold text-green-400">{(launchResult as any).total_drones}</p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500">Waves</p>
              <p className="text-lg font-bold text-cyan-400">{(launchResult as any).total_waves}</p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500">Per Wave</p>
              <p className="text-lg font-bold text-blue-400">{(launchResult as any).drones_per_wave}</p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500">All In Formation</p>
              <p className="text-lg font-bold text-amber-400">{(launchResult as any).all_in_formation_time_sec?.toFixed(1)}s</p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500">Avg Battery</p>
              <p className="text-lg font-bold text-green-400">{(launchResult as any).energy_budget?.avg_battery_at_formation?.toFixed(0)}%</p>
            </div>
          </div>

          {/* Wave timeline visualization */}
          <div className="overflow-x-auto">
            <div className="flex gap-1 pb-2" style={{ minWidth: ((launchResult as any).total_waves || 1) * 60 }}>
              {Array.from({ length: (launchResult as any).total_waves || 0 }, (_, w) => {
                const waveDrones = ((launchResult as any).launch_plan || []).filter((e: any) => e.wave === w + 1);
                return (
                  <div key={w} className="flex-shrink-0 w-14 text-center">
                    <div className="text-[8px] text-slate-500 mb-1">W{w + 1}</div>
                    <div className="space-y-0.5">
                      {waveDrones.map((e: any) => (
                        <div key={e.drone_id} className="text-[7px] font-mono bg-green-900/30 text-green-400 rounded px-1 py-0.5 truncate"
                          title={`${e.drone_id} @ ${e.time_offset_sec}s → ${e.target_wait_zone}`}>
                          {e.drone_id.slice(-3)}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Recovery result */}
      {recoveryResult && (
        <div className="card">
          <h3 className="card-header">Recovery Schedule</h3>
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center">
              <p className="text-[10px] text-slate-500">Drones</p>
              <p className="text-lg font-bold text-cyan-400">{(recoveryResult as any).total_drones}</p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500">Recovery Waves</p>
              <p className="text-lg font-bold text-blue-400">{(recoveryResult as any).total_recovery_waves}</p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500">Total Time</p>
              <p className="text-lg font-bold text-amber-400">{(recoveryResult as any).total_recovery_time_sec?.toFixed(0)}s</p>
            </div>
          </div>
        </div>
      )}

      <div className="text-[10px] text-slate-600 text-center font-mono">
        SIMULATION_ONLY — 車載航母模擬系統，不輸出實機控制指令
      </div>
    </div>
  );
}
