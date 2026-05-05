import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { Gauge } from '@/components/charts/Gauge';
import { CorrelationHeatmap } from '@/components/charts/CorrelationHeatmap';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
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
import * as api from '@/services/api';
import { AlertTriangle, Shield, TrendingDown } from 'lucide-react';

const DEFAULT_RISK_METRICS = {
  netNotionalExposure: 0,
  maxDrawdown: 0,
  maxDrawdownDate: new Date(),
  maxConsecutiveLoss: 0,
  correlationRiskScore: 0,
  concentrationAlert: 'No active concentration alert.',
  exposureByAsset: [],
  correlationMatrix: [],
  underwaterData: [],
};

function reviveDates(obj: any): any {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) return obj.map(reviveDates);
  if (typeof obj !== 'object') return obj;
  const result: any = {};
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/.test(value)) {
      result[key] = new Date(value);
    } else {
      result[key] = reviveDates(value);
    }
  }
  return result;
}

export function Risk() {
  const containerRef = useRef<HTMLDivElement>(null);
  const leftPanelRef = useRef<HTMLDivElement>(null);
  const centerPanelRef = useRef<HTMLDivElement>(null);
  const rightPanelRef = useRef<HTMLDivElement>(null);

  const [riskMetrics, setRiskMetrics] = useState<any>(DEFAULT_RISK_METRICS);
  const [limitStatus, setLimitStatus] = useState<any[]>([]);
  const [blockedTrades, setBlockedTrades] = useState<any[]>([]);
  const assets = ['EUR_USD', 'GBP_USD', 'USD_JPY', 'AUD_USD', 'USD_CAD'];

  useEffect(() => {
    // Load all risk data in parallel
    Promise.allSettled([
      api.fetchRiskMetrics(),
      api.fetchRiskLimits(),
      api.fetchBlockedTrades(10),
    ]).then(([metricsResult, limitsResult, tradesResult]) => {
      if (metricsResult.status === 'fulfilled') {
        setRiskMetrics(reviveDates(metricsResult.value));
      } else {
        console.error('Failed to fetch risk metrics:', metricsResult.reason);
        setRiskMetrics(DEFAULT_RISK_METRICS);
      }

      if (limitsResult.status === 'fulfilled') {
        setLimitStatus(reviveDates(limitsResult.value));
      } else {
        console.error('Failed to fetch risk limits:', limitsResult.reason);
        setLimitStatus([]);
      }

      if (tradesResult.status === 'fulfilled') {
        setBlockedTrades(reviveDates(tradesResult.value));
      } else {
        console.error('Failed to fetch blocked trades:', tradesResult.reason);
        setBlockedTrades([]);
      }
    });
  }, []);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Left panel
      gsap.fromTo(
        leftPanelRef.current?.children || [],
        { x: -20, opacity: 0 },
        { x: 0, opacity: 1, duration: 0.35, stagger: 0.1, ease: 'power2.out' }
      );

      // Center panel
      gsap.fromTo(
        centerPanelRef.current?.children || [],
        { y: 20, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.35, stagger: 0.1, ease: 'power2.out', delay: 0.15 }
      );

      // Right panel
      gsap.fromTo(
        rightPanelRef.current?.children || [],
        { x: 20, opacity: 0 },
        { x: 0, opacity: 1, duration: 0.35, stagger: 0.1, ease: 'power2.out', delay: 0.3 }
      );
    });

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef} className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Shield className="w-6 h-6 text-cyan-400" />
          <h2 className="text-xl font-semibold text-[#F3F4F6]">Risk Dashboard</h2>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-[#A1A7B3]">
            Correlation Risk Score:
          </span>
          <span className={`
            px-3 py-1 rounded-lg text-sm font-medium
            ${riskMetrics.correlationRiskScore > 75 
              ? 'bg-red-500/10 text-red-400' 
              : riskMetrics.correlationRiskScore > 50
              ? 'bg-amber-500/10 text-amber-400'
              : 'bg-emerald-500/10 text-emerald-400'}
          `}>
            {riskMetrics.correlationRiskScore}/100
          </span>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Panel - Risk Summary */}
        <div ref={leftPanelRef} className="lg:col-span-3 space-y-4">
          {/* Net Exposure */}
          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#A1A7B3] mb-3">
              Net Notional Exposure
            </h3>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold text-[#F3F4F6]">
                {riskMetrics.netNotionalExposure.toFixed(1)}%
              </span>
              <span className="text-sm text-[#6B7280]">of capital</span>
            </div>
            <div className="mt-3 h-2 bg-[#1E2129] rounded-full overflow-hidden">
              <div
                className="h-full bg-cyan-400 rounded-full transition-all duration-500"
                style={{ width: `${riskMetrics.netNotionalExposure}%` }}
              />
            </div>
          </div>

          {/* Max Drawdown */}
          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#A1A7B3] mb-3">
              Max Drawdown
            </h3>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold text-red-400">
                -{riskMetrics.maxDrawdown.toFixed(1)}%
              </span>
            </div>
            <p className="mt-2 text-xs text-[#6B7280]">
              Occurred on {format(riskMetrics.maxDrawdownDate, 'yyyy-MM-dd')}
            </p>
          </div>

          {/* Max Consecutive Loss */}
          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#A1A7B3] mb-3">
              Max Consecutive Loss
            </h3>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold text-amber-400">
                {riskMetrics.maxConsecutiveLoss}
              </span>
              <span className="text-sm text-[#6B7280]">trades</span>
            </div>
          </div>

          {/* Concentration Alert */}
          <div className="bg-[#14161C] rounded-xl border border-amber-500/20 p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-medium text-amber-400">Concentration Alert</h3>
                <p className="mt-1 text-xs text-[#A1A7B3]">{riskMetrics.concentrationAlert}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Center Panel - Charts */}
        <div ref={centerPanelRef} className="lg:col-span-6 space-y-4">
          {/* Correlation Heatmap */}
          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
            <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Correlation Matrix (30-day)</h3>
            <CorrelationHeatmap
              assets={assets}
              correlations={riskMetrics.correlationMatrix}
              animated
            />
          </div>

          {/* Exposure Bar Chart */}
          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
            <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Exposure by Asset</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={riskMetrics.exposureByAsset}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis
                  dataKey="asset"
                  tickFormatter={(a) => a.split('_')[0]}
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
                />
                <Bar dataKey="long" stackId="a" fill="#34D399" name="Long" />
                <Bar dataKey="short" stackId="a" fill="#F87171" name="Short" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Underwater Plot */}
          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
            <div className="flex items-center gap-2 mb-4">
              <TrendingDown className="w-4 h-4 text-red-400" />
              <h3 className="text-sm font-semibold text-[#F3F4F6]">Underwater Plot</h3>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={riskMetrics.underwaterData}>
                <defs>
                  <linearGradient id="underwaterGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#F87171" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#F87171" stopOpacity={0} />
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
                  formatter={(v: number) => [`${v.toFixed(2)}%`, 'Drawdown']}
                />
                <Area
                  type="monotone"
                  dataKey="drawdown"
                  stroke="#F87171"
                  fill="url(#underwaterGradient)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right Panel - Limits & Alerts */}
        <div ref={rightPanelRef} className="lg:col-span-3 space-y-4">
          {/* Risk Limit Trackers */}
          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
            <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Risk Limits</h3>
            <div className="space-y-4">
              {limitStatus.map((limit) => (
                <div key={limit.name}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-[#A1A7B3]">{limit.name}</span>
                    <span className={`
                      ${limit.current / limit.limit > 0.8 ? 'text-red-400' : 'text-[#F3F4F6]'}
                    `}>
                      {limit.current.toFixed(1)}{limit.unit} / {limit.limit}{limit.unit}
                    </span>
                  </div>
                  <div className="h-1.5 bg-[#1E2129] rounded-full overflow-hidden">
                    <div
                      className={`
                        h-full rounded-full transition-all duration-500
                        ${limit.current / limit.limit > 0.8 
                          ? 'bg-red-400' 
                          : limit.current / limit.limit > 0.6
                          ? 'bg-amber-400'
                          : 'bg-cyan-400'}
                      `}
                      style={{ width: `${Math.min((limit.current / limit.limit) * 100, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Gauges */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-3">
              <Gauge
                value={riskMetrics.netNotionalExposure}
                max={50}
                size={100}
                strokeWidth={8}
                color="#22D3EE"
                label="Exposure"
                unit="%"
              />
            </div>
            <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-3">
              <Gauge
                value={riskMetrics.correlationRiskScore}
                max={100}
                size={100}
                strokeWidth={8}
                color={riskMetrics.correlationRiskScore > 75 ? '#F87171' : '#F59E0B'}
                label="Correlation"
                unit="/100"
              />
            </div>
          </div>

          {/* Blocked Trades Log */}
          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] overflow-hidden">
            <div className="px-4 py-3 border-b border-white/[0.06]">
              <h3 className="text-sm font-semibold text-[#F3F4F6]">Blocked Trades (last 10)</h3>
            </div>
            <ScrollArea className="h-[200px]">
              <Table>
                <TableHeader>
                  <TableRow className="border-white/[0.06] hover:bg-transparent">
                    <TableHead className="text-[#A1A7B3] text-[10px] uppercase">Time</TableHead>
                    <TableHead className="text-[#A1A7B3] text-[10px] uppercase">Asset</TableHead>
                    <TableHead className="text-[#A1A7B3] text-[10px] uppercase">Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {blockedTrades.map((trade) => (
                    <TableRow
                      key={trade.id}
                      className="border-white/[0.06] text-[#F3F4F6]"
                    >
                      <TableCell className="font-mono text-xs">
                        {trade.timestamp && format(trade.timestamp, 'HH:mm')}
                      </TableCell>
                      <TableCell className="text-xs">{trade.asset}</TableCell>
                      <TableCell className="text-xs text-red-400 truncate max-w-[100px]">
                        {trade.vetoReason}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ScrollArea>
          </div>
        </div>
      </div>
    </div>
  );
}
