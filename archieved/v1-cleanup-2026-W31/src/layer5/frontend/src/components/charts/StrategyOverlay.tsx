/**
 * StrategyOverlay - Visualizes trading strategy performance directly on charts.
 * 
 * Features:
 * - Entry signals: Green triangles ▲ (long) / Red triangles ▼ (short)
 * - Stop Loss lines: Dashed red horizontal lines
 * - Take Profit lines: Dashed green horizontal lines
 * - Trade outcome: Green (win) / Red (loss) shading on bars during position hold
 * - Win rate badge: Small widget showing % wins for strategy on this symbol/timeframe
 * - Equity curve: Optional secondary panel showing cumulative PnL
 */

import { useEffect, useRef, useCallback, useMemo, useState } from 'react';
import type { IChartApi, ISeriesApi, Time, CandlestickData, LineWidth } from 'lightweight-charts';
import { createChart } from 'lightweight-charts';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';
import { 
  TrendingUp, 
  TrendingDown, 
  Percent,
  Activity,
  X
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export interface StrategyEntry {
  timestamp: Date;
  signal: 1 | -1; // long | short
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  confidence: number; // 0-1, controls opacity/boldness
  regime: string;
}

export type ExitReason = 'sl_hit' | 'tp_hit' | 'timeout' | 'manual';

export interface TradeResult {
  entry: StrategyEntry;
  exit_price: number;
  exit_reason: ExitReason;
  pnl: number;
  pips_gained: number;
  r_multiple: number;
  exit_timestamp: Date;
}

export interface StrategyOverlayProps {
  entries: StrategyEntry[];
  trades: TradeResult[];
  chart: IChartApi | null;
  candlestickSeries: ISeriesApi<'Candlestick'> | null;
  showEquityCurve?: boolean;
  showWinRate?: boolean;
  onTradeSelect?: (trade: TradeResult) => void;
  className?: string;
  winRate?: number;
  equityHeight?: number;
}

// Color configuration for light/dark themes
const OVERLAY_COLORS = {
  dark: {
    longEntry: '#22C55E',
    shortEntry: '#EF4444',
    stopLoss: '#EF4444',
    takeProfit: '#22C55E',
    winShade: 'rgba(34, 197, 94, 0.15)',
    lossShade: 'rgba(239, 68, 68, 0.15)',
    lineWidth: 1 as LineWidth,
    markerSize: 3,
  },
  light: {
    longEntry: '#16A34A',
    shortEntry: '#DC2626',
    stopLoss: '#DC2626',
    takeProfit: '#16A34A',
    winShade: 'rgba(22, 163, 74, 0.12)',
    lossShade: 'rgba(220, 38, 38, 0.12)',
    lineWidth: 1 as LineWidth,
    markerSize: 3,
  },
};

/**
 * Format number with fixed decimals
 */
function formatPrice(price: number): string {
  return price.toFixed(5);
}

/**
 * Format R-multiple for display
 */
function formatRMultiple(r: number): string {
  const sign = r >= 0 ? '+' : '';
  return `${sign}${r.toFixed(2)}R`;
}

/**
 * Calculate equity curve from trades
 */
function calculateEquityCurve(trades: TradeResult[]): { time: Time; value: number }[] {
  let equity = 0;
  return trades.map(trade => {
    equity += trade.pnl;
    return {
      time: (trade.exit_timestamp.getTime() / 1000) as Time,
      value: equity,
    };
  });
}

/**
 * Check if a time value is a number (UTCTimestamp)
 */
function isNumberTime(time: Time): boolean {
  return typeof time === 'number';
}

/**
 * Convert Time to timestamp in milliseconds
 */
function timeToMs(time: Time): number {
  if (isNumberTime(time)) {
    return Number(time) * 1000;
  }
  // Handle BusinessDay format if needed
  if (typeof time === 'object' && 'year' in time) {
    return new Date(time.year, time.month - 1, time.day).getTime();
  }
  return 0;
}

/**
 * WinRateBadge - Small badge showing win rate statistics
 */
function WinRateBadge({ 
  winRate, 
  totalTrades, 
  wins, 
  losses 
}: { 
  winRate: number; 
  totalTrades: number;
  wins: number;
  losses: number;
}) {
  const isPositive = winRate >= 50;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div 
            className={cn(
              "absolute top-3 right-3 z-20 flex items-center gap-2 px-3 py-2 rounded-lg border backdrop-blur-sm",
              "bg-background/90 shadow-lg cursor-pointer hover:scale-105 transition-transform"
            )}
          >
            <div className={cn(
              "flex items-center justify-center w-8 h-8 rounded-full",
              isPositive ? "bg-green-500/20" : "bg-red-500/20"
            )}>
              {isPositive ? (
                <TrendingUp className="w-4 h-4 text-green-500" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-500" />
              )}
            </div>
            <div className="flex flex-col">
              <span className="text-lg font-bold leading-none">
                {winRate.toFixed(1)}%
              </span>
              <span className="text-xs text-muted-foreground">
                Win Rate
              </span>
            </div>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="p-3">
          <div className="space-y-2 min-w-[140px]">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Total Trades</span>
              <Badge variant="secondary">{totalTrades}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-green-500">Wins</span>
              <span className="font-medium">{wins}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-red-500">Losses</span>
              <span className="font-medium">{losses}</span>
            </div>
            <div className="h-px bg-border my-1" />
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Win Rate</span>
              <span className={cn(
                "font-bold",
                isPositive ? "text-green-500" : "text-red-500"
              )}>
                {winRate.toFixed(1)}%
              </span>
            </div>
          </div>
        </TooltipContent>
      </Tooltip>
  </TooltipProvider>
  );
}

