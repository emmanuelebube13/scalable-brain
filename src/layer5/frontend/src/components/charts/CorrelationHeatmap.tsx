import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import type { CorrelationData } from '@/types';

interface CorrelationHeatmapProps {
  assets: string[];
  correlations: CorrelationData[];
  animated?: boolean;
}

export function CorrelationHeatmap({
  assets,
  correlations,
  animated = true,
}: CorrelationHeatmapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cellsRef = useRef<(HTMLDivElement | null)[]>([]);

  const getCorrelation = (asset1: string, asset2: string): number => {
    if (asset1 === asset2) return 1;
    const corr = correlations.find(
      (c) =>
        (c.asset1 === asset1 && c.asset2 === asset2) ||
        (c.asset1 === asset2 && c.asset2 === asset1)
    );
    return corr?.correlation ?? 0;
  };

  const getColor = (value: number): string => {
    // Red for negative, neutral for near 0, cyan for positive
    if (value < 0) {
      const intensity = Math.abs(value);
      return `rgba(248, 113, 113, ${0.1 + intensity * 0.5})`;
    }
    const intensity = value;
    return `rgba(34, 211, 238, ${0.1 + intensity * 0.5})`;
  };

  useEffect(() => {
    if (!animated) return;

    const ctx = gsap.context(() => {
      gsap.fromTo(
        cellsRef.current.filter(Boolean),
        { scale: 0.96, opacity: 0 },
        {
          scale: 1,
          opacity: 1,
          duration: 0.3,
          stagger: {
            each: 0.02,
            from: 'start',
            grid: [assets.length, assets.length],
          },
          ease: 'power2.out',
        }
      );
    });

    return () => ctx.revert();
  }, [assets.length, animated]);

  return (
    <div ref={containerRef} className="overflow-auto">
      <div
        className="grid gap-1"
        style={{
          gridTemplateColumns: `auto repeat(${assets.length}, minmax(40px, 1fr))`,
        }}
      >
        {/* Header row */}
        <div className="w-12" /> {/* Corner cell */}
        {assets.map((asset) => (
          <div
            key={`header-${asset}`}
            className="text-[10px] text-[#A1A7B3] text-center py-1 truncate"
            title={asset}
          >
            {asset.split('_')[0]}
          </div>
        ))}

        {/* Data rows */}
        {assets.map((rowAsset, rowIndex) => (
          <div key={`row-${rowAsset}`} className="contents">
            {/* Row label */}
            <div
              className="text-[10px] text-[#A1A7B3] text-right pr-2 py-1 flex items-center justify-end"
              title={rowAsset}
            >
              {rowAsset.split('_')[0]}
            </div>

            {/* Cells */}
            {assets.map((colAsset, colIndex) => {
              const correlation = getCorrelation(rowAsset, colAsset);
              const cellIndex = rowIndex * assets.length + colIndex;

              return (
                <div
                  key={`cell-${rowAsset}-${colAsset}`}
                  ref={(el) => { cellsRef.current[cellIndex] = el; }}
                  className={`
                    aspect-square rounded flex items-center justify-center
                    text-[10px] font-medium cursor-pointer
                    transition-transform hover:scale-110 hover:z-10
                  `}
                  style={{
                    backgroundColor: getColor(correlation),
                    color: Math.abs(correlation) > 0.5 ? '#F3F4F6' : '#A1A7B3',
                  }}
                  title={`${rowAsset} vs ${colAsset}: ${(correlation * 100).toFixed(1)}%`}
                >
                  {correlation.toFixed(2)}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-3 text-[10px] text-[#A1A7B3]">
        <div className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-red-400/30" />
          <span>Negative</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-[#1E2129]" />
          <span>Neutral</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-cyan-400/30" />
          <span>Positive</span>
        </div>
      </div>
    </div>
  );
}
