import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import {
  Activity,
  CheckCircle2,
  Brain,
  TrendingUp,
  BarChart3,
} from 'lucide-react';
import { KPICard } from '@/components/ui-custom/KPICard';
import { StatusBadge } from '@/components/ui-custom/StatusBadge';
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
  PieChart as RePieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
} from 'recharts';
import { format } from 'date-fns';
import * as api from '@/services/api';
import { dataCache } from '@/services/dataCache';

interface OverviewProps {
  onOpenPositionsClick?: () => void;
}

const DEFAULT_KPI = {
  totalSignals: 0,
  approvalRate: 0,
  avgConfidence: 0,
  livePositions: 0,
  unrealizedPnL: 0,
  winRate24h: 0,
  sharpeRatio: 0,
  maxDrawdown: 0,
  sortinoRatio: 0,
  calmarRatio: 0,
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

function safeDate(value: unknown): Date | null {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  if (typeof value === 'string') {
    const d = new Date(value);
    if (!Number.isNaN(d.getTime())) return d;
  }
  return null;
}

function sortByTimestampDesc<T extends Record<string, any>>(
  rows: T[],
  keys: string[] = ['timestamp', 'date', 'createdAt', 'closeTime']
): T[] {
  return [...rows].sort((left, right) => {
    const leftDate = keys.map((key) => safeDate(left[key])).find(Boolean)?.getTime() ?? 0;
    const rightDate = keys.map((key) => safeDate(right[key])).find(Boolean)?.getTime() ?? 0;
    return rightDate - leftDate;
  });
}

function findLatestTimestamp(collections: Array<Record<string, any>[]>): Date | null {
  let latest: Date | null = null;

  for (const collection of collections) {
    for (const row of collection) {
      for (const key of ['timestamp', 'date', 'createdAt', 'closeTime']) {
        const candidate = safeDate(row?.[key]);
        if (candidate && (!latest || candidate > latest)) {
          latest = candidate;
        }
      }
    }
  }

  return latest;
}

// Generate sparkline data from actual trend data, fallback to simple array if not available
function generateSparkline(trendData: any[], dataKey: string, points: number = 8): number[] {
  if (trendData && trendData.length > 0) {
    const values = trendData.map(d => d[dataKey]).filter(v => v !== undefined && v !== null);
    if (values.length >= 2) {
      return values.slice(-points);
    }
  }
  return [];
}

export function Overview({ onOpenPositionsClick }: OverviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const kpiRef = useRef<HTMLDivElement>(null);
  const tablesRef = useRef<HTMLDivElement>(null);

  const [kpiData, setKpiData] = useState<any>(DEFAULT_KPI);
  const [liveTrades, setLiveTrades] = useState<any[]>([]);
  const [pendingSignals, setPendingSignals] = useState<any[]>([]);
  const [regimeData, setRegimeData] = useState<any[]>([]);
  const [approvalTrend, setApprovalTrend] = useState<any[]>([]);
  const [exposureData, setExposureData] = useState<any[]>([]);
  const [equityCurve, setEquityCurve] = useState<any[]>([]);
  const [attribution, setAttribution] = useState<any[]>([]);
  const [lastDataPoint, setLastDataPoint] = useState<Date | null>(null);

  useEffect(() => {
    const loadData = async () => {
      const [kpiResult, tradesResult, signalsResult, regimesResult, trendResult, riskResult, attrResult, equityResult] = await Promise.allSettled([
        api.fetchKPI(),
        api.fetchTrades(10),
        api.fetchPendingSignals(5),
        api.fetchCurrentRegimes(),
        api.fetchApprovalTrend(),
        api.fetchRiskMetrics(),
        api.fetchAttribution(),
        api.fetchEquityCurve(30),
      ]);

      setKpiData(kpiResult.status === 'fulfilled' ? reviveDates(kpiResult.value) : DEFAULT_KPI);

      const revivedTrades = tradesResult.status === 'fulfilled'
        ? sortByTimestampDesc(reviveDates(tradesResult.value)).slice(0, 10)
        : [];
      setLiveTrades(revivedTrades);

      const revivedSignals = signalsResult.status === 'fulfilled'
        ? sortByTimestampDesc(reviveDates(signalsResult.value)).slice(0, 5)
        : [];
      setPendingSignals(revivedSignals);

      setRegimeData(regimesResult.status === 'fulfilled' ? reviveDates(regimesResult.value) : []);

      const revivedTrend = trendResult.status === 'fulfilled' ? reviveDates(trendResult.value) : [];
      setApprovalTrend(revivedTrend);

      setExposureData(
        riskResult.status === 'fulfilled' ? (reviveDates(riskResult.value).exposureByAsset || []) : []
      );

      setAttribution(attrResult.status === 'fulfilled' ? reviveDates(attrResult.value) : []);

      const revivedEquity = equityResult.status === 'fulfilled' ? reviveDates(equityResult.value) : [];
      setEquityCurve(revivedEquity);

      setLastDataPoint(findLatestTimestamp([revivedTrades, revivedSignals, revivedTrend, revivedEquity]));

      if (kpiResult.status === 'rejected') {
        console.error('Failed to fetch KPI:', kpiResult.reason);
      }
      if (tradesResult.status === 'rejected') {
        console.error('Failed to fetch trades:', tradesResult.reason);
      }
      if (signalsResult.status === 'rejected') {
        console.error('Failed to fetch signals:', signalsResult.reason);
      }
      if (regimesResult.status === 'rejected') {
        console.error('Failed to fetch regimes:', regimesResult.reason);
      }
      if (trendResult.status === 'rejected') {
        console.error('Failed to fetch approval trend:', trendResult.reason);
      }
      if (riskResult.status === 'rejected') {
        console.error('Failed to fetch risk metrics:', riskResult.reason);
      }
      if (attrResult.status === 'rejected') {
        console.error('Failed to fetch attribution:', attrResult.reason);
      }
      if (equityResult.status === 'rejected') {
        console.error('Failed to fetch equity curve:', equityResult.reason);
      }
    };

    loadData();
  }, []);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // KPI cards stagger
      gsap.fromTo(
        kpiRef.current?.children || [],
        { y: 16, opacity: 0, scale: 0.98 },
        {
          y: 0,
          opacity: 1,
          scale: 1,
          duration: 0.35,
          stagger: 0.06,
          ease: 'power2.out',
        }
      );

      // Tables slide in
      gsap.fromTo(
        tablesRef.current?.children || [],
        { x: -10, opacity: 0 },
        {
          x: 0,
          opacity: 1,
          duration: 0.3,
          stagger: 0.08,
          ease: 'power2.out',
          delay: 0.3,
        }
      );
    });

    return () => ctx.revert();
  }, []);

  const approvalPieData = [
    { name: 'Approved', value: kpiData.approvalRate, color: '#34D399' },
    { name: 'Vetoed', value: Math.max(0, 100 - kpiData.approvalRate), color: '#F87171' },
  ];
  const unrealized = Number(kpiData.unrealizedPnL) || 0;
  const pnlSign = unrealized >= 0 ? '+' : '';

  // Generate sparklines from actual trend data (or empty arrays if no data)
  const totalSignalsSparkline = generateSparkline(approvalTrend, 'signalCount');
  const approvalRateSparkline = generateSparkline(approvalTrend, 'approvalRate');
  const confidenceSparkline: number[] = [];
  const winRateSparkline = generateSparkline(approvalTrend, 'approvalRate');

  // Use empty arrays as fallback - no synthetic data
  const defaultSparkline: number[] = [];

  return (
    <div ref={containerRef} className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-[#F3F4F6]">Overview</h2>
        <span className="text-sm text-[#A1A7B3]">
          Data through: {lastDataPoint ? format(lastDataPoint, 'HH:mm:ss') : '—'}
        </span>
      </div>

      {/* KPI Grid */}
      <div ref={kpiRef} className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KPICard
          title="Total Signals"
          value={kpiData.totalSignals.toLocaleString()}
          change={totalSignalsSparkline.length > 1 ? 
            ((totalSignalsSparkline[totalSignalsSparkline.length - 1] - totalSignalsSparkline[0]) / Math.max(1, totalSignalsSparkline[0]) * 100) : undefined}
          sparklineData={totalSignalsSparkline.length > 1 ? totalSignalsSparkline : defaultSparkline}
          icon={<Activity className="w-4 h-4 text-cyan-400" />}
          color="cyan"
        />
        <KPICard
          title="Approval Rate"
          value={`${kpiData.approvalRate}%`}
          change={approvalRateSparkline.length > 1 ? 
            (approvalRateSparkline[approvalRateSparkline.length - 1] - approvalRateSparkline[0]) : undefined}
          sparklineData={approvalRateSparkline.length > 1 ? approvalRateSparkline : defaultSparkline}
          icon={<CheckCircle2 className="w-4 h-4 text-emerald-400" />}
          color="green"
        />
        <KPICard
          title="Avg Confidence"
          value={kpiData.avgConfidence.toFixed(3)}
          sparklineData={confidenceSparkline.length > 1 ? confidenceSparkline : defaultSparkline}
          icon={<Brain className="w-4 h-4 text-violet-400" />}
          color="violet"
        />
        <button
          type="button"
          onClick={onOpenPositionsClick}
          className="text-left rounded-xl focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
          title="Open live positions"
        >
          <KPICard
            title="Live Positions"
            value={kpiData.livePositions}
            subtitle={
              kpiData.positionSource === 'oanda'
                ? `Broker: OANDA${kpiData.openTrades ? ` (${kpiData.livePositions} positions / ${kpiData.openTrades} trades)` : ''} (click to inspect)`
                : 'System snapshot (click to inspect)'
            }
            icon={<TrendingUp className="w-4 h-4 text-cyan-400" />}
            color="cyan"
          />
        </button>
        <KPICard
          title="Unrealized P&L"
          value={`${pnlSign}$${Math.abs(unrealized).toLocaleString()}`}
          subtitle={kpiData.positionSource === 'oanda' ? 'Marked from OANDA account' : 'Marked from system telemetry'}
          icon={<TrendingUp className="w-4 h-4 text-emerald-400" />}
          color={unrealized >= 0 ? "green" : "red"}
        />
        <KPICard
          title="24h Win Rate"
          value={`${kpiData.winRate24h}%`}
          sparklineData={winRateSparkline.length > 1 ? winRateSparkline : defaultSparkline}
          icon={<BarChart3 className="w-4 h-4 text-amber-400" />}
          color="amber"
        />
      </div>

      {/* Main Content Grid */}
      <div ref={tablesRef} className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Live Trades */}
        <div className="lg:col-span-2 bg-[#14161C] rounded-xl border border-white/[0.06] overflow-hidden">
          <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[#F3F4F6]">Live Trades (last 10)</h3>
            <span className="px-2 py-0.5 rounded text-[10px] bg-cyan-500/10 text-cyan-400">Live</span>
          </div>
          <ScrollArea className="h-[280px]">
            <Table>
              <TableHeader>
                <TableRow className="border-white/[0.06] hover:bg-transparent">
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Time</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Asset</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Strategy</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Confidence</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Status</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">P&L</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {liveTrades.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-[#6B7280] py-8">
                      No trades found
                    </TableCell>
                  </TableRow>
                ) : (
                  liveTrades.map((trade, index) => (
                    <TableRow
                      key={trade.id}
                      className={`
                        border-white/[0.06] text-[#F3F4F6]
                        ${index === 0 ? 'animate-flash-new' : ''}
                      `}
                    >
                      <TableCell className="font-mono text-xs">
                        {safeDate(trade.timestamp) ? format(safeDate(trade.timestamp) as Date, 'HH:mm:ss') : 'N/A'}
                      </TableCell>
                      <TableCell className="text-xs">{trade.asset}</TableCell>
                      <TableCell className="text-xs text-[#A1A7B3]">{trade.strategy}</TableCell>
                      <TableCell className="text-xs">
                        <span className={trade.confidence >= 0.535 ? 'text-emerald-400' : 'text-red-400'}>
                          {(trade.confidence ?? 0).toFixed(3)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={trade.status} size="sm" />
                      </TableCell>
                      <TableCell className="text-right">
                        {trade.pnl != null ? (
                          <span className={trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                            {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(0)}
                          </span>
                        ) : (
                          <span className="text-[#6B7280]">-</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>

        {/* Pending Signals */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] overflow-hidden">
          <div className="px-4 py-3 border-b border-white/[0.06]">
            <h3 className="text-sm font-semibold text-[#F3F4F6]">Pending Signals</h3>
          </div>
          <ScrollArea className="h-[280px]">
            <div className="p-3 space-y-2">
              {pendingSignals.length === 0 ? (
                <div className="text-center text-[#6B7280] py-8">
                  No pending signals
                </div>
              ) : (
                pendingSignals.map((signal) => (
                  <div
                    key={signal.id}
                    className="p-3 rounded-lg bg-[#1E2129] border border-white/[0.04] hover:border-cyan-500/30 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-[#F3F4F6]">{signal.asset}</span>
                      <span className="text-xs text-[#A1A7B3]">{signal.strategy}</span>
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`
                          text-xs px-1.5 py-0.5 rounded
                          ${signal.signalValue === 1 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}
                        `}>
                          {signal.signalValue === 1 ? 'BUY' : 'SELL'}
                        </span>
                        <span className="text-xs text-[#A1A7B3]">{signal.regime}</span>
                      </div>
                      <span className="text-sm font-medium text-cyan-400">
                        {(signal.confidence * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Approval Trend */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Approval Trend (7-day)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={approvalTrend.length > 0 ? approvalTrend : [{date: new Date().toISOString(), approvalRate: 0}]}>
              <defs>
                <linearGradient id="approvalGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22D3EE" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#22D3EE" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => {
                  const dt = safeDate(d);
                  return dt ? format(dt, 'MM/dd') : '--';
                }}
                stroke="#6B7280"
                fontSize={10}
              />
              <YAxis stroke="#6B7280" fontSize={10} domain={[0, 100]} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#14161C',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '8px',
                }}
                labelStyle={{ color: '#A1A7B3' }}
                formatter={(value: number) => [`${Number(value).toFixed(1)}%`, 'Approval Rate']}
              />
              <Area
                type="monotone"
                dataKey="approvalRate"
                stroke="#22D3EE"
                fill="url(#approvalGradient)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Approval Distribution */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Approval Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <RePieChart>
              <Pie
                data={approvalPieData}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
              >
                {approvalPieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#14161C',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '8px',
                }}
                formatter={(value: number) => [`${Number(value).toFixed(1)}%`, '']}
              />
            </RePieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-2">
            {approvalPieData.map((item) => (
              <div key={item.name} className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                <span className="text-xs text-[#A1A7B3]">{item.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Equity Curve */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Equity Curve</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={equityCurve.length > 0 ? equityCurve : [{date: new Date().toISOString(), equity: 0}]}>
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#34D399" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#34D399" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => {
                  const dt = safeDate(d);
                  return dt ? format(dt, 'MM/dd') : '--';
                }}
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
                formatter={(v: number) => [`${v.toFixed(2)}`, 'Equity']}
                labelFormatter={(l) => {
                  const dt = safeDate(l);
                  return dt ? format(dt, 'MM/dd/yyyy') : l;
                }}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#34D399"
                fill="url(#equityGradient)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Exposure by Asset */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Exposure by Asset</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={exposureData.length > 0 ? exposureData : []}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="asset"
                tickFormatter={(a) => a?.split('_')[0] || a}
                stroke="#6B7280"
                fontSize={9}
              />
              <YAxis stroke="#6B7280" fontSize={10} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#14161C',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '8px',
                }}
              />
              <Bar dataKey="long" stackId="a" fill="#34D399" />
              <Bar dataKey="short" stackId="a" fill="#F87171" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Performance Attribution */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Performance Attribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={attribution.length > 0 ? attribution : []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" horizontal={false} />
              <XAxis type="number" stroke="#6B7280" fontSize={10} />
              <YAxis
                dataKey="layer"
                type="category"
                stroke="#6B7280"
                fontSize={9}
                width={100}
                tickFormatter={(l) => l?.split(' ')[0] || l}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#14161C',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '8px',
                }}
                formatter={(v: number) => [`${v.toFixed(1)}%`, 'Contribution']}
              />
              <Bar dataKey="contribution" fill="#22D3EE" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Regime Heatmap */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Current Regimes</h3>
          <div className="grid grid-cols-2 gap-2">
            {regimeData.length === 0 ? (
              <div className="col-span-2 text-center text-[#6B7280] py-4">
                No regime data available
              </div>
            ) : (
              regimeData.map((regime) => (
                <div
                  key={regime.asset}
                  className="p-2 rounded-lg bg-[#1E2129] border border-white/[0.04]"
                >
                  <div className="text-xs font-medium text-[#F3F4F6]">{regime.asset}</div>
                  <div className={`
                    text-[10px] mt-1 px-1.5 py-0.5 rounded inline-block
                    ${(regime.currentRegime || '').includes('Trending') 
                      ? 'bg-emerald-500/10 text-emerald-400' 
                      : 'bg-amber-500/10 text-amber-400'}
                  `}>
                    {regime.currentRegime}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