/**
 * TradeDetailPopup - Shows trade details when clicked
 */
function TradeDetailPopup({
  trade,
  onClose,
  position,
}: {
  trade: TradeResult;
  onClose: () => void;
  position: { x: number; y: number };
}) {
  const isWin = trade.pnl > 0;

  return (
    <div
      className={cn(
        "absolute z-30 p-4 rounded-lg border shadow-xl min-w-[240px]",
        "bg-background/95 backdrop-blur-sm animate-in fade-in zoom-in-95 duration-200"
      )}
      style={{
        left: Math.min(position.x, window.innerWidth - 260),
        top: Math.min(position.y, window.innerHeight - 200),
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {trade.entry.signal === 1 ? (
            <TrendingUp className="w-4 h-4 text-green-500" />
          ) : (
            <TrendingDown className="w-4 h-4 text-red-500" />
          )}
          <span className="font-semibold">
            {trade.entry.signal === 1 ? 'Long' : 'Short'} Trade
          </span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={onClose}
        >
          <X className="h-3 w-3" />
        </Button>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Entry</span>
          <span className="font-mono">{formatPrice(trade.entry.entry_price)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Exit</span>
          <span className="font-mono">{formatPrice(trade.exit_price)}</span>
        </div>
        <div className="h-px bg-border my-2" />
        <div className="flex justify-between items-center">
          <span className="text-muted-foreground flex items-center gap-1">
            <Activity className="w-3 h-3" />
            PnL
          </span>
          <span className={cn(
            "font-bold font-mono",
            isWin ? "text-green-500" : "text-red-500"
          )}>
            {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(2)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Pips</span>
          <span className={cn(
            "font-mono",
            isWin ? "text-green-500" : "text-red-500"
          )}>
            {trade.pips_gained >= 0 ? '+' : ''}{trade.pips_gained.toFixed(1)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">R-Multiple</span>
          <Badge 
            variant={isWin ? "default" : "destructive"}
            className="text-xs"
          >
            {formatRMultiple(trade.r_multiple)}
          </Badge>
        </div>
        <div className="h-px bg-border my-2" />
        <div className="flex justify-between">
          <span className="text-muted-foreground">Exit Reason</span>
          <Badge variant="outline" className="text-xs capitalize">
            {trade.exit_reason.replace('_', ' ')}
          </Badge>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Confidence</span>
          <span className="font-mono">{(trade.entry.confidence * 100).toFixed(0)}%</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Regime</span>
          <span className="text-xs">{trade.entry.regime}</span>
        </div>
      </div>
    </div>
  );
}

/**
 * EquityCurvePanel - Secondary panel showing cumulative PnL
 */
function EquityCurvePanel({
  trades,
  height,
  className,
}: {
  trades: TradeResult[];
  height: number;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const { resolvedTheme } = useTheme();

  const equityData = useMemo(() => calculateEquityCurve(trades), [trades]);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: 'transparent' },
        textColor: resolvedTheme === 'dark' ? '#9CA3AF' : '#6B7280',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: resolvedTheme === 'dark' ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)' },
        horzLines: { color: resolvedTheme === 'dark' ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)' },
      },
      rightPriceScale: {
        borderVisible: false,
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: 0,
      },
      handleScroll: false,
      handleScale: false,
    });

    chartRef.current = chart;

    // Create area series for equity curve
    const series = chart.addAreaSeries({
      lineColor: '#3B82F6',
      topColor: 'rgba(59, 130, 246, 0.4)',
      bottomColor: 'rgba(59, 130, 246, 0.05)',
      lineWidth: 2,
      title: 'Equity',
    });

    seriesRef.current = series;

    // Handle resize
    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height,
        });
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [height, resolvedTheme]);

  // Update equity data
  useEffect(() => {
    if (!seriesRef.current) return;
    seriesRef.current.setData(equityData);
    
    if (chartRef.current && equityData.length > 0) {
      chartRef.current.timeScale().fitContent();
    }
  }, [equityData]);

  if (trades.length === 0) {
    return (
      <div 
        className={cn(
          "flex items-center justify-center border-t bg-muted/30",
          className
        )}
        style={{ height }}
      >
        <p className="text-sm text-muted-foreground">No trades to display</p>
      </div>
    );
  }

  return (
    <div className={cn("border-t", className)}>
      <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-blue-500" />
          <span className="text-sm font-medium">Equity Curve</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-muted-foreground">
            Total: <span className={cn(
              "font-mono font-medium",
              equityData[equityData.length - 1]?.value >= 0 ? "text-green-500" : "text-red-500"
            )}>
              {equityData[equityData.length - 1]?.value?.toFixed(2) ?? '0.00'}
            </span>
          </span>
          <span className="text-muted-foreground">
            Trades: <span className="font-medium">{trades.length}</span>
          </span>
        </div>
      </div>
      <div ref={containerRef} style={{ height: height - 41 }} />
    </div>
  );
}

