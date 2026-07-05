import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { StatusBadge } from '@/components/ui-custom/StatusBadge';
import { format } from 'date-fns';
import * as api from '@/services/api';
import type { Trade, OpenPosition } from '@/types';
import {
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  Download,
  Brain,
  DollarSign,
  Clock,
  Target,
  Shield,
  TrendingUp,
  BarChart3,
  PieChart,
} from 'lucide-react';
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
} from 'recharts';

function safeToDate(value: unknown): Date | null {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  if (typeof value === 'string') {
    const normalized = value.includes('T') ? value : value.replace(' ', 'T');
    const d = new Date(normalized);
    if (!Number.isNaN(d.getTime())) return d;
  }
  if (typeof value === 'number') {
    const d = new Date(value);
    if (!Number.isNaN(d.getTime())) return d;
  }
  return null;
}

function safeFmtDate(value: unknown, fmt = 'MM/dd HH:mm'): string {
  const d = safeToDate(value);
  if (!d) return 'N/A';
  try {
    return format(d, fmt);
  } catch {
    return 'N/A';
  }
}

function safeNum(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

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

export function Trades() {
  const containerRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<HTMLDivElement>(null);

  const [trades, setTrades] = useState<Trade[]>([]);
  const [openPositions, setOpenPositions] = useState<OpenPosition[]>([]);
  const [expandedTrade, setExpandedTrade] = useState<string | null>(null);
  const [assetOptions, setAssetOptions] = useState<string[]>([]);
  const [strategyOptions, setStrategyOptions] = useState<string[]>([]);
  const [filters, setFilters] = useState({
    asset: '',
    strategy: '',
    status: '',
    outcome: '',
  });

  useEffect(() => {
    api.fetchTrades(20)
      .then((data) => setTrades(parseDates(data)))
      .catch((err) => {
        console.error('Failed to fetch trades:', err);
        setTrades([]);
      });

    api.fetchOpenPositions(100)
      .then((data) => setOpenPositions(parseDates(data)))
      .catch((err) => {
        console.error('Failed to fetch open positions:', err);
        setOpenPositions([]);
      });

    api.fetchAssets()
      .then((data) => setAssetOptions(Array.from(new Set(data.map((a) => a.symbol))).sort()))
      .catch((err) => {
        console.error('Failed to fetch assets:', err);
        setAssetOptions([]);
      });

    api.fetchStrategies()
      .then((data) => setStrategyOptions(Array.from(new Set(data.map((s) => s.name))).sort()))
      .catch((err) => {
        console.error('Failed to fetch strategies:', err);
        setStrategyOptions([]);
      });
  }, []);

  useEffect(() => {
    const ctx = gsap.context(() => {
      if (!tableRef.current) return;

      gsap.fromTo(
        tableRef.current,
        { y: 20, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.35, ease: 'power2.out' }
      );
    });

    return () => ctx.revert();
  }, []);

  const toggleExpand = (tradeId: string) => {
    setExpandedTrade(expandedTrade === tradeId ? null : tradeId);
  };

  const filteredTrades = trades.filter((trade) => {
    if (filters.asset && filters.asset !== 'all' && trade.asset !== filters.asset) return false;
    if (filters.strategy && filters.strategy !== 'all' && trade.strategy !== filters.strategy) return false;
    if (filters.status && filters.status !== 'all' && trade.status !== filters.status) return false;
    if (filters.outcome && filters.outcome !== 'all' && trade.outcome !== filters.outcome) return false;
    return true;
  });

  // Calculate trade statistics for charts
  const tradeStats = trades.reduce((acc, trade) => {
    // Asset performance
    if (!acc.assetPerf[trade.asset]) {
      acc.assetPerf[trade.asset] = { wins: 0, losses: 0, totalPnL: 0 };
    }
    if (trade.outcome === 'win') acc.assetPerf[trade.asset].wins++;
    else if (trade.outcome === 'loss') acc.assetPerf[trade.asset].losses++;
    acc.assetPerf[trade.asset].totalPnL += trade.pnl || 0;

    // Strategy performance
    if (!acc.strategyPerf[trade.strategy]) {
      acc.strategyPerf[trade.strategy] = { wins: 0, losses: 0 };
    }
    if (trade.outcome === 'win') acc.strategyPerf[trade.strategy].wins++;
    else if (trade.outcome === 'loss') acc.strategyPerf[trade.strategy].losses++;

    // Outcome distribution
    if (trade.outcome) {
      acc.outcomes[trade.outcome] = (acc.outcomes[trade.outcome] || 0) + 1;
    }

    return acc;
  }, { assetPerf: {} as Record<string, { wins: number; losses: number; totalPnL: number }>, strategyPerf: {} as Record<string, { wins: number; losses: number }>, outcomes: {} as Record<string, number> });

  const assetChartData = Object.entries(tradeStats.assetPerf).map(([asset, data]) => ({
    asset,
    winRate: data.wins + data.losses > 0 ? (data.wins / (data.wins + data.losses)) * 100 : 0,
    totalPnL: data.totalPnL,
  }));

  const outcomeChartData = [
    { name: 'Win', value: tradeStats.outcomes.win || 0, color: '#34D399' },
    { name: 'Loss', value: tradeStats.outcomes.loss || 0, color: '#F87171' },
    { name: 'Breakeven', value: tradeStats.outcomes.breakeven || 0, color: '#6B7280' },
  ].filter(d => d.value > 0);

  const exportToCSV = () => {
    const headers = ['ID', 'Time', 'Asset', 'Strategy', 'Entry', 'Exit', 'SL', 'TP', 'Regime', 'Confidence', 'Status', 'P&L'];
    const rows = filteredTrades.map((t) => [
      t.id,
        safeFmtDate(t.timestamp, 'yyyy-MM-dd HH:mm:ss'),
      t.asset,
      t.strategy,
        safeNum(t.entryPrice, 0),
      t.exitPrice || '',
        safeNum(t.stopLoss, 0),
        safeNum(t.takeProfit, 0),
      t.regime,
        safeNum(t.confidence, 0),
      t.status,
      t.pnl || '',
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trades_${format(new Date(), 'yyyyMMdd_HHmmss')}.csv`;
    a.click();
  };

  return (
    <div ref={containerRef} className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <TrendingUp className="w-6 h-6 text-cyan-400" />
          <h2 className="text-xl font-semibold text-[#F3F4F6]">Trade Blotter</h2>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={exportToCSV}
          className="border-white/[0.06] text-[#A1A7B3] hover:text-[#F3F4F6]"
        >
          <Download className="w-4 h-4 mr-2" />
          Export CSV
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 p-4 bg-[#14161C] rounded-xl border border-white/[0.06]">
        <div className="flex items-center gap-2 flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-[#6B7280]" />
          <Select
            value={filters.asset || 'all'}
            onValueChange={(v) => setFilters({ ...filters, asset: v === 'all' ? '' : v })}
          >
            <SelectTrigger className="bg-[#1E2129] border-white/[0.06] text-[#F3F4F6] h-9">
              <SelectValue placeholder="Filter by asset" />
            </SelectTrigger>
            <SelectContent className="bg-[#14161C] border-white/[0.06]">
              <SelectItem value="all">All Assets</SelectItem>
              {assetOptions.map((asset) => (
                <SelectItem key={asset} value={asset}>{asset}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2 flex-1 min-w-[200px]">
          <Filter className="w-4 h-4 text-[#6B7280]" />
          <Select
            value={filters.strategy || 'all'}
            onValueChange={(v) => setFilters({ ...filters, strategy: v === 'all' ? '' : v })}
          >
            <SelectTrigger className="bg-[#1E2129] border-white/[0.06] text-[#F3F4F6] h-9">
              <SelectValue placeholder="Filter by strategy" />
            </SelectTrigger>
            <SelectContent className="bg-[#14161C] border-white/[0.06]">
              <SelectItem value="all">All Strategies</SelectItem>
              {strategyOptions.map((strategy) => (
                <SelectItem key={strategy} value={strategy}>{strategy}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Select
          value={filters.status}
          onValueChange={(v) => setFilters({ ...filters, status: v })}
        >
          <SelectTrigger className="w-[140px] bg-[#1E2129] border-white/[0.06] text-[#F3F4F6] h-9">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent className="bg-[#14161C] border-white/[0.06]">
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="vetoed">Vetoed</SelectItem>
            <SelectItem value="executed">Executed</SelectItem>
            <SelectItem value="closed">Closed</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={filters.outcome}
          onValueChange={(v) => setFilters({ ...filters, outcome: v })}
        >
          <SelectTrigger className="w-[140px] bg-[#1E2129] border-white/[0.06] text-[#F3F4F6] h-9">
            <SelectValue placeholder="Outcome" />
          </SelectTrigger>
          <SelectContent className="bg-[#14161C] border-white/[0.06]">
            <SelectItem value="all">All Outcomes</SelectItem>
            <SelectItem value="win">Win</SelectItem>
            <SelectItem value="loss">Loss</SelectItem>
            <SelectItem value="breakeven">Breakeven</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Trade Performance Summary */}
      {trades.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-[#F3F4F6]">Performance by Asset</h3>
            </div>
            {assetChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={assetChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                  <XAxis dataKey="asset" stroke="#6B7280" fontSize={10} />
                  <YAxis stroke="#6B7280" fontSize={10} tickFormatter={(v) => `${v.toFixed(0)}%`} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#14161C',
                      border: '1px solid rgba(255,255,255,0.06)',
                      borderRadius: '8px',
                    }}
                    formatter={(v: number, name: string) => [
                      name === 'winRate' ? `${v.toFixed(1)}%` : `$${v.toFixed(2)}`,
                      name === 'winRate' ? 'Win Rate' : 'Total P&L'
                    ]}
                  />
                  <Bar dataKey="winRate" fill="#22D3EE" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[180px] flex items-center justify-center text-xs text-[#6B7280]">
                No trade data available
              </div>
            )}
          </div>

          <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
            <div className="flex items-center gap-2 mb-4">
              <PieChart className="w-4 h-4 text-violet-400" />
              <h3 className="text-sm font-semibold text-[#F3F4F6]">Outcome Distribution</h3>
            </div>
            {outcomeChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <RePieChart>
                  <Pie
                    data={outcomeChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {outcomeChartData.map((entry, index) => (
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
            ) : (
              <div className="h-[180px] flex items-center justify-center text-xs text-[#6B7280]">
                No outcome data available
              </div>
            )}
            <div className="flex justify-center gap-4 mt-2">
              {outcomeChartData.map((item) => (
                <div key={item.name} className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                  <span className="text-xs text-[#A1A7B3]">{item.name}: {item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Open Positions */}
      <div className="bg-[#14161C] rounded-xl border border-white/[0.06] overflow-hidden">
        <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[#F3F4F6]">Open Positions</h3>
          <span className="text-xs text-[#A1A7B3]">
            {openPositions[0]?.source === 'oanda' ? 'Source: OANDA' : 'Source: System'}
          </span>
        </div>
        <div className="p-4">
          {openPositions.length === 0 ? (
            <p className="text-xs text-[#A1A7B3]">No open positions currently reported.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {openPositions.map((pos, idx) => {
                const pnl = safeNum(pos.unrealizedPnl, 0);
                return (
                  <div key={`${pos.instrument}-${pos.side}-${idx}`} className="rounded-lg border border-white/[0.06] bg-[#0F1117] p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-[#F3F4F6]">{pos.instrument}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${pos.side === 'long' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                        {pos.side.toUpperCase()}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-[#A1A7B3] space-y-1">
                      <div className="flex justify-between"><span>Units</span><span className="text-[#F3F4F6]">{safeNum(pos.units, 0).toLocaleString()}</span></div>
                      <div className="flex justify-between"><span>Avg Price</span><span className="text-[#F3F4F6]">{safeNum(pos.avgPrice, 0).toFixed(5)}</span></div>
                      <div className="flex justify-between"><span>Unrealized P&L</span><span className={pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>{pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</span></div>
                      <div className="flex justify-between"><span>Trade IDs</span><span className="text-[#F3F4F6]">{(pos.tradeIds || []).slice(0, 2).join(', ') || '-'}</span></div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Trades Table */}
      <div ref={tableRef} className="bg-[#14161C] rounded-xl border border-white/[0.06] overflow-hidden">
        <ScrollArea className="h-[600px]">
          <Table>
            <TableHeader className="sticky top-0 bg-[#14161C] z-10">
              <TableRow className="border-white/[0.06] hover:bg-transparent">
                <TableHead className="w-8"></TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Time</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Asset</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Strategy</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Entry</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">SL</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">TP</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Regime</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Conf</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Status</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">P&L</TableHead>
                <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Outcome</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredTrades.map((trade) => (
                <div key={trade.id}>
                  <TableRow
                    className="border-white/[0.06] text-[#F3F4F6] cursor-pointer hover:bg-white/[0.02]"
                    onClick={() => toggleExpand(trade.id)}
                  >
                    <TableCell>
                      {expandedTrade === trade.id ? (
                        <ChevronUp className="w-4 h-4 text-[#6B7280]" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-[#6B7280]" />
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {safeFmtDate(trade.timestamp, 'MM/dd HH:mm')}
                    </TableCell>
                    <TableCell className="text-xs font-medium">{trade.asset}</TableCell>
                    <TableCell className="text-xs text-[#A1A7B3]">{trade.strategy}</TableCell>
                    <TableCell className="text-right text-xs font-mono">
                      {safeNum(trade.entryPrice, 0).toFixed(5)}
                    </TableCell>
                    <TableCell className="text-right text-xs font-mono text-red-400">
                      {safeNum(trade.stopLoss, 0).toFixed(5)}
                    </TableCell>
                    <TableCell className="text-right text-xs font-mono text-emerald-400">
                      {safeNum(trade.takeProfit, 0).toFixed(5)}
                    </TableCell>
                    <TableCell>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1E2129] text-[#A1A7B3]">
                        {(trade.regime || 'N/A').replace('_', ' ')}
                      </span>
                    </TableCell>
                    <TableCell className="text-right text-xs">
                      <span className={safeNum(trade.confidence, 0) >= 0.535 ? 'text-emerald-400' : 'text-red-400'}>
                        {(safeNum(trade.confidence, 0) * 100).toFixed(1)}%
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={trade.status} size="sm" />
                    </TableCell>
                    <TableCell className="text-right">
                      {trade.pnl != null ? (
                        <span className={safeNum(trade.pnl, 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                          {safeNum(trade.pnl, 0) >= 0 ? '+' : ''}{safeNum(trade.pnl, 0).toFixed(0)}
                        </span>
                      ) : (
                        <span className="text-[#6B7280]">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {trade.outcome && <StatusBadge status={trade.outcome} size="sm" />}
                    </TableCell>
                  </TableRow>

                  {/* Expanded Forensics */}
                  {expandedTrade === trade.id && trade.forensics && (
                    <TableRow className="border-white/[0.06] bg-[#0B0C0F]">
                      <TableCell colSpan={12} className="p-0">
                        <div className="p-4 space-y-4">
                          {/* Market Context */}
                          <div className="grid grid-cols-4 gap-4">
                            <div className="bg-[#14161C] rounded-lg p-3">
                              <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
                                <Target className="w-4 h-4" />
                                <span className="text-xs uppercase">Market Context</span>
                              </div>
                              <div className="space-y-1 text-xs">
                                <div className="flex justify-between">
                                  <span className="text-[#6B7280]">ATR:</span>
                                  <span className="text-[#F3F4F6]">{trade.forensics.marketContext.atr.toFixed(4)}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-[#6B7280]">ADX:</span>
                                  <span className="text-[#F3F4F6]">{trade.forensics.marketContext.adx.toFixed(1)}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-[#6B7280]">Support:</span>
                                  <span className="text-[#F3F4F6]">{trade.forensics.marketContext.nearestSupport.toFixed(5)}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-[#6B7280]">Resistance:</span>
                                  <span className="text-[#F3F4F6]">{trade.forensics.marketContext.nearestResistance.toFixed(5)}</span>
                                </div>
                              </div>
                            </div>

                            {/* Technical Setup */}
                            <div className="bg-[#14161C] rounded-lg p-3">
                              <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
                                <TrendingUp className="w-4 h-4" />
                                <span className="text-xs uppercase">Technical Setup</span>
                              </div>
                              <p className="text-xs text-[#F3F4F6]">{trade.forensics.technicalSetup}</p>
                            </div>

                            {/* ML Reasoning */}
                            <div className="bg-[#14161C] rounded-lg p-3">
                              <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
                                <Brain className="w-4 h-4" />
                                <span className="text-xs uppercase">ML Reasoning</span>
                              </div>
                              <div className="space-y-1 text-xs">
                                {Object.entries(trade.forensics.mlReasoning.confidenceBreakdown).map(([key, value]) => (
                                  <div key={key} className="flex justify-between">
                                    <span className="text-[#6B7280]">{key.replace('_', ' ')}:</span>
                                    <span className="text-[#F3F4F6]">{(value * 100).toFixed(1)}%</span>
                                  </div>
                                ))}
                                <div className="flex justify-between pt-1 border-t border-white/[0.06]">
                                  <span className="text-[#6B7280]">Regime match:</span>
                                  <span className={trade.forensics.mlReasoning.regimeMatch ? 'text-emerald-400' : 'text-red-400'}>
                                    {trade.forensics.mlReasoning.regimeMatch ? 'Yes' : 'No'}
                                  </span>
                                </div>
                              </div>
                            </div>

                            {/* Execution */}
                            <div className="bg-[#14161C] rounded-lg p-3">
                              <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
                                <Shield className="w-4 h-4" />
                                <span className="text-xs uppercase">Execution</span>
                              </div>
                              <div className="space-y-1 text-xs">
                                <div className="flex justify-between">
                                  <span className="text-[#6B7280]">Fill price:</span>
                                  <span className="text-[#F3F4F6]">{trade.forensics.execution.brokerFillPrice.toFixed(5)}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-[#6B7280]">Slippage:</span>
                                  <span className={trade.forensics.execution.slippagePips >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                    {trade.forensics.execution.slippagePips >= 0 ? '+' : ''}{trade.forensics.execution.slippagePips.toFixed(1)} pips
                                  </span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-[#6B7280]">Fill time:</span>
                                  <span className="text-[#F3F4F6] font-mono">
                                    {safeFmtDate(trade.forensics.execution.fillTime, 'HH:mm:ss')}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* P&L Breakdown */}
                          <div className="bg-[#14161C] rounded-lg p-3">
                            <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
                              <DollarSign className="w-4 h-4" />
                              <span className="text-xs uppercase">P&L Breakdown</span>
                            </div>
                            <div className="grid grid-cols-4 gap-4">
                              <div>
                                <span className="text-[10px] text-[#6B7280]">Gross P&L</span>
                                <p className={trade.forensics.pnlBreakdown.gross >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                  {trade.forensics.pnlBreakdown.gross >= 0 ? '+' : ''}{trade.forensics.pnlBreakdown.gross.toFixed(2)}
                                </p>
                              </div>
                              <div>
                                <span className="text-[10px] text-[#6B7280]">Commission</span>
                                <p className="text-red-400">{trade.forensics.pnlBreakdown.commission.toFixed(2)}</p>
                              </div>
                              <div>
                                <span className="text-[10px] text-[#6B7280]">Slippage</span>
                                <p className={trade.forensics.pnlBreakdown.slippage >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                  {trade.forensics.pnlBreakdown.slippage >= 0 ? '+' : ''}{trade.forensics.pnlBreakdown.slippage.toFixed(2)}
                                </p>
                              </div>
                              <div>
                                <span className="text-[10px] text-[#6B7280]">Net P&L</span>
                                <p className={trade.forensics.pnlBreakdown.net >= 0 ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>
                                  {trade.forensics.pnlBreakdown.net >= 0 ? '+' : ''}{trade.forensics.pnlBreakdown.net.toFixed(2)}
                                </p>
                              </div>
                            </div>
                          </div>

                          {/* Exit Details */}
                          <div className="bg-[#14161C] rounded-lg p-3">
                            <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
                              <Clock className="w-4 h-4" />
                              <span className="text-xs uppercase">Exit Details</span>
                            </div>
                            <div className="flex items-center gap-4">
                              <span className="text-xs">
                                <span className="text-[#6B7280]">Reason: </span>
                                <span className="text-[#F3F4F6]">{trade.forensics.exit.reason.replace('_', ' ').toUpperCase()}</span>
                              </span>
                              <span className="text-xs text-[#6B7280]">|</span>
                              <span className="text-xs text-[#A1A7B3]">{trade.forensics.exit.details}</span>
                            </div>
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </div>
              ))}
              {filteredTrades.length === 0 && (
                <TableRow className="border-white/[0.06]">
                  <TableCell colSpan={12} className="py-10 text-center text-sm text-[#6B7280]">
                    No trade data available for the selected filters.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </ScrollArea>
      </div>
    </div>
  );
}
