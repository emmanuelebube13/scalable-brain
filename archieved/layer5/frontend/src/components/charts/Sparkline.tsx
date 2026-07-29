import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  fillOpacity?: number;
  strokeWidth?: number;
  animated?: boolean;
}

export function Sparkline({
  data,
  width = 120,
  height = 40,
  color = '#22D3EE',
  fillOpacity = 0.15,
  strokeWidth = 2,
  animated = true,
}: SparklineProps) {
  const pathRef = useRef<SVGPathElement>(null);
  const areaRef = useRef<SVGPathElement>(null);

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data.map((value, index) => {
    const x = (index / (data.length - 1)) * width;
    const y = height - ((value - min) / range) * height;
    return [x, y];
  });

  const linePath = points
    .map((point, i) => `${i === 0 ? 'M' : 'L'} ${point[0]} ${point[1]}`)
    .join(' ');

  const areaPath = `${linePath} L ${width} ${height} L 0 ${height} Z`;

  useEffect(() => {
    if (!animated || !pathRef.current || !areaRef.current) return;

    const ctx = gsap.context(() => {
      // Animate line draw
      const length = pathRef.current!.getTotalLength();
      gsap.set(pathRef.current, {
        strokeDasharray: length,
        strokeDashoffset: length,
      });
      gsap.to(pathRef.current, {
        strokeDashoffset: 0,
        duration: 0.6,
        ease: 'power2.out',
      });

      // Animate area fade
      gsap.fromTo(
        areaRef.current,
        { opacity: 0 },
        { opacity: fillOpacity, duration: 0.4, delay: 0.3 }
      );
    });

    return () => ctx.revert();
  }, [data, animated, fillOpacity]);

  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={`gradient-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={fillOpacity} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path
        ref={areaRef}
        d={areaPath}
        fill={`url(#gradient-${color.replace('#', '')})`}
        opacity={animated ? 0 : fillOpacity}
      />
      <path
        ref={pathRef}
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