/**
 * StrategyOverlay - Main component for visualizing strategy performance on charts
 */
export function StrategyOverlay({
  entries,
  trades,
  chart,
  candlestickSeries,
  showEquityCurve = false,
  showWinRate = true,
  onTradeSelect,
  className,
  winRate = 0,
  equityHeight = 120,
}: StrategyOverlayProps) {
  const { resolvedTheme } = useTheme();
  const colors = OVERLAY_COLORS[resolvedTheme];
  
  // Refs for managing chart primitives
  const entryMarkersRef = useRef<ISeriesApi<'Line'>[]>([]);
  const slLinesRef = useRef<ISeriesApi<'Line'>[]>([]);
  const tpLinesRef = useRef<ISeriesApi<'Line'>[]>([]);
  const shadedAreasRef = useRef<ISeriesApi<'Line'>[]>([]);
  const clickHandlersRef = useRef<((param: MouseEventParams) => void)[]>([]);
  
  // State for trade detail popup
  const [selectedTrade, setSelectedTrade] = useState<TradeResult | null>(null);
  const [popupPosition, setPopupPosition] = useState({ x: 0, y: 0 });

  // Calculate win/loss counts
  const { wins, losses, totalTrades } = useMemo(() => {
    const winCount = trades.filter(t => t.pnl > 0).length;
    return {
      wins: winCount,
      losses: trades.length - winCount,
      totalTrades: trades.length,
    };
  }, [trades]);

  // Calculate actual win rate from trades if not provided
  const calculatedWinRate = useMemo(() => {
    if (winRate > 0) return winRate;
    if (totalTrades === 0) return 0;
    return (wins / totalTrades) * 100;
  }, [winRate, wins, totalTrades]);

  /**
   * Clear all overlay elements from chart
   */
  const clearOverlays = useCallback(() => {
    if (!chart) return;

    // Remove entry markers
    entryMarkersRef.current.forEach(series => {
      chart.removeSeries(series);
    });
    entryMarkersRef.current = [];

    // Remove SL lines
    slLinesRef.current.forEach(series => {
      chart.removeSeries(series);
    });
    slLinesRef.current = [];

    // Remove TP lines
    tpLinesRef.current.forEach(series => {
      chart.removeSeries(series);
    });
    tpLinesRef.current = [];

    // Remove shaded areas
    shadedAreasRef.current.forEach(series => {
      chart.removeSeries(series);
    });
    shadedAreasRef.current = [];

    // Remove click handlers
    clickHandlersRef.current.forEach(handler => {
      chart.unsubscribeClick(handler);
    });
    clickHandlersRef.current = [];
  }, [chart]);

  /**
   * Render entry markers
   */
  const renderEntryMarkers = useCallback(() => {
    if (!chart || entries.length === 0) return;

    entries.forEach((entry) => {
      // Create a line series for this marker (line not visible, just markers)
      const markerSeries = chart.addLineSeries({
        lineVisible: false,
        lastValueVisible: false,
        title: '',
        color: entry.signal === 1 ? colors.longEntry : colors.shortEntry,
      });

      const time = (entry.timestamp.getTime() / 1000) as Time;

      markerSeries.setData([{ time, value: entry.entry_price }]);
      
      // Store for cleanup
      entryMarkersRef.current.push(markerSeries);
    });
  }, [chart, entries, colors]);

  /**
   * Render SL and TP lines
   */
  const renderSLLines = useCallback(() => {
    if (!chart || entries.length === 0) return;

    entries.forEach(entry => {
      const time = (entry.timestamp.getTime() / 1000) as Time;

      // Stop Loss line
      const slSeries = chart.addLineSeries({
        color: colors.stopLoss,
        lineWidth: colors.lineWidth,
        lineStyle: 2, // dashed
        lastValueVisible: false,
        title: `SL ${formatPrice(entry.stop_loss)}`,
      });

      // Extend SL line to end of chart or until exit
      const exitTime = trades.find(t => 
        t.entry.timestamp.getTime() === entry.timestamp.getTime()
      )?.exit_timestamp;

      const slData = [
        { time, value: entry.stop_loss },
        { 
          time: exitTime 
            ? (exitTime.getTime() / 1000) as Time 
            : ((Date.now() / 1000) + 86400) as Time, // Extend 1 day if no exit
          value: entry.stop_loss 
        },
      ];

      slSeries.setData(slData);
      slLinesRef.current.push(slSeries);

      // Take Profit line
      const tpSeries = chart.addLineSeries({
        color: colors.takeProfit,
        lineWidth: colors.lineWidth,
        lineStyle: 2, // dashed
        lastValueVisible: false,
        title: `TP ${formatPrice(entry.take_profit)}`,
      });

      const tpData = [
        { time, value: entry.take_profit },
        { 
          time: exitTime 
            ? (exitTime.getTime() / 1000) as Time 
            : ((Date.now() / 1000) + 86400) as Time,
          value: entry.take_profit 
        },
      ];

      tpSeries.setData(tpData);
      tpLinesRef.current.push(tpSeries);
    });
  }, [chart, entries, trades, colors]);

  /**
   * Render trade outcome shading
   */
  const renderOutcomeShading = useCallback(() => {
    if (!chart || trades.length === 0 || !candlestickSeries) return;

    // Get candlestick data for shading
    const candleData = candlestickSeries.data();
    
    trades.forEach(trade => {
      // Find candles within trade duration
      const entryTime = trade.entry.timestamp.getTime();
      const exitTime = trade.exit_timestamp.getTime();
      
      const tradeCandles = candleData.filter(c => {
        const candleTime = timeToMs(c.time);
        return candleTime >= entryTime && candleTime <= exitTime;
      }) as CandlestickData<Time>[];
      
      if (tradeCandles.length === 0) return;

      // Create shaded area using line series with transparent line
      const shadeSeries = chart.addLineSeries({
        color: 'transparent',
        lineWidth: 1 as LineWidth,
        lastValueVisible: false,
        title: '',
      });

      // Create shaded band data
      const shadeData = tradeCandles.map(candle => ({
        time: candle.time,
        value: candle.high,
      }));

      shadeSeries.setData(shadeData);
      shadedAreasRef.current.push(shadeSeries);
    });
  }, [chart, trades, candlestickSeries]);

  // Type for mouse event params
  interface MouseEventParams {
    time?: Time;
    point?: { x: number; y: number };
  }

  /**
   * Handle chart click for trade selection
   */
  const handleChartClick = useCallback((param: MouseEventParams) => {
    if (!param.time || !onTradeSelect) return;

    const clickTime = (param.time as number) * 1000;
    const clickThreshold = 300000; // 5 minutes tolerance

    // Find nearest trade entry
    const nearestTrade = trades.find(trade => {
      const entryTime = trade.entry.timestamp.getTime();
      return Math.abs(entryTime - clickTime) < clickThreshold;
    });

    if (nearestTrade) {
      setSelectedTrade(nearestTrade);
      setPopupPosition({
        x: param.point?.x ?? 100,
        y: param.point?.y ?? 100,
      });
      onTradeSelect(nearestTrade);
    }
  }, [trades, onTradeSelect]);

  // Main effect to render overlays
  useEffect(() => {
    if (!chart) return;

    // Clear existing overlays
    clearOverlays();

    // Render new overlays
    renderEntryMarkers();
    renderSLLines();
    renderOutcomeShading();

    // Add click handler
    chart.subscribeClick(handleChartClick);
    clickHandlersRef.current.push(handleChartClick);

    return () => {
      clearOverlays();
    };
  }, [chart, entries, trades, handleChartClick, clearOverlays, renderEntryMarkers, renderSLLines, renderOutcomeShading]);

  // Handle empty state
  if (entries.length === 0 && trades.length === 0) {
    return (
      <div className={cn("relative", className)}>
        {showWinRate && (
          <div className="absolute top-3 right-3 z-20">
            <Badge variant="secondary" className="px-3 py-1">
              <Percent className="w-3 h-3 mr-1" />
              No strategy data
            </Badge>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={cn("relative", className)}>
      {/* Win Rate Badge */}
      {showWinRate && totalTrades > 0 && (
        <WinRateBadge 
          winRate={calculatedWinRate}
          totalTrades={totalTrades}
          wins={wins}
          losses={losses}
        />
      )}

      {/* Trade Detail Popup */}
      {selectedTrade && (
        <TradeDetailPopup
          trade={selectedTrade}
          onClose={() => setSelectedTrade(null)}
          position={popupPosition}
        />
      )}

      {/* Legend */}
      <div className="absolute bottom-3 left-3 z-20 flex flex-col gap-1.5 p-2 rounded-lg border bg-background/90 backdrop-blur-sm shadow-lg">
        <div className="flex items-center gap-2 text-xs">
          <TrendingUp className="w-3 h-3 text-green-500" />
          <span className="text-muted-foreground">Long Entry</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <TrendingDown className="w-3 h-3 text-red-500" />
          <span className="text-muted-foreground">Short Entry</span>
        </div>
        <div className="h-px bg-border my-0.5" />
        <div className="flex items-center gap-2 text-xs">
          <div className="w-4 h-0.5 border-t border-dashed border-red-500" />
          <span className="text-muted-foreground">Stop Loss</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <div className="w-4 h-0.5 border-t border-dashed border-green-500" />
          <span className="text-muted-foreground">Take Profit</span>
        </div>
      </div>

      {/* Equity Curve Panel */}
      {showEquityCurve && (
        <div className="absolute inset-x-0 bottom-0 z-10">
          <EquityCurvePanel
            trades={trades}
            height={equityHeight}
          />
        </div>
      )}
    </div>
  );
}

export default StrategyOverlay;
