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
import * as mockData from '@/services/mockData';
import * as api from '@/services/api';

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

export function Overview() {
  const containerRef = useRef<HTMLDivElement>(null);
  const kpiRef = useRef<HTMLDivElement>(null);
  const tablesRef = useRef<HTMLDivElement>(null);

  const [kpiData, setKpiData] = useState(mockData.getKPIData());
  const [liveTrades, setLiveTrades] = useState(mockData.getLiveTrades(10));
  const [pendingSignals, setPendingSignals] = useState(mockData.getPendingSignals(5));
  const [regimeData, setRegimeData] = useState(mockData.getRegimeData());
  const [approvalTrend, setApprovalTrend] = useState(mockData.getApprovalTrend());
  const [exposureData, setExposureData] = useState(mockData.getRiskMetrics().exposureByAsset);
  const [equityCurve, setEquityCurve] = useState(mockData.getEquityCurve());
  const [attribution, setAttribution] = useState(mockData.getPerformanceAttribution());

  useEffect(() => {
    api.fetchKPI()
      .then((data) => setKpiData(reviveDates(data)))
      .catch(() => setKpiData(mockData.getKPIData()));
    api.fetchTrades(10)
      .then((data) => setLiveTrades(reviveDates(data)))
      .catch(() => setLiveTrades(mockData.getLiveTrades(10)));
    api.fetchPendingSignals(5)
      .then((data) => setPendingSignals(reviveDates(data)))
      .catch(() => setPendingSignals(mockData.getPendingSignals(5)));
    api.fetchCurrentRegimes()
      .then((data) => setRegimeData(reviveDates(data)))
      .catch(() => setRegimeData(mockData.getRegimeData()));
    api.fetchApprovalTrend()
      .then((data) => setApprovalTrend(reviveDates(data)))
      .catch(() => setApprovalTrend(mockData.getApprovalTrend()));
    api.fetchRiskMetrics()
      .then((data) => setExposureData(reviveDates(data).exposureByAsset))
      .catch(() => setExposureData(mockData.getRiskMetrics().exposureByAsset));
    api.fetchAttribution()
      .then((data) => setAttribution(reviveDates(data)))
      .catch(() => setAttribution(mockData.getPerformanceAttribution()));
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
    { name: 'Vetoed', value: 100 - kpiData.approvalRate, color: '#F87171' },
  ];

  return (
    <div ref={containerRef} className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-[#F3F4F6]">Overview</h2>
        <span className="text-sm text-[#A1A7B3]">
          Last updated: {format(new Date(), 'HH:mm:ss')}
        </span>
      </div>

      {/* KPI Grid */}
      <div ref={kpiRef} className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KPICard
          title="Total Signals"
          value={kpiData.totalSignals.toLocaleString()}
          change={12.5}
          sparklineData={[100, 120, 115, 140, 135, 150, 145, 160]}
          icon={<Activity className="w-4 h-4 text-cyan-400" />}
          color="cyan"
        />
        <KPICard
          title="Approval Rate"
          value={`${kpiData.approvalRate}%`}
          change={3.2}
          sparklineData={[52, 54, 53, 56, 55, 58, 57, 58.3]}
          icon={<CheckCircle2 className="w-4 h-4 text-emerald-400" />}
          color="green"
        />
        <KPICard
          title="Avg Confidence"
          value={kpiData.avgConfidence.toFixed(3)}
          change={1.8}
          sparklineData={[0.58, 0.59, 0.60, 0.61, 0.61, 0.62, 0.62, 0.623]}
          icon={<Brain className="w-4 h-4 text-violet-400" />}
          color="violet"
        />
        <KPICard
          title="Live Positions"
          value={kpiData.livePositions}
          subtitle="Across 7 assets"
          icon={<TrendingUp className="w-4 h-4 text-cyan-400" />}
          color="cyan"
        />
        <KPICard
          title="Unrealized P&L"
          value={`+$${kpiData.unrealizedPnL.toLocaleString()}`}
          change={5.4}
          icon={<TrendingUp className="w-4 h-4 text-emerald-400" />}
          color="green"
        />
        <KPICard
          title="24h Win Rate"
          value={`${kpiData.winRate24h}%`}
          change={-2.1}
          sparklineData={[68, 67, 66, 65, 65, 64, 65, 64.7]}
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
                {liveTrades.map((trade, index) => (
                  <TableRow
                    key={trade.id}
                    className={`
                      border-white/[0.06] text-[#F3F4F6]
                      ${index === 0 ? 'animate-flash-new' : ''}
                    `}
                  >
                    <TableCell className="font-mono text-xs">
                      {format(trade.timestamp, 'HH:mm:ss')}
                    </TableCell>
                    <TableCell className="text-xs">{trade.asset}</TableCell>
                    <TableCell className="text-xs text-[#A1A7B3]">{trade.strategy}</TableCell>
                    <TableCell className="text-xs">
                      <span className={trade.confidence >= 0.535 ? 'text-emerald-400' : 'text-red-400'}>
                        {trade.confidence.toFixed(3)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={trade.status} size="sm" />
                    </TableCell>
                    <TableCell className="text-right">
                      {trade.pnl !== undefined ? (
                        <span className={trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                          {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(0)}
                        </span>
                      ) : (
                        <span className="text-[#6B7280]">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
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
              {pendingSignals.map((signal) => (
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
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* Approval Trend */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Approval Trend (7-day)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={approvalTrend}>
              <defs>
                <linearGradient id="approvalGradient" x1="0" y1="0" x2="0" y2="1">
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
              <YAxis stroke="#6B7280" fontSize={10} domain={[40, 70]} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#14161C',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '8px',
                }}
                labelStyle={{ color: '#A1A7B3' }}
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
            <AreaChart data={equityCurve}>
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#34D399" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#34D399" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => format(new Date(d), 'MM/dd')}
                stroke="#6B7280"
                fontSize={10}
              />
              <YAxis stroke="#6B7280" fontSize={10} domain={['dataMin - 1000', 'dataMax + 1000']} />
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
            <BarChart data={exposureData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="asset"
                tickFormatter={(a) => a.split('_')[0]}
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
            <BarChart data={attribution} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" horizontal={false} />
              <XAxis type="number" stroke="#6B7280" fontSize={10} />
              <YAxis
                dataKey="layer"
                type="category"
                stroke="#6B7280"
                fontSize={9}
                width={100}
                tickFormatter={(l) => l.split(' ')[0]}
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
            {regimeData.slice(0, 6).map((regime) => (
              <div
                key={regime.asset}
                className="p-2 rounded-lg bg-[#1E2129] border border-white/[0.04]"
              >
                <div className="text-xs font-medium text-[#F3F4F6]">{regime.asset}</div>
                <div className={`
                  text-[10px] mt-1 px-1.5 py-0.5 rounded inline-block
                  ${regime.currentRegime.includes('Trending') 
                    ? 'bg-emerald-500/10 text-emerald-400' 
                    : 'bg-amber-500/10 text-amber-400'}
                `}>
                  {regime.currentRegime}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
