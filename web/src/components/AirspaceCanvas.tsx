import { type AirspaceTarget } from '../api';

interface AirspaceCanvasProps {
  targets: AirspaceTarget[];
  maxRange?: number;
  sectorAngle?: number; // degrees, total fan angle
}

export default function AirspaceCanvas({
  targets,
  maxRange = 500,
  sectorAngle = 120,
}: AirspaceCanvasProps) {
  const width = 600;
  const height = 450;
  const cx = width / 2;
  const cy = height - 40;
  const radius = height - 80;

  const numRings = 4;
  const halfAngle = (sectorAngle / 2) * (Math.PI / 180);

  // Generate range rings
  const rings = Array.from({ length: numRings }, (_, i) => {
    const r = ((i + 1) / numRings) * radius;
    const rangeVal = ((i + 1) / numRings) * maxRange;
    return { r, label: `${rangeVal.toFixed(0)}m` };
  });

  // Fan boundary lines
  const leftAngle = -Math.PI / 2 - halfAngle;
  const rightAngle = -Math.PI / 2 + halfAngle;
  const leftX = cx + radius * Math.cos(leftAngle);
  const leftY = cy + radius * Math.sin(leftAngle);
  const rightX = cx + radius * Math.cos(rightAngle);
  const rightY = cy + radius * Math.sin(rightAngle);

  // Generate arc path for range rings (sector arc)
  function arcPath(r: number): string {
    const startX = cx + r * Math.cos(leftAngle);
    const startY = cy + r * Math.sin(leftAngle);
    const endX = cx + r * Math.cos(rightAngle);
    const endY = cy + r * Math.sin(rightAngle);
    const largeArc = sectorAngle > 180 ? 1 : 0;
    return `M ${startX} ${startY} A ${r} ${r} 0 ${largeArc} 1 ${endX} ${endY}`;
  }

  // Map target to SVG coords
  function targetToSvg(t: AirspaceTarget): { x: number; y: number } {
    const normRange = Math.min(t.range_m / maxRange, 1);
    const r = normRange * radius;
    const azRad = (t.azimuth_deg * Math.PI) / 180 - Math.PI / 2;
    return {
      x: cx + r * Math.cos(azRad),
      y: cy + r * Math.sin(azRad),
    };
  }

  function isUAV(cls: string): boolean {
    const lower = cls.toLowerCase();
    return lower.includes('uav') || lower.includes('drone');
  }

  return (
    <div className="flex justify-center">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full max-w-[600px]"
        style={{ filter: 'drop-shadow(0 0 20px rgba(22, 163, 74, 0.15))' }}
      >
        <defs>
          <radialGradient id="radarBg" cx="50%" cy="90%" r="80%">
            <stop offset="0%" stopColor="#16a34a" stopOpacity={0.05} />
            <stop offset="100%" stopColor="#0b0f19" stopOpacity={0} />
          </radialGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background fill */}
        <rect width={width} height={height} fill="#0b0f19" />

        {/* Sector fill */}
        <path
          d={`M ${cx} ${cy} L ${leftX} ${leftY} A ${radius} ${radius} 0 ${sectorAngle > 180 ? 1 : 0} 1 ${rightX} ${rightY} Z`}
          fill="url(#radarBg)"
        />

        {/* Range rings */}
        {rings.map((ring, i) => (
          <g key={i}>
            <path d={arcPath(ring.r)} fill="none" stroke="#16a34a" strokeOpacity={0.2} strokeWidth={1} />
            <text
              x={cx + ring.r * Math.cos(rightAngle) + 8}
              y={cy + ring.r * Math.sin(rightAngle)}
              fill="#334155"
              fontSize={9}
              fontFamily="monospace"
            >
              {ring.label}
            </text>
          </g>
        ))}

        {/* Azimuth lines */}
        {[-60, -30, 0, 30, 60].map((deg) => {
          const azRad = (deg * Math.PI) / 180 - Math.PI / 2;
          const endX = cx + radius * Math.cos(azRad);
          const endY = cy + radius * Math.sin(azRad);
          return (
            <g key={deg}>
              <line x1={cx} y1={cy} x2={endX} y2={endY} stroke="#16a34a" strokeOpacity={0.1} strokeWidth={1} strokeDasharray="4 4" />
              <text
                x={endX + (deg < 0 ? -20 : deg > 0 ? 5 : -5)}
                y={endY - 5}
                fill="#475569"
                fontSize={9}
                fontFamily="monospace"
                textAnchor="middle"
              >
                {deg}&deg;
              </text>
            </g>
          );
        })}

        {/* Sector boundary lines */}
        <line x1={cx} y1={cy} x2={leftX} y2={leftY} stroke="#16a34a" strokeOpacity={0.4} strokeWidth={1.5} />
        <line x1={cx} y1={cy} x2={rightX} y2={rightY} stroke="#16a34a" strokeOpacity={0.4} strokeWidth={1.5} />

        {/* Radar position */}
        <circle cx={cx} cy={cy} r={5} fill="#16a34a" filter="url(#glow)" />
        <circle cx={cx} cy={cy} r={2} fill="#22c55e" />
        <text x={cx} y={cy + 18} fill="#16a34a" fontSize={9} fontFamily="monospace" textAnchor="middle">
          RADAR
        </text>

        {/* Targets */}
        {targets.map((t) => {
          const pos = targetToSvg(t);
          const uav = isUAV(t.classification);
          const color = uav ? '#ef4444' : '#3b82f6';
          return (
            <g key={t.track_id}>
              {/* Halo */}
              <circle cx={pos.x} cy={pos.y} r={10} fill={color} fillOpacity={0.1} />
              {/* Dot */}
              <circle cx={pos.x} cy={pos.y} r={4} fill={color} filter="url(#glow)" />
              <circle cx={pos.x} cy={pos.y} r={2} fill="white" fillOpacity={0.8} />
              {/* Label */}
              <text
                x={pos.x + 8}
                y={pos.y - 6}
                fill={color}
                fontSize={8}
                fontFamily="monospace"
                fontWeight="bold"
              >
                {t.classification.toUpperCase()}
              </text>
              <text
                x={pos.x + 8}
                y={pos.y + 4}
                fill="#64748b"
                fontSize={7}
                fontFamily="monospace"
              >
                {t.track_id}
              </text>
            </g>
          );
        })}

        {/* Legend */}
        <g transform={`translate(${width - 120}, 15)`}>
          <rect x={0} y={0} width={110} height={50} rx={4} fill="#111827" fillOpacity={0.9} stroke="#334155" strokeWidth={0.5} />
          <circle cx={12} cy={16} r={4} fill="#ef4444" />
          <text x={22} y={19} fill="#94a3b8" fontSize={9} fontFamily="monospace">UAV / Drone</text>
          <circle cx={12} cy={34} r={4} fill="#3b82f6" />
          <text x={22} y={37} fill="#94a3b8" fontSize={9} fontFamily="monospace">Bird / Other</text>
        </g>
      </svg>
    </div>
  );
}
