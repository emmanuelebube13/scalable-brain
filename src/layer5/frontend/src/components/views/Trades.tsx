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
import { Input } from '@/components/ui/input';
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
import type { Trade } from '@/types';
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
} from 'lucide-react';

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
  const [expandedTrade, setExpandedTrade] = useState<string | null>(null);
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
  }, []);

  useEffect(() => {
    const ctx = gsap.context(() => {
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
    if (filters.asset && !trade.asset.toLowerCase().includes(filters.asset.toLowerCase())) return false;
    if (filters.strategy && !trade.strategy.toLowerCase().includes(filters.strategy.toLowerCase())) return false;
    if (filters.status && filters.status !== 'all' && trade.status !== filters.status) return false;
    if (filters.outcome && filters.outcome !== 'all' && trade.outcome !== filters.outcome) return false;
    return true;
  });

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
          <Input
            placeholder="Filter by asset..."
            value={filters.asset}
            onChange={(e) => setFilters({ ...filters, asset: e.target.value })}
            className="bg-[#1E2129] border-white/[0.06] text-[#F3F4F6] h-9"
          />
        </div>
        <div className="flex items-center gap-2 flex-1 min-w-[200px]">
          <Filter className="w-4 h-4 text-[#6B7280]" />
          <Input
            placeholder="Filter by strategy..."
            value={filters.strategy}
            onChange={(e) => setFilters({ ...filters, strategy: e.target.value })}
            className="bg-[#1E2129] border-white/[0.06] text-[#F3F4F6] h-9"
          />
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
