import { cn } from '@/lib/utils';
import type { TradeStatus, TradeOutcome, StrategyStatus } from '@/types';

interface StatusBadgeProps {
  status: TradeStatus | TradeOutcome | StrategyStatus | 'approved' | 'vetoed' | 'pending' | 'executed' | 'closed' | 'win' | 'loss' | 'breakeven' | 'open' | 'active' | 'paused' | 'archived' | 'live';
  size?: 'sm' | 'md';
  className?: string;
}

const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
  // Trade statuses
  approved: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', label: 'Approved' },
  vetoed: { bg: 'bg-red-500/10', text: 'text-red-400', label: 'Vetoed' },
  pending: { bg: 'bg-amber-500/10', text: 'text-amber-400', label: 'Pending' },
  executed: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', label: 'Executed' },
  closed: { bg: 'bg-[#1E2129]', text: 'text-[#A1A7B3]', label: 'Closed' },
  live: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', label: 'Live' },
  
  // Outcomes
  win: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', label: 'Win' },
  loss: { bg: 'bg-red-500/10', text: 'text-red-400', label: 'Loss' },
  breakeven: { bg: 'bg-[#1E2129]', text: 'text-[#A1A7B3]', label: 'Breakeven' },
  open: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', label: 'Open' },
  
  // Strategy statuses
  active: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', label: 'Active' },
  paused: { bg: 'bg-amber-500/10', text: 'text-amber-400', label: 'Paused' },
  archived: { bg: 'bg-[#1E2129]', text: 'text-[#6B7280]', label: 'Archived' },
};

export function StatusBadge({ status, size = 'md', className }: StatusBadgeProps) {
  const config = statusConfig[status] || { bg: 'bg-[#1E2129]', text: 'text-[#A1A7B3]', label: status };
  
  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium',
        size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs',
        config.bg,
        config.text,
        className
      )}
    >
      {config.label}
    </span>
  );
}
