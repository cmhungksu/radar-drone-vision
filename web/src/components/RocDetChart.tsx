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
} from 'recharts';

interface RocDetChartProps {
  mode: 'roc' | 'det';
  fpr: number[];
  tprOrFnr: number[];
  auc?: number;
}

export default function RocDetChart({ mode, fpr, tprOrFnr, auc }: RocDetChartProps) {
  const data = useMemo(() => {
    if (!fpr || !tprOrFnr || fpr.length === 0) return [];

    // Downsample if too many points
    const step = fpr.length > 200 ? Math.ceil(fpr.length / 200) : 1;
    const points = [];
    for (let i = 0; i < fpr.length; i += step) {
      points.push({
        fpr: fpr[i],
        value: tprOrFnr[i],
      });
    }
    // Always include last point
    if (points.length > 0 && points[points.length - 1].fpr !== fpr[fpr.length - 1]) {
      points.push({
        fpr: fpr[fpr.length - 1],
        value: tprOrFnr[tprOrFnr.length - 1],
      });
    }
    return points;
  }, [fpr, tprOrFnr]);

  if (data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
        No curve data available
      </div>
    );
  }

  const isRoc = mode === 'roc';
  const yLabel = isRoc ? 'True Positive Rate' : 'False Negative Rate';
  const lineColor = isRoc ? '#22c55e' : '#f59e0b';

  return (
    <div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
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
              offset: -5,
              fill: '#64748b',
              fontSize: 10,
            }}
          />
          <YAxis
            dataKey="value"
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
              fontSize: 10,
            }}
          />
          <Tooltip
            contentStyle={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 8,
              color: '#e2e8f0',
              fontSize: 11,
            }}
            formatter={(val: number) => [val.toFixed(4), isRoc ? 'TPR' : 'FNR']}
            labelFormatter={(val: number) => `FPR: ${Number(val).toFixed(4)}`}
          />

          {/* Diagonal reference line */}
          {isRoc && (
            <ReferenceLine
              segment={[
                { x: 0, y: 0 },
                { x: 1, y: 1 },
              ]}
              stroke="#334155"
              strokeDasharray="4 4"
            />
          )}

          <Line
            type="monotone"
            dataKey="value"
            stroke={lineColor}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3, fill: lineColor }}
          />
        </LineChart>
      </ResponsiveContainer>

      {isRoc && auc != null && (
        <div className="text-center mt-1">
          <span className="text-xs text-slate-500 font-mono">
            AUC = <span className="text-green-400">{auc.toFixed(4)}</span>
          </span>
        </div>
      )}
    </div>
  );
}
