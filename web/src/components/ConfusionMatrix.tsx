interface ConfusionMatrixProps {
  matrix: number[][];
  labels: string[];
}

export default function ConfusionMatrix({ matrix, labels }: ConfusionMatrixProps) {
  if (!matrix || matrix.length === 0) return null;

  // Find max value for color scaling
  const allValues = matrix.flat();
  const maxVal = Math.max(...allValues, 1);

  function cellColor(value: number, row: number, col: number): string {
    const norm = value / maxVal;
    if (row === col) {
      // Diagonal (correct predictions): green
      const alpha = 0.15 + norm * 0.65;
      return `rgba(22, 163, 74, ${alpha})`;
    } else {
      // Off-diagonal (errors): red
      const alpha = norm * 0.6;
      return `rgba(239, 68, 68, ${alpha})`;
    }
  }

  function textColor(value: number, row: number, col: number): string {
    const norm = value / maxVal;
    if (row === col) {
      return norm > 0.5 ? '#bbf7d0' : '#86efac';
    }
    return norm > 0.3 ? '#fecaca' : '#94a3b8';
  }

  const cellSize = labels.length <= 3 ? 80 : labels.length <= 6 ? 60 : 48;

  return (
    <div className="flex flex-col items-center">
      {/* Y-axis label */}
      <div className="flex items-start gap-2">
        <div
          className="flex items-center justify-center"
          style={{ width: 20, height: labels.length * cellSize }}
        >
          <span
            className="text-[10px] text-slate-500 font-mono tracking-wider whitespace-nowrap"
            style={{ transform: 'rotate(-90deg)' }}
          >
            ACTUAL
          </span>
        </div>

        <div>
          {/* Column headers */}
          <div className="flex" style={{ marginLeft: cellSize - 10 }}>
            {labels.map((label) => (
              <div
                key={label}
                className="text-center text-[10px] text-slate-400 font-mono truncate"
                style={{ width: cellSize }}
              >
                {label}
              </div>
            ))}
          </div>

          {/* Matrix grid */}
          {matrix.map((row, ri) => (
            <div key={ri} className="flex items-center">
              {/* Row label */}
              <div
                className="text-[10px] text-slate-400 font-mono text-right pr-2 truncate"
                style={{ width: cellSize - 10 }}
              >
                {labels[ri] ?? `C${ri}`}
              </div>

              {row.map((val, ci) => (
                <div
                  key={ci}
                  className="flex items-center justify-center border border-slate-800/30 transition-colors"
                  style={{
                    width: cellSize,
                    height: cellSize,
                    backgroundColor: cellColor(val, ri, ci),
                  }}
                >
                  <span
                    className="font-mono text-sm font-bold"
                    style={{ color: textColor(val, ri, ci) }}
                  >
                    {val}
                  </span>
                </div>
              ))}
            </div>
          ))}

          {/* X-axis label */}
          <div className="text-center mt-2">
            <span className="text-[10px] text-slate-500 font-mono tracking-wider">PREDICTED</span>
          </div>
        </div>
      </div>
    </div>
  );
}
