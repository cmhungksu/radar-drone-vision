import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts';
import type { RocComparison } from '../api';

interface RocComparisonChartProps {
  data: RocComparison;
  mode: 'roc' | 'det';
}

export default function RocComparisonChart({ data, mode }: RocComparisonChartProps) {
  const methods = Object.keys(data);

  const chartData = useMemo(() => {
    if (methods.length === 0) return [];

    // Build a unified FPR axis from all methods
    const allFpr = new Set<number>();
    for (const name of methods) {
      const fprArr = mode === 'roc' ? data[name].roc.fpr : data[name].det.fpr;
      for (const v of fprArr) allFpr.add(v);
    }
    const fprSorted = Array.from(allFpr).sort((a, b) => a - b);

    // Downsample to ~300 points
    const step = Math.max(1, Math.floor(fprSorted.length / 300));
    const fprDown = fprSorted.filter((_, i) => i % step === 0);
    if (fprDown[fprDown.length - 1] !== fprSorted[fprSorted.length - 1]) {
      fprDown.push(fprSorted[fprSorted.length - 1]);
    }

    // For each FPR point, find nearest TPR/FNR for each method
    return fprDown.map((fprVal) => {
      const row: Record<string, number> = { fpr: fprVal };
      for (const name of methods) {
        const rocData = data[name].roc;
        const detData = data[name].det;
        const fprArr = mode === 'roc' ? rocData.fpr : detData.fpr;
        const valArr = mode === 'roc' ? rocData.tpr : detData.fnr;
        // Find nearest FPR index
        let bestIdx = 0;
        let bestDist = Infinity;
        for (let i = 0; i < fprArr.length; i++) {
          const d = Math.abs(fprArr[i] - fprVal);
          if (d < bestDist) {
            bestDist = d;
            bestIdx = i;
          }
        }
        row[name] = valArr[bestIdx];
      }
      return row;
    });
  }, [data, methods, mode]);

  if (chartData.length === 0) {
    return (
      <div className="h-80 flex items-center justify-center text-slate-500 text-sm">
        No curve data — run: python scripts/precompute_roc.py
      </div>
    );
  }

  const isRoc = mode === 'roc';
  const yLabel = isRoc ? 'True Positive Rate' : 'False Negative Rate';

  return (
    <div>
      <ResponsiveContainer width="100%" height={380}>
        <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 30 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            dataKey="fpr"
            type="number"
            domain={[0, 1]}
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            axisLine={{ stroke: '#334155' }}
            tickLine={false}
            tickFormatter={(v: number) => v.toFixed(1)}
            label={{
              value: 'False Positive Rate',
              position: 'insideBottom',
              offset: -15,
              fill: '#64748b',
              fontSize: 11,
            }}
          />
          <YAxis
            type="number"
            domain={[0, 1]}
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            axisLine={{ stroke: '#334155' }}
            tickLine={false}
            tickFormatter={(v: number) => v.toFixed(1)}
            label={{
              value: yLabel,
              angle: -90,
              position: 'insideLeft',
              fill: '#64748b',
              fontSize: 11,
            }}
          />
          <Tooltip
            contentStyle={{
              background: '#0f172a',
              border: '1px solid #334155',
              borderRadius: 8,
              color: '#e2e8f0',
              fontSize: 11,
            }}
            formatter={(val: number, name: string) => [
              val.toFixed(4),
              name,
            ]}
            labelFormatter={(val: number) => `FPR: ${Number(val).toFixed(4)}`}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, color: '#94a3b8', paddingTop: 8 }}
            iconType="line"
          />

          {/* Diagonal reference for ROC */}
          {isRoc && (
            <ReferenceLine
              segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
              stroke="#334155"
              strokeDasharray="4 4"
            />
          )}

          {methods.map((name) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              name={`${name} (AUC=${data[name].auc.toFixed(3)})`}
              stroke={data[name].color}
              strokeWidth={2}
              strokeDasharray={data[name].dash ? '6 3' : undefined}
              dot={false}
              activeDot={{ r: 3 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>

      {/* Summary table below chart */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-700/50">
              <th className="text-left py-1 px-2 text-slate-400 font-medium">Method</th>
              <th className="text-right py-1 px-2 text-slate-400 font-medium">AUC</th>
              <th className="text-right py-1 px-2 text-slate-400 font-medium">EER</th>
              <th className="text-right py-1 px-2 text-slate-400 font-medium">FAR@FRR=1%</th>
            </tr>
          </thead>
          <tbody>
            {methods.map((name) => {
              const r = data[name];
              return (
                <tr key={name} className="border-b border-slate-800/30 hover:bg-slate-800/20">
                  <td className="py-1.5 px-2 font-medium" style={{ color: r.color }}>
                    {name}
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono text-slate-300">
                    {r.auc.toFixed(4)}
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono text-slate-300">
                    {(r.eer * 100).toFixed(2)}%
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono text-slate-300">
                    {(r.far_at_frr_1pct * 100).toFixed(2)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
