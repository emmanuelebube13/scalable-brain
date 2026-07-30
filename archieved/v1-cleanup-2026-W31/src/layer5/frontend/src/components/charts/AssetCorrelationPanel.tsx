import { useState, useMemo, useCallback, useEffect } from 'react';
import {
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
  TrendingDown,
  Minus,
  RefreshCw,
  Filter,
  BarChart3,
} from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

// Types
export type CorrelationStrength =
  | 'strong_positive'
  | 'moderate_positive'
  | 'weak'
  | 'moderate_negative'
  | 'strong_negative';

export type CorrelationSlope = 'diverging' | 'converging';

export type CorrelationPeriod = '1W' | '1M' | '3M';

export interface CorrelatedAsset {
  symbol: string;
  correlation: number; // -1 to 1
  strength: CorrelationStrength;
  slope: CorrelationSlope;
}

export interface CorrelationData {
  baseAsset: string;
  correlatedAssets: CorrelatedAsset[];
  period: CorrelationPeriod;
  refreshTime: Date;
}

export interface AssetCorrelationPanelProps {
  baseSymbol: string;
  correlatedAssets: CorrelatedAsset[];
  onAssetToggle: (symbol: string, enabled: boolean) => void;
  onPeriodChange: (period: CorrelationPeriod) => void;
  onMinCorrelationChange: (min: number) => void;
  activeOverlays: string[];
  isLoading?: boolean;
  className?: string;
  lastUpdated?: Date;
  onRefresh?: () => void;
}

// Utility functions
function getStrengthFromCorrelation(correlation: number): CorrelationStrength {
  if (correlation >= 0.7) return 'strong_positive';
  if (correlation >= 0.3) return 'moderate_positive';
  if (correlation > -0.3) return 'weak';
  if (correlation > -0.7) return 'moderate_negative';
  return 'strong_negative';
}

function getStrengthLabel(strength: CorrelationStrength): string {
  const labels: Record<CorrelationStrength, string> = {
    strong_positive: 'Strong +',
    moderate_positive: 'Moderate +',
    weak: 'Weak',
    moderate_negative: 'Moderate -',
    strong_negative: 'Strong -',
  };
  return labels[strength];
}

function getStrengthColor(strength: CorrelationStrength): string {
  const colors: Record<CorrelationStrength, string> = {
    strong_positive: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    moderate_positive: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
    weak: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
    moderate_negative: 'bg-rose-500/10 text-rose-300 border-rose-500/20',
    strong_negative: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
  };
  return colors[strength];
}

function getCorrelationColor(correlation: number): string {
  if (correlation >= 0.7) return 'text-emerald-400';
  if (correlation >= 0.3) return 'text-emerald-300';
  if (correlation > -0.3) return 'text-slate-400';
  if (correlation > -0.7) return 'text-rose-300';
  return 'text-rose-400';
}

function getProgressBarColor(correlation: number): string {
  if (correlation >= 0.7) return 'bg-emerald-500';
  if (correlation >= 0.3) return 'bg-emerald-400';
  if (correlation > -0.3) return 'bg-slate-400';
  if (correlation > -0.7) return 'bg-rose-400';
  return 'bg-rose-500';
}

function getTrendIcon(slope: CorrelationSlope, correlation: number) {
  if (slope === 'converging') {
    return correlation >= 0 ? (
      <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
    ) : (
      <TrendingDown className="h-3.5 w-3.5 text-rose-400" />
    );
  }
  return correlation >= 0 ? (
    <TrendingDown className="h-3.5 w-3.5 text-rose-400/70" />
  ) : (
    <TrendingUp className="h-3.5 w-3.5 text-emerald-400/70" />
  );
}

function getTrendLabel(slope: CorrelationSlope, correlation: number): string {
  if (slope === 'converging') {
    return correlation >= 0 ? 'Strengthening' : 'Weakening';
  }
  return correlation >= 0 ? 'Weakening' : 'Strengthening';
}

// Mini Heatmap Component
interface MiniHeatmapProps {
  assets: CorrelatedAsset[];
  baseSymbol: string;
  minCorrelation: number;
}

