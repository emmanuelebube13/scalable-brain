import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { format } from 'date-fns';
import * as api from '@/services/api';
import { GitBranch, TrendingUp, Activity, Clock } from 'lucide-react';
import type { Asset, RegimeData, RegimePerformance, RegimeType } from '@/types';

const parseDates = (obj: any): any => {
  if (Array.isArray(obj)) return obj.map(parseDates);
  if (obj && typeof obj === 'object') {
    const out = { ...obj };
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
};

const regimeColors: Record<RegimeType, { bg: string; text: string; border: string }> = {
  Trending_HighVol: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
  Trending_LowVol: { bg: 'bg-emerald-500/5', text: 'text-emerald-300', border: 'border-emerald-500/10' },
  Ranging_HighVol: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
  Ranging_LowVol: { bg: 'bg-amber-500/5', text: 'text-amber-300', border: 'border-amber-500/10' },
};

const defaultRegimeColor = { bg: 'bg-[#1E2129]', text: 'text-[#A1A7B3]', border: 'border-white/[0.06]' };

export function Regimes() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  const [regimeData, setRegimeData] = useState<RegimeData[]>([]);
  const [regimePerformance, setRegimePerformance] = useState<RegimePerformance[]>([]);
  const [priceData, setPriceData] = useState<any[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.fetchCurrentRegimes();
        setRegimeData(parseDates(data));
      } catch (err) {
        console.error('Failed to fetch regimes:', err);
        setRegimeData([]);
      }
      try {
        const perf = await api.fetchRegimePerformance();
        setRegimePerformance(parseDates(perf));
      } catch (err) {
        console.error('Failed to fetch regime performance:', err);
        setRegimePerformance([]);
      }
      try {
        const fetchedAssets = await api.fetchAssets();
        setAssets(parseDates(fetchedAssets));

        if (fetchedAssets && fetchedAssets.length > 0 && fetchedAssets[0].priceHistory) {
          const priceHist = (fetchedAssets[0] as any).priceHistory.map((p: any, i: number) => ({
            ...p,
            regime: i < 10 ? 'Trending_HighVol' : i < 20 ? 'Ranging_LowVol' : 'Trending_LowVol',
          }));
          setPriceData(priceHist);
        }
      } catch (err) {
        console.error('Failed to fetch assets:', err);
        setAssets([]);
        setPriceData([]);
      }
    };
    load();
  }, []);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Regime cards stagger
      gsap.fromTo(
        cardsRef.current?.children || [],
        { y: 20, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.35, stagger: 0.08, ease: 'power2.out' }
      );

      // Timeline draw
      gsap.fromTo(
        timelineRef.current,
        { opacity: 0 },
        { opacity: 1, duration: 0.5, delay: 0.3 }
      );
    });

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef} className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <GitBranch className="w-6 h-6 text-amber-400" />
        <h2 className="text-xl font-semibold text-[#F3F4F6]">Regime Analysis</h2>
      </div>

      {/* Current Regime Cards */}
      <div>
        <h3 className="text-sm font-semibold text-[#A1A7B3] mb-3 uppercase tracking-wider">
          Current Regime by Asset
        </h3>
        <div ref={cardsRef} className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {regimeData.map((regime) => {
            const colors = regimeColors[regime.currentRegime] || defaultRegimeColor;
            return (
              <div
                key={regime.asset}
                className={`
                  p-3 rounded-xl border ${colors.border} ${colors.bg}
                  hover:scale-[1.02] transition-transform cursor-pointer
                `}
              >
                <div className="text-xs font-medium text-[#A1A7B3]">{regime.asset}</div>
                <div className={`mt-1 text-sm font-semibold ${colors.text}`}>
                  {regime.currentRegime.replace('_', ' ')}
                </div>
                <div className="mt-2 flex items-center gap-1 text-[10px] text-[#6B7280]">
                  <Clock className="w-3 h-3" />
                  {regime.duration}
                </div>
                <div className="mt-1 text-[10px] text-[#6B7280]">
                  ATR: {regime.atr.toFixed(4)}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Regime Performance Table */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] overflow-hidden">
          <div className="px-4 py-3 border-b border-white/[0.06]">
            <h3 className="text-sm font-semibold text-[#F3F4F6]">Regime Performance</h3>
          </div>
          <div className="h-[300px] overflow-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-white/[0.06] hover:bg-transparent">
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Regime</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Signals</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Approval</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Win Rate</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Expectancy</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Avg Hold</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {regimePerformance.map((perf) => {
                  const colors = regimeColors[perf.regime] || defaultRegimeColor;
                  return (
                    <TableRow
                      key={perf.regime}
                      className="border-white/[0.06] text-[#F3F4F6]"
                    >
                      <TableCell>
                        <span className={`
                          px-2 py-1 rounded text-xs font-medium ${colors.bg} ${colors.text}
                        `}>
                          {perf.regime.replace('_', ' ')}
                        </span>
                      </TableCell>
                      <TableCell className="text-right text-xs">{perf.signalCount}</TableCell>
                      <TableCell className="text-right text-xs">{perf.approvalRate}%</TableCell>
                      <TableCell className={`
                        text-right text-xs font-medium
                        ${perf.winRate >= 55 ? 'text-emerald-400' : perf.winRate >= 45 ? 'text-amber-400' : 'text-red-400'}
                      `}>
                        {perf.winRate}%
                      </TableCell>
                      <TableCell className={`
                        text-right text-xs font-medium
                        ${perf.avgExpectancyR >= 0.2 ? 'text-emerald-400' : perf.avgExpectancyR >= 0 ? 'text-amber-400' : 'text-red-400'}
                      `}>
                        {perf.avgExpectancyR >= 0 ? '+' : ''}{perf.avgExpectancyR.toFixed(2)}R
                      </TableCell>
                      <TableCell className="text-right text-xs text-[#A1A7B3]">{perf.avgHold}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>

        {/* Regime Transition Timeline */}
        <div ref={timelineRef} className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Recent Regime Transitions</h3>
          <div className="space-y-3">
              {(regimeData[0]?.transitions || []).map((transition, index) => {
              const fromColors = regimeColors[transition.from] || defaultRegimeColor;
              const toColors = regimeColors[transition.to] || defaultRegimeColor;
              return (
                <div key={index} className="flex items-center gap-3">
                  <div className="w-16 text-[10px] text-[#6B7280] font-mono">
                    {format(transition.timestamp, 'MM/dd HH:mm')}
                  </div>
                  <div className="flex items-center gap-2 flex-1">
                    <span className={`
                      px-2 py-0.5 rounded text-[10px] ${fromColors.bg} ${fromColors.text}
                    `}>
                      {transition.from.replace('_', ' ')}
                    </span>
                    <TrendingUp className="w-3 h-3 text-[#6B7280]" />
                    <span className={`
                      px-2 py-0.5 rounded text-[10px] ${toColors.bg} ${toColors.text}
                    `}>
                      {transition.to.replace('_', ' ')}
                    </span>
                  </div>
                  <div className="text-[10px] text-[#6B7280]">EUR/USD</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Price + Regime Bands Chart */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Price with Regime Bands</h3>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={priceData}>
              <defs>
                <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22D3EE" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#22D3EE" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(d) => format(new Date(d), 'HH:mm')}
                stroke="#6B7280"
                fontSize={10}
              />
              <YAxis stroke="#6B7280" fontSize={10} domain={['dataMin', 'dataMax']} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#14161C',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '8px',
                }}
                formatter={(v: number) => [v.toFixed(5), 'Price']}
              />
              <Area
                type="monotone"
                dataKey="close"
                stroke="#22D3EE"
                fill="url(#priceGradient)"
                strokeWidth={2}
              />
              {/* Regime change markers */}
              <ReferenceLine x={priceData[10]?.timestamp?.getTime()} stroke="#F59E0B" strokeDasharray="3 3" />
              <ReferenceLine x={priceData[20]?.timestamp?.getTime()} stroke="#34D399" strokeDasharray="3 3" />
            </AreaChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-2">
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-[10px] text-[#A1A7B3]">Trending</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-400" />
              <span className="text-[10px] text-[#A1A7B3]">Ranging</span>
            </div>
          </div>
        </div>

        {/* Regime Dwell Time Heatmap */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Regime Dwell Time (%)</h3>
          <div className="grid grid-cols-5 gap-2">
            <div className="text-[10px] text-[#6B7280]"></div>
            {['Trend_HV', 'Trend_LV', 'Range_HV', 'Range_LV'].map((r) => (
              <div key={r} className="text-[10px] text-[#A1A7B3] text-center">{r}</div>
            ))}
            {assets.slice(0, 4).map((asset) => (
              <div key={asset.symbol} className="contents">
                <div
                  className="text-[10px] text-[#A1A7B3] text-right pr-2 py-1 flex items-center justify-end"
                >
                  {asset.symbol.split('_')[0]}
                </div>
                {[25, 35, 20, 20].map((value, i) => (
                  <div
                    key={i}
                    className="aspect-square rounded flex items-center justify-center text-[10px] font-medium"
                    style={{
                      backgroundColor: `rgba(34, 211, 238, ${0.1 + (value / 100) * 0.5})`,
                      color: value > 30 ? '#F3F4F6' : '#A1A7B3',
                    }}
                  >
                    {value}%
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Key Insights */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-medium text-emerald-400">Best Regime</span>
          </div>
          <p className="mt-2 text-xs text-[#A1A7B3]">
            Trending_HighVol shows 65% win rate with +0.35R expectancy
          </p>
        </div>
        <div className="bg-amber-500/5 border border-amber-500/10 rounded-xl p-4">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-medium text-amber-400">Avoid</span>
          </div>
          <p className="mt-2 text-xs text-[#A1A7B3]">
            Ranging_HighVol has negative expectancy (-0.02R), consider filtering
          </p>
        </div>
        <div className="bg-cyan-500/5 border border-cyan-500/10 rounded-xl p-4">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-cyan-400" />
            <span className="text-sm font-medium text-cyan-400">Hold Time</span>
          </div>
          <p className="mt-2 text-xs text-[#A1A7B3]">
            Trending regimes average 12-18h holds vs 6-9h for ranging
          </p>
        </div>
      </div>
    </div>
  );
}
