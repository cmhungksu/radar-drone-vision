import { useQuery } from '@tanstack/react-query';
import { getAirspaceTargets, type AirspaceTarget } from '../api';
import AirspaceCanvas from '../components/AirspaceCanvas';

export default function AirspaceView() {
  const { data: targets } = useQuery<AirspaceTarget[]>({
    queryKey: ['airspaceTargets'],
    queryFn: getAirspaceTargets,
    refetchInterval: 2000,
  });

  const targetList = targets ?? [];
  const uavCount = targetList.filter(
    (t) => t.classification.toLowerCase().includes('uav') || t.classification.toLowerCase().includes('drone')
  ).length;
  const birdCount = targetList.filter((t) => t.classification.toLowerCase().includes('bird')).length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-wide">AIRSPACE VIEW</h2>
        <p className="text-sm text-slate-500 mt-1">2D radar sector visualization with target classification</p>
      </div>

      {/* Warning banner */}
      <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-4 py-3 flex items-start gap-3">
        <svg className="w-5 h-5 text-amber-400 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
        <div>
          <p className="text-sm text-amber-300 font-medium">Simulated Coordinates</p>
          <p className="text-xs text-amber-400/70 mt-0.5">
            Dataset does not provide full spatial coordinates. Positions are derived from sample index and available sweep data for visualization purposes only.
          </p>
        </div>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card text-center">
          <p className="stat-label">Total Tracks</p>
          <p className="stat-value text-white">{targetList.length}</p>
        </div>
        <div className="card text-center">
          <p className="stat-label">UAV Targets</p>
          <p className="stat-value text-red-400">{uavCount}</p>
        </div>
        <div className="card text-center">
          <p className="stat-label">Bird Targets</p>
          <p className="stat-value text-blue-400">{birdCount}</p>
        </div>
        <div className="card text-center">
          <p className="stat-label">Other</p>
          <p className="stat-value text-amber-400">{targetList.length - uavCount - birdCount}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Radar canvas */}
        <div className="card lg:col-span-2">
          <h3 className="card-header">Radar Sector</h3>
          <AirspaceCanvas targets={targetList} />
        </div>

        {/* Track table */}
        <div className="card lg:col-span-1">
          <h3 className="card-header">Track Table</h3>
          <div className="overflow-y-auto max-h-[500px] space-y-2">
            {targetList.length === 0 ? (
              <p className="text-sm text-slate-500">No active targets</p>
            ) : (
              targetList.map((t) => {
                const isUAV =
                  t.classification.toLowerCase().includes('uav') ||
                  t.classification.toLowerCase().includes('drone');
                return (
                  <div
                    key={t.track_id}
                    className={`p-3 rounded-md border ${
                      isUAV
                        ? 'border-red-700/40 bg-red-900/10'
                        : 'border-blue-700/40 bg-blue-900/10'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-mono text-xs text-slate-400">{t.track_id}</span>
                      <span
                        className={`badge ${isUAV ? 'badge-red' : 'badge-blue'}`}
                      >
                        {t.classification}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                      <div className="flex justify-between">
                        <span className="text-slate-500">Range</span>
                        <span className="font-mono text-slate-300">{t.range_m.toFixed(0)}m</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Azimuth</span>
                        <span className="font-mono text-slate-300">{t.azimuth_deg.toFixed(1)}&deg;</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Velocity</span>
                        <span className="font-mono text-slate-300">{t.velocity_mps.toFixed(1)} m/s</span>
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
    </div>
  );
}
