interface RangeDopplerPanelProps {
  imageData: string; // base64 data URL or raw base64
  title?: string;
}

export default function RangeDopplerPanel({ imageData, title }: RangeDopplerPanelProps) {
  const src = imageData.startsWith('data:')
    ? imageData
    : `data:image/png;base64,${imageData}`;

  return (
    <div className="relative">
      {title && (
        <div className="absolute top-2 left-2 bg-black/60 backdrop-blur-sm px-2 py-1 rounded text-[10px] text-cyan-400 font-mono uppercase tracking-wider z-10">
          {title}
        </div>
      )}
      <div className="bg-black rounded-lg overflow-hidden border border-slate-800">
        <img
          src={src}
          alt={title ?? 'Range-Doppler Map'}
          className="w-full h-auto object-contain max-h-[400px]"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
      </div>
      <div className="flex justify-between mt-1.5 text-[10px] text-slate-600 font-mono">
        <span>Doppler Velocity &rarr;</span>
        <span>&uarr; Range</span>
      </div>
    </div>
  );
}
