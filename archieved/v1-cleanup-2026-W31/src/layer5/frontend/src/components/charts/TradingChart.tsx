import { useEffect, useRef, useState, useCallback } from 'react';
import { createChart } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, CandlestickData, Time } from 'lightweight-charts';
import { useTheme } from '@/hooks/useTheme';
import { Button } from '@/components/ui/button';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { 
  Loader2, 
  Maximize2, 
  Minimize2, 
  TrendingUp, 
  BarChart3,
  LineChart,
  Settings
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface OHLCData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface IndicatorData {
  indicator: string;
  name?: string;
  values: (number | null)[];
  timestamps?: string[];
  upper?: (number | null)[];
  middle?: (number | null)[];
  lower?: (number | null)[];
  signal?: (number | null)[];
  histogram?: (number | null)[];
}

interface TradingChartProps {
  symbol: string;
  data: OHLCData[];
  indicators?: IndicatorData[];
  onTimeframeChange?: (timeframe: string) => void;
  onSymbolChange?: (symbol: string) => void;
  availableSymbols?: string[];
  availableTimeframes?: string[];
  currentTimeframe?: string;
  isLoading?: boolean;
  height?: number;
  className?: string;
  showToolbar?: boolean;
  allowFullscreen?: boolean;
}

const TIMEFRAMES = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '30m', label: '30m' },
  { value: '1h', label: '1H' },
  { value: '2h', label: '2H' },
  { value: '4h', label: '4H' },
  { value: '6h', label: '6H' },
  { value: '8h', label: '8H' },
  { value: '12h', label: '12H' },
  { value: '1d', label: '1D' },
  { value: '1w', label: '1W' },
  { value: '1M', label: '1M' },
];

const CHART_COLORS = {
  dark: {
    background: '#0B0C0F',
    grid: 'rgba(255, 255, 255, 0.06)',
    text: '#9CA3AF',
    up: '#22C55E',
    down: '#EF4444',
    wickUp: '#22C55E',
    wickDown: '#EF4444',
    border: 'rgba(255, 255, 255, 0.08)',
  },
  light: {
    background: '#FFFFFF',
    grid: 'rgba(0, 0, 0, 0.06)',
    text: '#6B7280',
    up: '#16A34A',
    down: '#DC2626',
    wickUp: '#16A34A',
    wickDown: '#DC2626',
    border: 'rgba(0, 0, 0, 0.08)',
  },
};

const INDICATOR_COLORS = [
  '#3B82F6', // blue
  '#F59E0B', // amber
  '#8B5CF6', // violet
  '#EC4899', // pink
  '#10B981', // emerald
  '#06B6D4', // cyan
];

