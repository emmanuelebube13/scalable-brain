import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { StatusBadge } from '@/components/ui-custom/StatusBadge';
import { Sparkline } from '@/components/charts/Sparkline';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts';
import { format } from 'date-fns';
import * as mockData from '@/services/mockData';
import * as api from '@/services/api';
import type { Strategy } from '@/types';
import {
  Target,
  TrendingUp,
  CheckCircle2,
  XCircle,
  BarChart3,
} from 'lucide-react';

function parseDates<T>(obj: T): T {
  if (Array.isArray(obj)) return obj.map(parseDates) as unknown as T;
  if (obj && typeof obj === 'object') {
    const out: any = { ...obj };
    for (const key of Object.keys(out)) {
      if (typeof out[key] === 'string' && /\d{4}-\d{2}-\d{2}T/.test(out[key])) {
        out[key] = new Date(out[key]);
      } else if (typeof out[key] === 'object') {
        out[key] = parseDates(out[key]);
      }
    }
    return out;
  }
  return obj;
}

export function Strategies() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);

  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);

  useEffect(() => {
    api.fetchStrategies()
      .then((data) => setStrategies(parseDates(data)))
      .catch(() => setStrategies(mockData.getStrategies()));
  }, []);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        cardsRef.current?.children || [],
        { y: 20, opacity: 0, scale: 0.98 },
        { y: 0, opacity: 1, scale: 1, duration: 0.35, stagger: 0.08, ease: 'power2.out' }
      );
    });

    return () => ctx.revert();
  }, [strategies]);

  return (
    <div ref={containerRef} className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Target className="w-6 h-6 text-cyan-400" />
        <h2 className="text-xl font-semibold text-[#F3F4F6]">Strategy Breakdown</h2>
      </div>

      {/* Strategy Cards Grid */}
      <div ref={cardsRef} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {strategies.map((strategy) => (
          <div
            key={strategy.id}
            onClick={() => setSelectedStrategy(strategy)}
            className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4 cursor-pointer card-hover"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="text-sm font-semibold text-[#F3F4F6]">{strategy.name}</h3>
                <p className="text-xs text-[#6B7280] mt-0.5 line-clamp-1">{strategy.description}</p>
              </div>
              <StatusBadge status={strategy.status} size="sm" />
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="bg-[#1E2129] rounded-lg p-2">
                <div className="flex items-center gap-1 text-[10px] text-[#6B7280] mb-1">
                  <BarChart3 className="w-3 h-3" />
                  Win Rate
                </div>
                <p className={`text-sm font-semibold ${strategy.winRate >= 55 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {strategy.winRate.toFixed(1)}%
                </p>
              </div>
              <div className="bg-[#1E2129] rounded-lg p-2">
                <div className="flex items-center gap-1 text-[10px] text-[#6B7280] mb-1">
                  <TrendingUp className="w-3 h-3" />
                  Expectancy
                </div>
                <p className={`text-sm font-semibold ${strategy.expectancyR >= 0.2 ? 'text-emerald-400' : strategy.expectancyR >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
                  {strategy.expectancyR >= 0 ? '+' : ''}{strategy.expectancyR.toFixed(2)}R
                </p>
              </div>
              <div className="bg-[#1E2129] rounded-lg p-2">
                <div className="flex items-center gap-1 text-[10px] text-[#6B7280] mb-1">
                  <Target className="w-3 h-3" />
                  PF
                </div>
                <p className={`text-sm font-semibold ${strategy.profitFactor >= 1.5 ? 'text-emerald-400' : strategy.profitFactor >= 1 ? 'text-amber-400' : 'text-red-400'}`}>
                  {strategy.profitFactor.toFixed(2)}
                </p>
              </div>
            </div>

            {/* Sparkline */}
            <div className="h-10 mb-3">
              <Sparkline
                data={strategy.equityCurve.map((e) => e.equity)}
                width={280}
                height={40}
                color={strategy.equityCurve[strategy.equityCurve.length - 1].equity > strategy.equityCurve[0].equity ? '#34D399' : '#F87171'}
                animated
              />
            </div>

            {/* Footer Stats */}
            <div className="flex items-center justify-between text-xs text-[#6B7280]">
              <span>{strategy.totalSignals} signals</span>
              <span>{strategy.approvalRate}% approved</span>
            </div>
          </div>
        ))}
      </div>

      {/* Strategy Detail Dialog */}
      <Dialog open={!!selectedStrategy} onOpenChange={() => setSelectedStrategy(null)}>
        <DialogContent className="max-w-4xl bg-[#14161C] border-white/[0.06] text-[#F3F4F6]">
          {selectedStrategy && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <Target className="w-5 h-5 text-cyan-400" />
                  {selectedStrategy.name}
                </DialogTitle>
              </DialogHeader>

              <div className="space-y-6 mt-4">
                {/* Description */}
                <p className="text-sm text-[#A1A7B3]">{selectedStrategy.description}</p>

                {/* Key Metrics */}
                <div className="grid grid-cols-4 gap-4">
                  <div className="bg-[#1E2129] rounded-lg p-3 text-center">
                    <div className="text-[10px] text-[#6B7280] uppercase mb-1">Win Rate</div>
                    <div className={`text-xl font-bold ${selectedStrategy.winRate >= 55 ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {selectedStrategy.winRate.toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-[#1E2129] rounded-lg p-3 text-center">
                    <div className="text-[10px] text-[#6B7280] uppercase mb-1">Expectancy</div>
                    <div className={`text-xl font-bold ${selectedStrategy.expectancyR >= 0.2 ? 'text-emerald-400' : selectedStrategy.expectancyR >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
                      {selectedStrategy.expectancyR >= 0 ? '+' : ''}{selectedStrategy.expectancyR.toFixed(2)}R
                    </div>
                  </div>
                  <div className="bg-[#1E2129] rounded-lg p-3 text-center">
                    <div className="text-[10px] text-[#6B7280] uppercase mb-1">Profit Factor</div>
                    <div className={`text-xl font-bold ${selectedStrategy.profitFactor >= 1.5 ? 'text-emerald-400' : selectedStrategy.profitFactor >= 1 ? 'text-amber-400' : 'text-red-400'}`}>
                      {selectedStrategy.profitFactor.toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-[#1E2129] rounded-lg p-3 text-center">
                    <div className="text-[10px] text-[#6B7280] uppercase mb-1">Total Signals</div>
                    <div className="text-xl font-bold text-[#F3F4F6]">
                      {selectedStrategy.totalSignals}
                    </div>
                  </div>
                </div>

                {/* Equity Curve */}
                <div className="bg-[#0B0C0F] rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-[#F3F4F6] mb-3">Equity Curve</h4>
                  <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={selectedStrategy.equityCurve}>
                      <defs>
                        <linearGradient id="strategyEquityGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#22D3EE" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#22D3EE" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(d) => format(new Date(d), 'MM/dd')}
                        stroke="#6B7280"
                        fontSize={10}
                      />
                      <YAxis stroke="#6B7280" fontSize={10} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#14161C',
                          border: '1px solid rgba(255,255,255,0.06)',
                          borderRadius: '8px',
                        }}
                        formatter={(v: number) => [`$${v.toFixed(2)}`, 'Equity']}
                      />
                      <Area
                        type="monotone"
                        dataKey="equity"
                        stroke="#22D3EE"
                        fill="url(#strategyEquityGradient)"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>

                {/* Win/Loss by Granularity */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-[#0B0C0F] rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-[#F3F4F6] mb-3">Win/Loss by Granularity</h4>
                    <ResponsiveContainer width="100%" height={150}>
                      <BarChart
                        data={Object.entries(selectedStrategy.winLossByGranularity).map(([g, d]) => ({
                          granularity: g,
                          wins: d.wins,
                          losses: d.losses,
                        }))}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                        <XAxis dataKey="granularity" stroke="#6B7280" fontSize={10} />
                        <YAxis stroke="#6B7280" fontSize={10} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#14161C',
                            border: '1px solid rgba(255,255,255,0.06)',
                            borderRadius: '8px',
                          }}
                        />
                        <Bar dataKey="wins" fill="#34D399" />
                        <Bar dataKey="losses" fill="#F87171" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Best/Worst Trade */}
                  <div className="bg-[#0B0C0F] rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-[#F3F4F6] mb-3">Extreme Trades</h4>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between p-2 bg-emerald-500/5 rounded-lg border border-emerald-500/10">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          <span className="text-xs text-[#A1A7B3]">Best Trade</span>
                        </div>
                        <span className="text-sm font-semibold text-emerald-400">
                          +{selectedStrategy.bestTrade.pnl?.toFixed(0)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between p-2 bg-red-500/5 rounded-lg border border-red-500/10">
                        <div className="flex items-center gap-2">
                          <XCircle className="w-4 h-4 text-red-400" />
                          <span className="text-xs text-[#A1A7B3]">Worst Trade</span>
                        </div>
                        <span className="text-sm font-semibold text-red-400">
                          {selectedStrategy.worstTrade.pnl?.toFixed(0)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Correlation with Others */}
                <div className="bg-[#0B0C0F] rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-[#F3F4F6] mb-3">Correlation with Other Strategies</h4>
                  <div className="grid grid-cols-4 gap-2">
                    {Object.entries(selectedStrategy.correlationWithOthers)
                      .slice(0, 8)
                      .map(([name, corr]) => (
                        <div
                          key={name}
                          className="flex items-center justify-between p-2 bg-[#1E2129] rounded-lg"
                        >
                          <span className="text-[10px] text-[#A1A7B3] truncate max-w-[80px]">{name}</span>
                          <span className={`text-xs font-medium ${corr > 0.5 ? 'text-amber-400' : 'text-[#F3F4F6]'}`}>
                            {(corr * 100).toFixed(0)}%
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
