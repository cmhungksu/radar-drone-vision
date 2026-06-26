import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { getDatasets, getSamples, getSampleSpectrogram, type DatasetStatus, type SampleList } from '../api';
import SpectrogramPanel from '../components/SpectrogramPanel';

const CLASS_COLORS: Record<string, string> = {
  drone: '#ef4444',
  uav: '#ef4444',
  bird: '#3b82f6',
  human: '#f59e0b',
  default: '#8b5cf6',
};

function getColor(label: string): string {
  const lower = label.toLowerCase();
  for (const [key, color] of Object.entries(CLASS_COLORS)) {
    if (lower.includes(key)) return color;
  }
  return CLASS_COLORS.default;
}

export default function DatasetExplorer() {
  const [page, setPage] = useState(1);
  const [labelFilter, setLabelFilter] = useState<string>('');
  const [selectedSampleId, setSelectedSampleId] = useState<string | null>(null);
  const pageSize = 20;

  const { data: datasets } = useQuery<DatasetStatus[]>({
    queryKey: ['datasets'],
    queryFn: getDatasets,
  });

  const { data: sampleList, isLoading: samplesLoading } = useQuery<SampleList>({
    queryKey: ['samples', page, labelFilter],
    queryFn: () => getSamples('zenodo_77ghz', page, pageSize, labelFilter || undefined),
  });

  const { data: spectrogramUrl } = useQuery<string>({
    queryKey: ['spectrogram', selectedSampleId],
    queryFn: () => getSampleSpectrogram(selectedSampleId!),
    enabled: !!selectedSampleId,
  });

  const ds = datasets?.[0];
  const classDist = ds?.class_distribution ?? {};
  const chartData = Object.entries(classDist)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);

  const samples = sampleList?.samples ?? [];
  const totalSamples = sampleList?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalSamples / pageSize));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-wide">DATASET EXPLORER</h2>
        <p className="text-sm text-slate-500 mt-1">
          Browse and analyze radar micro-Doppler samples
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Class distribution chart */}
        <div className="card">
          <h3 className="card-header">Class Distribution</h3>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                  angle={-35}
                  textAnchor="end"
                  height={60}
                />
                <YAxis
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: 8,
                    color: '#e2e8f0',
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry) => (
                    <Cell key={entry.name} fill={getColor(entry.name)} fillOpacity={0.8} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
              No dataset loaded. Use Dashboard to prepare dataset.
            </div>
          )}
        </div>

        {/* Spectrogram preview */}
        <div className="card">
          <h3 className="card-header">
            Spectrogram Preview
            {selectedSampleId && (
              <span className="ml-2 text-green-400 normal-case font-mono">{selectedSampleId}</span>
            )}
          </h3>
          {selectedSampleId && spectrogramUrl ? (
            <SpectrogramPanel imageData={spectrogramUrl} title="Micro-Doppler Spectrogram" />
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-500 text-sm border border-dashed border-slate-700 rounded-lg">
              Select a sample from the table below to preview its spectrogram
            </div>
          )}
        </div>
      </div>

      {/* Sample browser */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="card-header mb-0">Sample Browser</h3>
          <div className="flex items-center gap-3">
            <select
              value={labelFilter}
              onChange={(e) => {
                setLabelFilter(e.target.value);
                setPage(1);
              }}
              className="bg-slate-800 border border-slate-700 rounded-md text-sm text-slate-300 px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-green-500"
            >
              <option value="">All classes</option>
              {Object.keys(classDist).map((cls) => (
                <option key={cls} value={cls}>
                  {cls}
                </option>
              ))}
            </select>
            <span className="text-xs text-slate-500 font-mono">
              {totalSamples.toLocaleString()} samples
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700/50">
                <th className="table-header">Sample ID</th>
                <th className="table-header">Label</th>
                <th className="table-header">Binary</th>
                <th className="table-header">Radar Type</th>
                <th className="table-header">Freq (GHz)</th>
                <th className="table-header">Shape</th>
                <th className="table-header">Action</th>
              </tr>
            </thead>
            <tbody>
              {samplesLoading ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-slate-500 text-sm">
                    Loading samples...
                  </td>
                </tr>
              ) : samples.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-slate-500 text-sm">
                    No samples found. Prepare the dataset first.
                  </td>
                </tr>
              ) : (
                samples.map((s) => (
                  <tr
                    key={s.sample_id}
                    className={`border-b border-slate-800/50 hover:bg-slate-800/30 cursor-pointer transition-colors ${
                      selectedSampleId === s.sample_id ? 'bg-green-900/10' : ''
                    }`}
                    onClick={() => setSelectedSampleId(s.sample_id)}
                  >
                    <td className="table-cell text-xs text-slate-300">{s.sample_id}</td>
                    <td className="table-cell">
                      <span
                        className="badge"
                        style={{
                          backgroundColor: `${getColor(s.label)}20`,
                          color: getColor(s.label),
                          borderColor: `${getColor(s.label)}40`,
                          borderWidth: 1,
                        }}
                      >
                        {s.label}
                      </span>
                    </td>
                    <td className="table-cell text-slate-400">
                      {s.label_binary === 1 ? (
                        <span className="text-red-400">UAV</span>
                      ) : (
                        <span className="text-blue-400">NON-UAV</span>
                      )}
                    </td>
                    <td className="table-cell text-slate-400">{s.radar_type}</td>
                    <td className="table-cell text-slate-400">
                      {(s.carrier_frequency_hz / 1e9).toFixed(1)}
                    </td>
                    <td className="table-cell text-slate-500 text-xs">
                      {s.raw_shape?.join(' x ') ?? '--'}
                    </td>
                    <td className="table-cell">
                      <button
                        className="text-green-400 hover:text-green-300 text-xs font-medium"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedSampleId(s.sample_id);
                        }}
                      >
                        VIEW
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-800/50">
          <button
            className="btn-secondary text-xs"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
          >
            Previous
          </button>
          <span className="text-xs text-slate-500 font-mono">
            Page {page} of {totalPages}
          </span>
          <button
            className="btn-secondary text-xs"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
