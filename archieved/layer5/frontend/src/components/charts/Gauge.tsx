import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';

interface GaugeProps {
  value: number;
  min?: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  backgroundColor?: string;
  label?: string;
  unit?: string;
  animated?: boolean;
}

export function Gauge({
  value,
  min = 0,
  max = 100,
  size = 120,
  strokeWidth = 10,
  color = '#22D3EE',
  backgroundColor = '#1E2129',
  label,
  unit = '%',
  animated = true,
}: GaugeProps) {
  const progressRef = useRef<SVGCircleElement>(null);
  const valueRef = useRef<HTMLSpanElement>(null);

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const percentage = Math.min(Math.max((value - min) / (max - min), 0), 1);
  const strokeDashoffset = circumference * (1 - percentage * 0.75); // 75% circle

  const center = size / 2;

  useEffect(() => {
    if (!animated || !progressRef.current) return;

    const ctx = gsap.context(() => {
      // Animate arc draw
      gsap.fromTo(
        progressRef.current,
        { strokeDashoffset: circumference },
        {
          strokeDashoffset,
          duration: 0.7,
          ease: 'power2.out',
        }
      );

      // Animate number count-up
      if (valueRef.current) {
        const obj = { val: 0 };
        gsap.to(obj, {
          val: value,
          duration: 0.5,
          ease: 'power2.out',
          onUpdate: () => {
            if (valueRef.current) {
              valueRef.current.textContent = obj.val.toFixed(1);
            }
          },
        });
      }
    });

    return () => ctx.revert();
  }, [value, animated, circumference, strokeDashoffset]);

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size * 0.75 }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="transform -rotate-[135deg]"
          style={{ transformOrigin: 'center' }}
        >
          {/* Background arc */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={backgroundColor}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={circumference * 0.25}
            strokeLinecap="round"
          />
          {/* Progress arc */}
          <circle
            ref={progressRef}
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={animated ? circumference : strokeDashoffset}
            strokeLinecap="round"
          />
        </svg>
        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pt-4">
          <span
            ref={valueRef}
            className="text-2xl font-bold text-[#F3F4F6] tabular-nums"
          >
            {animated ? '0.0' : value.toFixed(1)}
          </span>
          <span className="text-xs text-[#A1A7B3]">{unit}</span>
        </div>
      </div>
      {label && (
        <span className="text-xs text-[#A1A7B3] mt-1">{label}</span>
      )}
    </div>
  );
}
