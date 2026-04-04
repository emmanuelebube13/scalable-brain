import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { Sparkline } from '@/components/charts/Sparkline';
import { cn } from '@/lib/utils';

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  change?: number;
  sparklineData?: number[];
  icon?: React.ReactNode;
  color?: 'cyan' | 'green' | 'red' | 'amber' | 'violet';
  className?: string;
  animated?: boolean;
}

const colorMap = {
  cyan: { text: 'text-cyan-400', bg: 'bg-cyan-500/10', glow: 'shadow-cyan-500/10' },
  green: { text: 'text-emerald-400', bg: 'bg-emerald-500/10', glow: 'shadow-emerald-500/10' },
  red: { text: 'text-red-400', bg: 'bg-red-500/10', glow: 'shadow-red-500/10' },
  amber: { text: 'text-amber-400', bg: 'bg-amber-500/10', glow: 'shadow-amber-500/10' },
  violet: { text: 'text-violet-400', bg: 'bg-violet-500/10', glow: 'shadow-violet-500/10' },
};

export function KPICard({
  title,
  value,
  subtitle,
  change,
  sparklineData,
  icon,
  color = 'cyan',
  className,
  animated = true,
}: KPICardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const valueRef = useRef<HTMLSpanElement>(null);

  const colors = colorMap[color];

  useEffect(() => {
    if (!animated || !cardRef.current) return;

    const ctx = gsap.context(() => {
      gsap.fromTo(
        cardRef.current,
        { scale: 0.98, opacity: 0, y: 16 },
        {
          scale: 1,
          opacity: 1,
          y: 0,
          duration: 0.35,
          ease: 'power2.out',
        }
      );

      // Count up animation for numeric values
      if (valueRef.current && typeof value === 'number') {
        const obj = { val: 0 };
        gsap.to(obj, {
          val: value,
          duration: 0.5,
          ease: 'power2.out',
          delay: 0.2,
          onUpdate: () => {
            if (valueRef.current) {
              valueRef.current.textContent = obj.val.toFixed(value % 1 === 0 ? 0 : 2);
            }
          },
        });
      }
    });

    return () => ctx.revert();
  }, [animated, value]);

  const isPositive = change && change >= 0;

  return (
    <div
      ref={cardRef}
      className={cn(
        'bg-[#14161C] rounded-xl p-4 border border-white/[0.06]',
        'hover:border-white/[0.1] transition-colors duration-150',
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          {/* Title */}
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-[#A1A7B3]">
            {title}
          </h3>

          {/* Value */}
          <div className="mt-2 flex items-baseline gap-2">
            <span
              ref={valueRef}
              className={cn('text-2xl font-bold tabular-nums', colors.text)}
            >
              {typeof value === 'number' && animated ? '0' : value}
            </span>
            {change !== undefined && (
              <span
                className={cn(
                  'text-xs font-medium',
                  isPositive ? 'text-emerald-400' : 'text-red-400'
                )}
              >
                {isPositive ? '+' : ''}{change.toFixed(1)}%
              </span>
            )}
          </div>

          {/* Subtitle */}
          {subtitle && (
            <p className="mt-1 text-xs text-[#6B7280]">{subtitle}</p>
          )}
        </div>

        {/* Icon */}
        {icon && (
          <div className={cn('p-2 rounded-lg', colors.bg)}>
            {icon}
          </div>
        )}
      </div>

      {/* Sparkline */}
      {sparklineData && (
        <div className="mt-3">
          <Sparkline
            data={sparklineData}
            width={180}
            height={40}
            color={color === 'cyan' ? '#22D3EE' : color === 'green' ? '#34D399' : color === 'red' ? '#F87171' : color === 'amber' ? '#F59E0B' : '#A78BFA'}
            animated={animated}
          />
        </div>
      )}
    </div>
  );
}