export function TradingChart({
  symbol,
  data,
  indicators = [],
  onTimeframeChange,
  onSymbolChange,
  availableSymbols = [],
  availableTimeframes = TIMEFRAMES.map(t => t.value),
  currentTimeframe = '1h',
  isLoading = false,
  height = 500,
  className,
  showToolbar = true,
  allowFullscreen = true,
}: TradingChartProps) {
  const { resolvedTheme } = useTheme();
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const indicatorSeriesRef = useRef<ISeriesApi<'Line'>[]>([]);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [chartType, setChartType] = useState<'candlestick' | 'bar' | 'line'>('candlestick');

  const colors = CHART_COLORS[resolvedTheme];

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: colors.background },
        textColor: colors.text,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: colors.text,
          width: 1,
          style: 2,
          labelBackgroundColor: colors.text,
        },
        horzLine: {
          color: colors.text,
          width: 1,
          style: 2,
          labelBackgroundColor: colors.text,
        },
      },
      rightPriceScale: {
        borderColor: colors.border,
        scaleMargins: {
          top: 0.1,
          bottom: 0.1,
        },
      },
      timeScale: {
        borderColor: colors.border,
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: {
        vertTouchDrag: false,
      },
    });

    chartRef.current = chart;

    // Create candlestick series
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: colors.up,
      downColor: colors.down,
      borderUpColor: colors.up,
      borderDownColor: colors.down,
      wickUpColor: colors.wickUp,
      wickDownColor: colors.wickDown,
    });

    candlestickSeriesRef.current = candlestickSeries;

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: isFullscreen ? window.innerHeight - 100 : height,
        });
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [colors.background, colors.border, colors.down, colors.grid, colors.text, colors.up, colors.wickDown, colors.wickUp, height, isFullscreen]);

  // Update data
  useEffect(() => {
    if (!candlestickSeriesRef.current || !data.length) return;

    // Convert timestamps and sort in ascending order to prevent lightweight-charts assertion errors
    const chartData: CandlestickData<Time>[] = data
      .map(d => ({
        time: (new Date(d.timestamp).getTime() / 1000) as Time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number))
      // Remove duplicate timestamps (keep the first occurrence)
      .reduce((acc, current) => {
        const isDuplicate = acc.length > 0 && acc[acc.length - 1].time === current.time;
        return isDuplicate ? acc : [...acc, current];
      }, [] as CandlestickData<Time>[]);

    candlestickSeriesRef.current.setData(chartData);

    // Fit content
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [data]);

  // Update indicators
  useEffect(() => {
    if (!chartRef.current) return;

    // Remove existing indicator series
    indicatorSeriesRef.current.forEach(series => {
      chartRef.current?.removeSeries(series);
    });
    indicatorSeriesRef.current = [];

    // Add new indicator series
    indicators.forEach((indicator, index) => {
      if (!chartRef.current) return;

      const color = INDICATOR_COLORS[index % INDICATOR_COLORS.length];

      // Handle multi-line indicators
      if (indicator.upper && indicator.middle && indicator.lower) {
        // Bollinger Bands
        const upperSeries = chartRef.current.addLineSeries({
          color: color,
          lineWidth: 1,
          title: `${indicator.indicator} Upper`,
        });
        const lowerSeries = chartRef.current.addLineSeries({
          color: color,
          lineWidth: 1,
          title: `${indicator.indicator} Lower`,
        });
        const middleSeries = chartRef.current.addLineSeries({
          color: color,
          lineWidth: 2,
          title: `${indicator.indicator} Middle`,
        });

        const lineData = indicator.upper.map((v, i) => ({
          time: (new Date(indicator.timestamps?.[i] || data[i]?.timestamp).getTime() / 1000) as Time,
          value: v || 0,
        })).filter(d => d.value !== 0);

        upperSeries.setData(lineData);
        indicatorSeriesRef.current.push(upperSeries);
      } else if (indicator.values) {
        // Single line indicator
        const series = chartRef.current.addLineSeries({
          color: color,
          lineWidth: 2,
          title: indicator.indicator,
        });

        const lineData = indicator.values.map((v, i) => ({
          time: (new Date(indicator.timestamps?.[i] || data[i]?.timestamp).getTime() / 1000) as Time,
          value: v || 0,
        })).filter(d => d.value !== 0);

        series.setData(lineData);
        indicatorSeriesRef.current.push(series);
      }
    });
  }, [indicators, data]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev);
  }, []);

  const timeframeOptions = TIMEFRAMES.filter(tf => availableTimeframes.includes(tf.value));

  return (
    <div className={cn("flex flex-col rounded-lg border border-border overflow-hidden", className)}>
      {/* Toolbar */}
      {showToolbar && (
        <div className="flex items-center justify-between p-3 border-b border-border bg-card">
          <div className="flex items-center gap-3">
            {/* Symbol Selector */}
            {availableSymbols.length > 0 && onSymbolChange ? (
              <Select value={symbol} onValueChange={onSymbolChange}>
                <SelectTrigger className="w-32 h-8">
                  <SelectValue placeholder="Symbol" />
                </SelectTrigger>
                <SelectContent>
                  {availableSymbols.map(s => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <span className="font-semibold text-sm">{symbol}</span>
            )}

            {/* Timeframe Selector */}
            {onTimeframeChange && (
              <Select value={currentTimeframe} onValueChange={onTimeframeChange}>
                <SelectTrigger className="w-20 h-8">
                  <SelectValue placeholder="TF" />
                </SelectTrigger>
                <SelectContent>
                  {timeframeOptions.map(tf => (
                    <SelectItem key={tf.value} value={tf.value}>{tf.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Chart Type Toggle */}
            <div className="flex items-center gap-1 bg-muted rounded-md p-1">
              <Button
                variant="ghost"
                size="icon"
                className={cn("h-6 w-6", chartType === 'candlestick' && "bg-background")}
                onClick={() => setChartType('candlestick')}
              >
                <BarChart3 className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className={cn("h-6 w-6", chartType === 'line' && "bg-background")}
                onClick={() => setChartType('line')}
              >
                <LineChart className="h-3.5 w-3.5" />
              </Button>
            </div>

            {/* Settings */}
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <Settings className="h-4 w-4" />
            </Button>

            {/* Fullscreen */}
            {allowFullscreen && (
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={toggleFullscreen}>
                {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Chart */}
      <div className="relative bg-background">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}
        {!isLoading && data.length === 0 && (
          <div
            style={{ height: isFullscreen ? window.innerHeight - 100 : height }}
            className="w-full flex items-center justify-center"
          >
            <div className="text-center">
              <BarChart3 className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
              <p className="text-muted-foreground text-sm">
                No chart data available for <strong>{symbol}</strong> at <strong>{currentTimeframe}</strong>
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Ensure the symbol exists and has recent trading data
              </p>
            </div>
          </div>
        )}
        <div
          ref={chartContainerRef}
          style={{ height: isFullscreen ? window.innerHeight - 100 : height }}
          className="w-full"
        />
      </div>

      {/* Legend */}
      {indicators.length > 0 && (
        <div className="flex items-center gap-4 px-3 py-2 border-t border-border bg-card text-xs">
          <span className="font-medium">{symbol}</span>
          {indicators.map((ind, i) => (
            <span key={ind.indicator} className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: INDICATOR_COLORS[i % INDICATOR_COLORS.length] }}
              />
              {ind.name || ind.indicator}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
