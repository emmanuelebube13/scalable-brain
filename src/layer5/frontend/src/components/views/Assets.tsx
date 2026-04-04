import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { Sparkline } from '@/components/charts/Sparkline';
import { CorrelationHeatmap } from '@/components/charts/CorrelationHeatmap';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
import * as mockData from '@/services/mockData';
import * as api from '@/services/api';
import type { Asset } from '@/types';
import {
  TrendingUp,
  DollarSign,
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

export function Assets() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);

  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);

  useEffect(() => {
    api.fetchAssets()
      .then((data) => setAssets(parseDates(data)))
      .catch(() => setAssets(mockData.getAssets()));
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
  }, [assets]);

  const getRegimeColor = (regime: string) => {
    if (regime.includes('Trending')) return 'text-emerald-400 bg-emerald-500/10';
    return 'text-amber-400 bg-amber-500/10';
  };

  return (
    <div ref={containerRef} className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <TrendingUp className="w-6 h-6 text-cyan-400" />
        <h2 className="text-xl font-semibold text-[#F3F4F6]">Asset Performance</h2>
      </div>

      {/* Asset Cards Grid */}
      <div ref={cardsRef} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {assets.map((asset) => (
          <div
            key={asset.id}
            onClick={() => setSelectedAsset(asset)}
            className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4 cursor-pointer card-hover"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="text-lg font-semibold text-[#F3F4F6]">{asset.name}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-sm text-[#F3F4F6]">{asset.currentPrice.toFixed(5)}</span>
                  <span className={`text-xs ${asset.change24hPct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {asset.change24hPct >= 0 ? '+' : ''}{asset.change24hPct.toFixed(2)}%
                  </span>
                </div>
              </div>
              <span className={`text-[10px] px-2 py-1 rounded ${getRegimeColor(asset.currentRegime)}`}>
                {asset.currentRegime.replace('_', ' ')}
              </span>
            </div>

            {/* Mini Chart */}
            <div className="h-12 mb-3">
              <Sparkline
                data={asset.priceHistory.map((p) => p.close)}
                width={240}
                height={48}
                color={asset.change24hPct >= 0 ? '#34D399' : '#F87171'}
                animated
              />
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-[#1E2129] rounded-lg p-2">
                <div className="text-[10px] text-[#6B7280] mb-0.5">ATR</div>
                <p className="text-xs font-medium text-[#F3F4F6]">{asset.atr.toFixed(4)}</p>
              </div>
              <div className="bg-[#1E2129] rounded-lg p-2">
                <div className="text-[10px] text-[#6B7280] mb-0.5">Win Rate</div>
                <p className={`text-xs font-medium ${asset.winRate >= 55 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {asset.winRate.toFixed(1)}%
                </p>
              </div>
              <div className="bg-[#1E2129] rounded-lg p-2">
                <div className="text-[10px] text-[#6B7280] mb-0.5">Open Pos</div>
                <p className="text-xs font-medium text-[#F3F4F6]">{asset.openPositions}</p>
              </div>
              <div className="bg-[#1E2129] rounded-lg p-2">
                <div className="text-[10px] text-[#6B7280] mb-0.5">Max DD</div>
                <p className="text-xs font-medium text-red-400">-{asset.maxDrawdown.toFixed(1)}%</p>
              </div>
            </div>

            {/* Footer */}
            <div className="mt-3 flex items-center justify-between text-[10px] text-[#6B7280]">
              <span>Regime: {asset.regimeDuration}</span>
              <span>Corr: {(asset.correlationToPortfolio * 100).toFixed(0)}%</span>
            </div>
          </div>
        ))}
      </div>

      {/* Asset Detail Dialog */}
      <Dialog open={!!selectedAsset} onOpenChange={() => setSelectedAsset(null)}>
        <DialogContent className="max-w-5xl bg-[#14161C] border-white/[0.06] text-[#F3F4F6]">
          {selectedAsset && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <DollarSign className="w-5 h-5 text-cyan-400" />
                  {selectedAsset.name}
                  <span className={`text-sm px-2 py-0.5 rounded ${getRegimeColor(selectedAsset.currentRegime)}`}>
                    {selectedAsset.currentRegime.replace('_', ' ')}
                  </span>
                </DialogTitle>
              </DialogHeader>

              <div className="space-y-6 mt-4">
                {/* Price Header */}
                <div className="flex items-center gap-6">
                  <div>
                    <div className="text-[10px] text-[#6B7280] uppercase">Current Price</div>
                    <div className="text-2xl font-bold text-[#F3F4F6]">{selectedAsset.currentPrice.toFixed(5)}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[#6B7280] uppercase">24h Change</div>
                    <div className={`text-xl font-bold ${selectedAsset.change24hPct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {selectedAsset.change24hPct >= 0 ? '+' : ''}{selectedAsset.change24hPct.toFixed(2)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[#6B7280] uppercase">ATR (14d)</div>
                    <div className="text-xl font-bold text-[#F3F4F6]">{selectedAsset.atr.toFixed(4)}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[#6B7280] uppercase">Open Positions</div>
                    <div className="text-xl font-bold text-[#F3F4F6]">{selectedAsset.openPositions}</div>
                  </div>
                </div>

                {/* Price Chart */}
                <div className="bg-[#0B0C0F] rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-[#F3F4F6] mb-3">Price History with Signal Markers</h4>
                  <ResponsiveContainer width="100%" height={250}>
                    <AreaChart data={selectedAsset.priceHistory}>
                      <defs>
                        <linearGradient id="assetPriceGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#22D3EE" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#22D3EE" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                      <XAxis
                        dataKey="timestamp"
                        tickFormatter={(d) => format(new Date(d), 'MM/dd')}
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
                        fill="url(#assetPriceGradient)"
                        strokeWidth={2}
                      />
                      {/* Signal markers */}
                      <ReferenceLine
                        x={selectedAsset.priceHistory[10]?.timestamp?.getTime()}
                        stroke="#34D399"
                        strokeDasharray="3 3"
                        label={{ value: 'BUY', fill: '#34D399', fontSize: 10 }}
                      />
                      <ReferenceLine
                        x={selectedAsset.priceHistory[20]?.timestamp?.getTime()}
                        stroke="#F87171"
                        strokeDasharray="3 3"
                        label={{ value: 'SELL', fill: '#F87171', fontSize: 10 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-4 gap-4">
                  <div className="bg-[#0B0C0F] rounded-lg p-3 text-center">
                    <div className="text-[10px] text-[#6B7280] uppercase mb-1">Win Rate</div>
                    <div className={`text-xl font-bold ${selectedAsset.winRate >= 55 ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {selectedAsset.winRate.toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-[#0B0C0F] rounded-lg p-3 text-center">
                    <div className="text-[10px] text-[#6B7280] uppercase mb-1">Max Drawdown</div>
                    <div className="text-xl font-bold text-red-400">
                      -{selectedAsset.maxDrawdown.toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-[#0B0C0F] rounded-lg p-3 text-center">
                    <div className="text-[10px] text-[#6B7280] uppercase mb-1">Portfolio Corr</div>
                    <div className="text-xl font-bold text-[#F3F4F6]">
                      {(selectedAsset.correlationToPortfolio * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="bg-[#0B0C0F] rounded-lg p-3 text-center">
                    <div className="text-[10px] text-[#6B7280] uppercase mb-1">Regime Duration</div>
                    <div className="text-xl font-bold text-[#F3F4F6]">{selectedAsset.regimeDuration}</div>
                  </div>
                </div>

                {/* Correlation Heatmap */}
                <div className="bg-[#0B0C0F] rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-[#F3F4F6] mb-3">Correlation to Other Assets</h4>
                  <CorrelationHeatmap
                    assets={assets.map((a) => a.symbol)}
                    correlations={Object.entries(selectedAsset.correlationToOthers).map(([asset2, corr]) => ({
                      asset1: selectedAsset.symbol,
                      asset2,
                      correlation: corr,
                    }))}
                    animated={false}
                  />
                </div>

                {/* ATR Comparison */}
                <div className="bg-[#0B0C0F] rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-[#F3F4F6] mb-3">ATR Analysis</h4>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center">
                      <div className="text-[10px] text-[#6B7280] mb-1">Current ATR</div>
                      <div className="text-lg font-bold text-cyan-400">{selectedAsset.atr.toFixed(4)}</div>
                    </div>
                    <div className="text-center">
                      <div className="text-[10px] text-[#6B7280] mb-1">14-Day Avg</div>
                      <div className="text-lg font-bold text-[#F3F4F6]">{selectedAsset.atr14DayAvg.toFixed(4)}</div>
                    </div>
                    <div className="text-center">
                      <div className="text-[10px] text-[#6B7280] mb-1">ATR Ratio</div>
                      <div className={`text-lg font-bold ${selectedAsset.atr / selectedAsset.atr14DayAvg > 1.2 ? 'text-amber-400' : 'text-emerald-400'}`}>
                        {(selectedAsset.atr / selectedAsset.atr14DayAvg).toFixed(2)}x
                      </div>
                    </div>
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
