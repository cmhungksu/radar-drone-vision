import { useQuery, useMutation } from '@tanstack/react-query';
import {
  getDatasets,
  getMetrics,
  getLatestInference,
  prepareDataset,
  triggerTraining,
  triggerEvaluation,
  type DatasetStatus,
  type MetricsSummary,
  type InferenceResult,
} from '../api';

function StatCard({
  label,
  value,
  sub,
  color = 'green',
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: 'green' | 'amber' | 'red' | 'blue' | 'cyan';
}) {
  const colorMap = {
    green: 'text-green-400',
    amber: 'text-amber-400',
    red: 'text-red-400',
    blue: 'text-blue-400',
    cyan: 'text-cyan-400',
  };
  return (
    <div className="card">
      <p className="stat-label">{label}</p>
      <p className={`stat-value ${colorMap[color]}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

function ClassDistribution({ dist }: { dist: Record<string, number> }) {
  const total = Object.values(dist).reduce((a, b) => a + b, 0);
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-2">
      {entries.map(([cls, count]) => {
        const pct = total > 0 ? (count / total) * 100 : 0;
        const isUAV = cls.toLowerCase().includes('drone') || cls.toLowerCase().includes('uav');
        return (
          <div key={cls}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-slate-300">{cls}</span>
              <span className="text-slate-400 font-mono">
                {count.toLocaleString()} ({pct.toFixed(1)}%)
              </span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${isUAV ? 'bg-red-500' : 'bg-blue-500'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function Dashboard() {
  const { data: datasets } = useQuery<DatasetStatus[]>({
    queryKey: ['datasets'],
    queryFn: getDatasets,
  });

  const { data: metrics } = useQuery<MetricsSummary | null>({
    queryKey: ['metrics'],
    queryFn: () => getMetrics(),
  });

  const { data: latestInference } = useQuery<InferenceResult | null>({
    queryKey: ['latestInference'],
    queryFn: getLatestInference,
  });

  const prepareMut = useMutation({ mutationFn: () => prepareDataset() });
  const trainMut = useMutation({ mutationFn: () => triggerTraining('sra') });
  const evalMut = useMutation({ mutationFn: () => triggerEvaluation('sra') });

  const ds = datasets?.[0];
  const downloaded = ds?.downloaded ?? false;
  const sampleCount = ds?.sample_count ?? 0;
  const classDist = ds?.class_distribution ?? {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-white tracking-wide">OPERATIONAL DASHBOARD</h2>
        <p className="text-sm text-slate-500 mt-1">
          Radar micro-Doppler UAV/bird discrimination platform status
        </p>
      </div>

      {/* Status cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Dataset Status"
          value={downloaded ? 'READY' : 'NOT LOADED'}
          sub={ds?.name ?? 'zenodo_77ghz'}
          color={downloaded ? 'green' : 'amber'}
        />
        <StatCard
          label="Total Samples"
          value={sampleCount.toLocaleString()}
          sub="micro-Doppler recordings"
          color="cyan"
        />
        <StatCard
          label="EER"
          value={metrics?.eer != null ? `${(metrics.eer * 100).toFixed(2)}%` : '--'}
          sub={metrics?.method ?? 'no evaluation yet'}
          color={metrics?.eer != null && metrics.eer < 0.05 ? 'green' : 'amber'}
        />
        <StatCard
          label="FAR @ FRR=1%"
          value={metrics?.far_at_frr_1 != null ? `${(metrics.far_at_frr_1 * 100).toFixed(2)}%` : '--'}
          sub="operational threshold"
          color="blue"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Class distribution */}
        <div className="card lg:col-span-1">
          <h3 className="card-header">Class Distribution</h3>
          {Object.keys(classDist).length > 0 ? (
            <ClassDistribution dist={classDist} />
          ) : (
            <p className="text-sm text-slate-500">No dataset loaded</p>
          )}
        </div>

        {/* Metrics summary */}
        <div className="card lg:col-span-1">
          <h3 className="card-header">Latest Metrics</h3>
          {metrics ? (
            <div className="space-y-3">
              {[
                { label: 'Accuracy', value: metrics.accuracy },
                { label: 'Precision', value: metrics.precision },
                { label: 'Recall', value: metrics.recall },
                { label: 'F1 Score', value: metrics.f1 },
                { label: 'AUC', value: metrics.auc },
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between items-center">
                  <span className="text-sm text-slate-400">{label}</span>
                  <span className="font-mono text-sm text-white">
                    {(value * 100).toFixed(2)}%
                  </span>
                </div>
              ))}
              <div className="pt-2 border-t border-slate-700/50">
                <p className="text-xs text-slate-500">
                  Method: {metrics.method} | Dataset: {metrics.dataset}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Run evaluation to see metrics</p>
          )}
        </div>

        {/* Latest inference */}
        <div className="card lg:col-span-1">
          <h3 className="card-header">Latest Inference</h3>
          {latestInference ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <span
                  className={`text-3xl font-bold font-mono ${
                    latestInference.prediction.toLowerCase().includes('uav') ||
                    latestInference.prediction.toLowerCase().includes('drone')
                      ? 'text-red-400'
                      : 'text-blue-400'
                  }`}
                >
                  {latestInference.prediction.toUpperCase()}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Confidence</span>
                <span className="font-mono text-green-400">
                  {(latestInference.confidence * 100).toFixed(1)}%
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Latency</span>
                <span className="font-mono text-slate-300">
                  {latestInference.latency_ms.toFixed(1)} ms
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Method</span>
                <span className="font-mono text-slate-300">{latestInference.method}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Sample</span>
                <span className="font-mono text-slate-300 text-xs">{latestInference.sample_id}</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">No inference results yet</p>
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card">
        <h3 className="card-header">Quick Actions</h3>
        <div className="flex flex-wrap gap-3">
          <button
            className="btn-primary"
            onClick={() => prepareMut.mutate()}
            disabled={prepareMut.isPending}
          >
            {prepareMut.isPending ? 'Preparing...' : 'Prepare Dataset'}
          </button>
          <button
            className="btn-primary"
            onClick={() => trainMut.mutate()}
            disabled={trainMut.isPending}
          >
            {trainMut.isPending ? 'Training...' : 'Train SRA Model'}
          </button>
          <button
            className="btn-secondary"
            onClick={() => evalMut.mutate()}
            disabled={evalMut.isPending}
          >
            {evalMut.isPending ? 'Evaluating...' : 'Run Evaluation'}
          </button>
        </div>
        {(prepareMut.isSuccess || trainMut.isSuccess || evalMut.isSuccess) && (
          <p className="text-xs text-green-400 mt-2 font-mono">Task submitted successfully</p>
        )}
        {(prepareMut.isError || trainMut.isError || evalMut.isError) && (
          <p className="text-xs text-red-400 mt-2 font-mono">
            Error: API not available. Start the backend first.
          </p>
        )}
      </div>
    </div>
  );
}