function MiniHeatmap({ assets, baseSymbol, minCorrelation }: MiniHeatmapProps) {
  const filteredAssets = assets.filter(
    (a) => Math.abs(a.correlation) >= minCorrelation
  );

  const getHeatmapColor = (value: number): string => {
    if (value < 0) {
      const intensity = Math.min(Math.abs(value), 1);
      return `rgba(244, 63, 94, ${0.1 + intensity * 0.6})`;
    }
    const intensity = Math.min(value, 1);
    return `rgba(34, 211, 238, ${0.1 + intensity * 0.6})`;
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div
          className="w-8 h-8 rounded flex items-center justify-center text-[10px] font-medium"
          style={{ backgroundColor: 'rgba(34, 211, 238, 0.3)' }}
          title={baseSymbol}
        >
          {baseSymbol.slice(0, 2)}
        </div>
        <div className="flex-1 flex gap-1">
          {filteredAssets.slice(0, 8).map((asset) => (
            <div
              key={asset.symbol}
              className="flex-1 aspect-square rounded flex items-center justify-center text-[9px] font-medium cursor-pointer transition-transform hover:scale-110"
              style={{ backgroundColor: getHeatmapColor(asset.correlation) }}
              title={`${asset.symbol}: ${(asset.correlation * 100).toFixed(1)}%`}
            >
              {asset.symbol.slice(0, 2)}
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span>Negative</span>
        <div className="flex gap-0.5">
          {[-1, -0.5, 0, 0.5, 1].map((v) => (
            <div
              key={v}
              className="w-4 h-1.5 rounded-sm"
              style={{ backgroundColor: getHeatmapColor(v) }}
            />
          ))}
        </div>
        <span>Positive</span>
      </div>
    </div>
  );
}

// Progress Bar Component
function CorrelationProgressBar({ value }: { value: number }) {
  const percentage = ((value + 1) / 2) * 100; // Convert -1..1 to 0..100
  const barColor = getProgressBarColor(value);

  return (
    <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
      <div
        className={cn('h-full transition-all duration-300', barColor)}
        style={{ width: `${percentage}%`, marginLeft: 0 }}
      />
    </div>
  );
}

// Skeleton Loading Component
function CorrelationRowSkeleton() {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border bg-card/50">
      <Skeleton className="h-8 w-8 rounded" />
      <div className="flex-1 space-y-2">
        <div className="flex items-center justify-between">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-12" />
        </div>
        <Skeleton className="h-2 w-full" />
      </div>
      <Skeleton className="h-6 w-10 rounded" />
    </div>
  );
}

// Main Component
export function AssetCorrelationPanel({
  baseSymbol,
  correlatedAssets,
  onAssetToggle,
  onPeriodChange,
  onMinCorrelationChange,
  activeOverlays,
  isLoading = false,
  className,
  lastUpdated,
  onRefresh,
}: AssetCorrelationPanelProps) {
  const [sortBy, setSortBy] = useState<'correlation' | 'symbol'>('correlation');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [minCorrelation, setMinCorrelation] = useState(0);
  const [selectedPeriod, setSelectedPeriod] = useState<CorrelationPeriod>('1M');

  // Handle period change
  const handlePeriodChange = useCallback(
    (period: CorrelationPeriod) => {
      setSelectedPeriod(period);
      onPeriodChange(period);
    },
    [onPeriodChange]
  );

  // Handle min correlation change
  const handleMinCorrelationChange = useCallback(
    (value: number[]) => {
      const min = value[0] / 100;
      setMinCorrelation(min);
      onMinCorrelationChange(min);
    },
    [onMinCorrelationChange]
  );

  // Filter and sort assets
  const processedAssets = useMemo(() => {
    let filtered = correlatedAssets.filter(
      (asset) => Math.abs(asset.correlation) >= minCorrelation
    );

    filtered.sort((a, b) => {
      if (sortBy === 'correlation') {
        return sortDirection === 'desc'
          ? Math.abs(b.correlation) - Math.abs(a.correlation)
          : Math.abs(a.correlation) - Math.abs(b.correlation);
      }
      return sortDirection === 'desc'
        ? b.symbol.localeCompare(a.symbol)
        : a.symbol.localeCompare(b.symbol);
    });

    return filtered;
  }, [correlatedAssets, minCorrelation, sortBy, sortDirection]);

  // Toggle sort
  const toggleSort = (column: 'correlation' | 'symbol') => {
    if (sortBy === column) {
      setSortDirection((prev) => (prev === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortBy(column);
      setSortDirection('desc');
    }
  };

  // Stats
  const stats = useMemo(() => {
    const strongPositive = correlatedAssets.filter(
      (a) => a.strength === 'strong_positive'
    ).length;
    const strongNegative = correlatedAssets.filter(
      (a) => a.strength === 'strong_negative'
    ).length;
    const weak = correlatedAssets.filter((a) => a.strength === 'weak').length;

    return { strongPositive, strongNegative, weak, total: correlatedAssets.length };
  }, [correlatedAssets]);

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-cyan-400" />
          <h3 className="text-sm font-semibold">Asset Correlation</h3>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onRefresh}
          disabled={isLoading}
        >
          <RefreshCw
            className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')}
          />
        </Button>
      </div>

      {/* Period Selector */}
      <Tabs
        value={selectedPeriod}
        onValueChange={(v) => handlePeriodChange(v as CorrelationPeriod)}
      >
        <TabsList className="w-full grid grid-cols-3">
          <TabsTrigger value="1W" className="text-xs">
            1W
          </TabsTrigger>
          <TabsTrigger value="1M" className="text-xs">
            1M
          </TabsTrigger>
          <TabsTrigger value="3M" className="text-xs">
            3M
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Stats Overview */}
      <div className="grid grid-cols-3 gap-2">
        <div className="flex flex-col items-center p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
          <span className="text-xs text-muted-foreground">Strong +</span>
          <span className="text-lg font-semibold text-emerald-400">
            {stats.strongPositive}
          </span>
        </div>
        <div className="flex flex-col items-center p-2 rounded-lg bg-slate-500/10 border border-slate-500/20">
          <span className="text-xs text-muted-foreground">Weak</span>
          <span className="text-lg font-semibold text-slate-400">
            {stats.weak}
          </span>
        </div>
        <div className="flex flex-col items-center p-2 rounded-lg bg-rose-500/10 border border-rose-500/20">
          <span className="text-xs text-muted-foreground">Strong -</span>
          <span className="text-lg font-semibold text-rose-400">
            {stats.strongNegative}
          </span>
        </div>
      </div>

      {/* Mini Heatmap */}
      {!isLoading && correlatedAssets.length > 0 && (
        <MiniHeatmap
          assets={correlatedAssets}
          baseSymbol={baseSymbol}
          minCorrelation={minCorrelation}
        />
      )}

      {/* Filter Control */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Filter className="h-3 w-3" />
            <span>Min Correlation</span>
          </div>
          <span className="font-medium">{(minCorrelation * 100).toFixed(0)}%</span>
        </div>
        <Slider
          value={[minCorrelation * 100]}
          onValueChange={handleMinCorrelationChange}
          min={0}
          max={100}
          step={5}
          disabled={isLoading}
        />
      </div>

      {/* Sort Headers */}
      {!isLoading && (
        <div className="flex items-center justify-between px-3 text-xs text-muted-foreground">
          <button
            className="flex items-center gap-1 hover:text-foreground transition-colors"
            onClick={() => toggleSort('symbol')}
          >
            Asset
            {sortBy === 'symbol' &&
              (sortDirection === 'desc' ? (
                <ArrowDownRight className="h-3 w-3" />
              ) : (
                <ArrowUpRight className="h-3 w-3" />
              ))}
          </button>
          <div className="flex items-center gap-4">
            <button
              className="flex items-center gap-1 hover:text-foreground transition-colors"
              onClick={() => toggleSort('correlation')}
            >
              Correlation
              {sortBy === 'correlation' &&
                (sortDirection === 'desc' ? (
                  <ArrowDownRight className="h-3 w-3" />
                ) : (
                  <ArrowUpRight className="h-3 w-3" />
                ))}
            </button>
            <span className="w-10 text-center">Overlay</span>
          </div>
        </div>
      )}

      {/* Assets List */}
      <ScrollArea className="h-[300px]">
        <div className="space-y-2 pr-3">
          {isLoading ? (
            // Loading skeletons
            Array.from({ length: 5 }).map((_, i) => (
              <CorrelationRowSkeleton key={i} />
            ))
          ) : processedAssets.length === 0 ? (
            // Empty state
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Minus className="h-8 w-8 text-muted-foreground/50 mb-2" />
              <p className="text-sm text-muted-foreground">
                No correlations above {(minCorrelation * 100).toFixed(0)}%
              </p>
              <p className="text-xs text-muted-foreground/70 mt-1">
                Try lowering the minimum threshold
              </p>
            </div>
          ) : (
            // Asset rows
            processedAssets.map((asset) => {
              const isOverlayActive = activeOverlays.includes(asset.symbol);
              const correlationPct = (asset.correlation * 100).toFixed(1);

              return (
                <div
                  key={asset.symbol}
                  className={cn(
                    'group flex items-center gap-3 p-3 rounded-lg border transition-all',
                    'bg-card/50 hover:bg-accent/50',
                    isOverlayActive && 'border-cyan-500/30 bg-cyan-500/5'
                  )}
                >
                  {/* Symbol */}
                  <div className="flex-shrink-0">
                    <div
                      className={cn(
                        'w-10 h-10 rounded-lg flex items-center justify-center font-semibold text-xs',
                        'bg-muted border border-border',
                        isOverlayActive && 'border-cyan-500/50 text-cyan-400'
                      )}
                    >
                      {asset.symbol.replace('_', '').slice(0, 4)}
                    </div>
                  </div>

                  {/* Correlation Info */}
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm truncate">
                        {asset.symbol}
                      </span>
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            'text-sm font-bold tabular-nums',
                            getCorrelationColor(asset.correlation)
                          )}
                        >
                          {asset.correlation > 0 ? '+' : ''}
                          {correlationPct}%
                        </span>
                        {getTrendIcon(asset.slope, asset.correlation)}
                      </div>
                    </div>

                    {/* Progress bar */}
                    <CorrelationProgressBar value={asset.correlation} />

                    {/* Labels */}
                    <div className="flex items-center justify-between">
                      <Badge
                        variant="outline"
                        className={cn(
                          'text-[10px] h-5 px-1.5',
                          getStrengthColor(asset.strength)
                        )}
                      >
                        {getStrengthLabel(asset.strength)}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground">
                        {getTrendLabel(asset.slope, asset.correlation)}
                      </span>
                    </div>
                  </div>

                  {/* Toggle */}
                  <div className="flex-shrink-0">
                    <Switch
                      checked={isOverlayActive}
                      onCheckedChange={(checked) =>
                        onAssetToggle(asset.symbol, checked)
                      }
                      className="data-[state=checked]:bg-cyan-500"
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t">
        <div className="flex items-center gap-1.5">
          <span>Base:</span>
          <Badge variant="secondary" className="text-xs">
            {baseSymbol}
          </Badge>
        </div>
        {lastUpdated && (
          <span>
            Updated: {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        )}
      </div>
    </div>
  );
}

// Hook for fetching correlation data
export function useCorrelationData(baseSymbol: string, period: CorrelationPeriod) {
  const [data, setData] = useState<CorrelationData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!baseSymbol) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/v1/chart/analysis-metrics?symbol=${encodeURIComponent(
          baseSymbol
        )}&metric=correlation&period=${period}`
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch correlation data: ${response.status}`);
      }

      const result = await response.json();

      // Transform API response to CorrelationData format
      const correlationData: CorrelationData = {
        baseAsset: baseSymbol,
        correlatedAssets: result.correlations?.map((item: unknown) => {
          const correlation =
            typeof item === 'object' && item !== null && 'correlation' in item
              ? Number((item as Record<string, unknown>).correlation)
              : 0;
          const slope =
            typeof item === 'object' && item !== null && 'slope' in item
              ? (item as Record<string, unknown>).slope
              : 'converging';

          return {
            symbol:
              typeof item === 'object' && item !== null && 'symbol' in item
                ? String((item as Record<string, unknown>).symbol)
                : '',
            correlation,
            strength: getStrengthFromCorrelation(correlation),
            slope: slope === 'diverging' ? 'diverging' : 'converging',
          };
        }) || [],
        period,
        refreshTime: new Date(),
      };

      setData(correlationData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      // Set mock data for development
      setData({
        baseAsset: baseSymbol,
        correlatedAssets: generateMockCorrelations(),
        period,
        refreshTime: new Date(),
      });
    } finally {
      setIsLoading(false);
    }
  }, [baseSymbol, period]);

  const refresh = useCallback(() => {
    fetchData();
  }, [fetchData]);

  // Fetch on mount and when dependencies change
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, isLoading, error, refresh };
}

// Helper to generate mock correlations for development
function generateMockCorrelations(): CorrelatedAsset[] {
  const symbols = [
    'EUR_USD',
    'GBP_USD',
    'USD_JPY',
    'AUD_USD',
    'USD_CAD',
    'USD_CHF',
    'NZD_USD',
    'EUR_GBP',
    'EUR_JPY',
    'GBP_JPY',
    'AUD_JPY',
    'XAU_USD',
    'XAG_USD',
  ];

  return symbols.map((symbol) => {
    const correlation = (Math.random() * 2 - 1); // -1 to 1
    return {
      symbol,
      correlation: Number(correlation.toFixed(3)),
      strength: getStrengthFromCorrelation(correlation),
      slope: Math.random() > 0.5 ? 'converging' : 'diverging',
    };
  });
}



export default AssetCorrelationPanel;
