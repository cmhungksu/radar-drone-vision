import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getMetrics, getMethodComparison, getFeatureDimSweep, type MetricsSummary, type MethodComparison, type FeatureDimResult } from '../api';
import ConfusionMatrix from '../components/ConfusionMatrix';
import RocDetChart from '../components/RocDetChart';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const METHODS = [
  { value: 'sra', label: 'Proposed Feature + SRA' },
  { value: 'pca', label: 'Proposed Feature + PCA' },
  { value: 'spectrogram_pca', label: 'Spectrogram + PCA' },
  { value: 'cvd_pca', label: 'CVD + PCA' },
  { value: 'cepstrogram_pca', label: 'Cepstrogram + PCA' },
  { value: 'cnn', label: 'CNN Proposed Feature' },
];

export default function ModelEvaluation() {
  const [selectedMethod, setSelectedMethod] = useState('sra');

  const { data: metrics } = useQuery<MetricsSummary | null>({
    queryKey: ['metrics', selectedMethod],
    queryFn: () => getMetrics(selectedMethod),
  });

  const { data: comparison } = useQuery<MethodComparison[]>({
    queryKey: ['methodComparison'],
    queryFn: getMethodComparison,
  });

  const { data: dimSweep } = useQuery<FeatureDimResult[]>({
    queryKey: ['featureDimSweep'],
    queryFn: getFeatureDimSweep,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">MODEL EVALUATION</h2>
          <p className="text-sm text-slate-500 mt-1">
            Performance analysis and method comparison
          </p>
        </div>
        <select
          value={selectedMethod}
          onChange={(e) => setSelectedMethod(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded-md text-sm text-slate-300 px-3 py-2 focus:outline-none focus:ring-1 focus:ring-green-500"
        >
          {METHODS.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </div>

      {/* EER and FAR highlights */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card text-center glow-green">
          <p className="stat-label">Equal Error Rate</p>
          <p className="stat-value text-green-400">
            {metrics?.eer != null ? `${(metrics.eer * 100).toFixed(2)}%` : '--'}
          </p>
          <p className="text-xs text-slate-500 mt-1">
            threshold: {metrics?.eer_threshold?.toFixed(4) ?? '--'}
          </p>
        </div>
        <div className="card text-center">
          <p className="stat-label">FAR @ FRR=1%</p>
          <p className="stat-value text-amber-400">
            {metrics?.far_at_frr_1 != null ? `${(metrics.far_at_frr_1 * 100).toFixed(2)}%` : '--'}
          </p>
          <p className="text-xs text-slate-500 mt-1">operational metric</p>
        </div>
        <div className="card text-center">
          <p className="stat-label">AUC</p>
          <p className="stat-value text-cyan-400">
            {metrics?.auc != null ? metrics.auc.toFixed(4) : '--'}
          </p>
          <p className="text-xs text-slate-500 mt-1">area under ROC</p>
        </div>
        <div className="card text-center">
          <p className="stat-label">F1 Score</p>
          <p className="stat-value text-blue-400">
            {metrics?.f1 != null ? `${(metrics.f1 * 100).toFixed(2)}%` : '--'}
          </p>
          <p className="text-xs text-slate-500 mt-1">harmonic mean</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Confusion Matrix */}
        <div className="card">
          <h3 className="card-header">Confusion Matrix</h3>
          {metrics?.confusion_matrix && metrics.class_names ? (
            <ConfusionMatrix
              matrix={metrics.confusion_matrix}
              labels={metrics.class_names}
            />
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
              No evaluation data available
            </div>
          )}
        </div>

        {/* ROC Curve */}
        <div className="card">
          <h3 className="card-header">ROC Curve</h3>
          {metrics?.roc_curve ? (
            <RocDetChart
              mode="roc"
              fpr={metrics.roc_curve.fpr}
              tprOrFnr={metrics.roc_curve.tpr}
              auc={metrics.auc}
            />
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
              No evaluation data available
            </div>
          )}
        </div>

        {/* DET Curve */}
        <div className="card">
          <h3 className="card-header">DET Curve</h3>
          {metrics?.det_curve ? (
            <RocDetChart
              mode="det"
              fpr={metrics.det_curve.fpr}
              tprOrFnr={metrics.det_curve.fnr}
            />
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
              No evaluation data available
            </div>
          )}
        </div>

        {/* Feature dimension vs error rate */}
        <div className="card">
          <h3 className="card-header">Feature Dimension vs Error Rate</h3>
          {dimSweep && dimSweep.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={dimSweep} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="dimension"
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                  label={{ value: 'Dimension', position: 'insideBottom', offset: -5, fill: '#64748b', fontSize: 11 }}
                />
                <YAxis
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                  label={{ value: 'Error Rate', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }}
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
                <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                <Line
                  type="monotone"
                  dataKey="eer"
                  name="EER"
                  stroke="#22c55e"
                  strokeWidth={2}
                  dot={{ fill: '#22c55e', r: 3 }}
                />
                <Line
                  type="monotone"
                  dataKey="far_at_frr_1"
                  name="FAR@FRR=1%"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={{ fill: '#f59e0b', r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
              No dimension sweep data available
            </div>
          )}
        </div>
      </div>

      {/* Method comparison table */}
      <div className="card">
        <h3 className="card-header">Method Comparison</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700/50">
                <th className="table-header">Method</th>
                <th className="table-header">Feature</th>
                <th className="table-header">Classifier</th>
                <th className="table-header">Dataset</th>
                <th className="table-header">EER (%)</th>
                <th className="table-header">FAR@FRR=1% (%)</th>
                <th className="table-header">Notes</th>
              </tr>
            </thead>
            <tbody>
              {comparison && comparison.length > 0 ? (
                comparison.map((row, i) => (
                  <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                    <td className="table-cell text-white font-medium text-sm">{row.method}</td>
                    <td className="table-cell text-slate-300">{row.feature}</td>
                    <td className="table-cell text-slate-300">{row.classifier}</td>
                    <td className="table-cell text-slate-400">{row.dataset}</td>
                    <td className="table-cell font-mono text-green-400">
                      {(row.eer * 100).toFixed(2)}
                    </td>
                    <td className="table-cell font-mono text-amber-400">
                      {(row.far_at_frr_1 * 100).toFixed(2)}
                    </td>
                    <td className="table-cell text-slate-500 text-xs">{row.notes}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-slate-500 text-sm">
                    No comparison data available. Run evaluations for multiple methods first.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
