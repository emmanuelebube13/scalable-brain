import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { createChart, CrosshairMode } from 'lightweight-charts';
import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LineData,
  HistogramData,
  Time,
  ChartOptions,
  DeepPartial,
  SeriesType,
  UTCTimestamp,
} from 'lightweight-charts';
import { useTheme } from '@/hooks/useTheme';
import { Button } from '@/components/ui/button';
import { Toggle } from '@/components/ui/toggle';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Loader2,
  Maximize2,
  Minimize2,
  TrendingUp,
  BarChart3,
  LineChart,
  Settings,
  Camera,
  Crosshair,
  Layers,
  Activity,
  Target,

  GitBranch,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// =============================================================================
// TYPES
// =============================================================================

export type Granularity = '1m' | '5m' | '15m' | '30m' | '1h' | '2h' | '4h' | '6h' | '8h' | '12h' | '1d' | '1w' | '1M';
export type ChartType = 'candlestick' | 'bar' | 'line';
export type DataSource = 'oanda' | 'database';
export type AnalysisToolType = 'trendline' | 'fibonacci' | 'horizontal' | 'ray' | 'rectangle' | 'text';

export interface OHLCData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorData {
  id: string;
  name: string;
  params: Record<string, any>;
  color: string;
  subpanel?: boolean;
  category?: 'trend' | 'momentum' | 'volatility' | 'volume';
  // Data fields
  values?: (number | null)[];
  upper?: (number | null)[];
  middle?: (number | null)[];
  lower?: (number | null)[];
  signal?: (number | null)[];
  histogram?: (number | null)[];
  timestamps?: string[];
  minValue?: number;
  maxValue?: number;
}

export interface AnalysisTool {
  id: string;
  type: AnalysisToolType;
  points: { time: Time; price: number }[];
  style?: {
    color?: string;
    lineWidth?: number;
    lineStyle?: number;
    fillColor?: string;
  };
  text?: string;
}

export interface TradeLine {
  id: string;
  type: 'entry' | 'sl' | 'tp';
  price: number;
  time: Time;
  label?: string;
  color?: string;
}

export interface SupportResistanceLevel {
  price: number;
  strength: number; // 0-1
  type: 'support' | 'resistance';
  touches: number;
}

export interface VolumeProfileData {
  price: number;
  volume: number;
  priceRange: { min: number; max: number };
}

export interface CorrelatedAsset {
  symbol: string;
  correlation: number;
  data: { timestamp: string; close: number }[];
  color: string;
}

export interface AdvancedChartProps {
  // Data binding
  symbol: string;
  timeframe: Granularity;
  dataSource?: DataSource;

  // Data
  data: OHLCData[];
  isLoading?: boolean;

  // Indicators
  activeIndicators?: IndicatorData[];

  // Overlays
  showStrategy?: boolean;
  strategyName?: string;
  strategyTrades?: TradeLine[];
  showLiveTradeLines?: boolean;
  liveTradeLines?: TradeLine[];
  showSupportResistance?: boolean;
  supportResistanceLevels?: SupportResistanceLevel[];
  showVolumeProfile?: boolean;
  volumeProfileData?: VolumeProfileData[];

  // Asset filtering
  correlatedAssets?: CorrelatedAsset[];
  hideWeakCorrelations?: boolean;
  minCorrelation?: number;

  // Analysis mode
  analysisTools?: AnalysisTool[];

  // Appearance
  height?: number;
  className?: string;
  showToolbar?: boolean;
  allowFullscreen?: boolean;
  showLegend?: boolean;

  // Callbacks
  onTimeframeChange?: (timeframe: Granularity) => void;
  onSymbolChange?: (symbol: string) => void;
  onIndicatorChange?: (indicators: IndicatorData[]) => void;
  onRangeChange?: (from: Date, to: Date) => void;
  onChartTypeChange?: (type: ChartType) => void;
  onAnalysisToolAdd?: (tool: AnalysisTool) => void;
  onAnalysisToolRemove?: (id: string) => void;

  // Options
  availableSymbols?: string[];
  availableTimeframes?: Granularity[];
}

// =============================================================================
// CONSTANTS
// =============================================================================

const ALL_TIMEFRAMES: { value: Granularity; label: string }[] = [
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
    textStrong: '#E5E7EB',
    up: '#22C55E',
    down: '#EF4444',
    wickUp: '#22C55E',
    wickDown: '#EF4444',
    border: 'rgba(255, 255, 255, 0.08)',
    crosshair: 'rgba(255, 255, 255, 0.2)',
    volume: 'rgba(59, 130, 246, 0.5)',
  },
  light: {
    background: '#FFFFFF',
    grid: 'rgba(0, 0, 0, 0.06)',
    text: '#6B7280',
    textStrong: '#374151',
    up: '#16A34A',
    down: '#DC2626',
    wickUp: '#16A34A',
    wickDown: '#DC2626',
    border: 'rgba(0, 0, 0, 0.08)',
    crosshair: 'rgba(0, 0, 0, 0.2)',
    volume: 'rgba(59, 130, 246, 0.5)',
  },
};

const INDICATOR_COLORS = [
  '#3B82F6', // blue
  '#F59E0B', // amber
  '#8B5CF6', // violet
  '#EC4899', // pink
  '#10B981', // emerald
  '#06B6D4', // cyan
  '#F97316', // orange
  '#84CC16', // lime
  '#14B8A6', // teal
  '#6366F1', // indigo
];

const TRADE_LINE_COLORS = {
  entry: '#3B82F6',
  sl: '#EF4444',
  tp: '#22C55E',
};

const SUBPANEL_INDICATORS = ['rsi', 'stochastic', 'macd', 'obv', 'atr', 'cci', 'williams'];

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

function parseTime(timestamp: string): Time {
  return (new Date(timestamp).getTime() / 1000) as UTCTimestamp;
}

function sortAndDeduplicateData<T extends { time: Time }>(data: T[]): T[] {
  return data
    .sort((a, b) => (a.time as number) - (b.time as number))
    .reduce((acc, current) => {
      const isDuplicate = acc.length > 0 && acc[acc.length - 1].time === current.time;
      return isDuplicate ? acc : [...acc, current];
    }, [] as T[]);
}

function formatPrice(price: number, decimals = 5): string {
  return price.toFixed(decimals);
}

function isSubpanelIndicator(indicator: IndicatorData): boolean {
  return indicator.subpanel || SUBPANEL_INDICATORS.some(id => indicator.id.toLowerCase().includes(id));
}

// =============================================================================
// COMPONENT
// =============================================================================

export function AdvancedChart({
  symbol,
  timeframe,
  dataSource = 'oanda',
  data = [],
  isLoading = false,
  activeIndicators = [],
  showStrategy = false,
  strategyName,
  strategyTrades = [],
  showLiveTradeLines = false,
  liveTradeLines = [],
  showSupportResistance = false,
  supportResistanceLevels = [],
  showVolumeProfile = false,
  volumeProfileData: _volumeProfileData = [],
  correlatedAssets = [],
  hideWeakCorrelations = false,
  minCorrelation = 0.3,
  analysisTools: _analysisTools = [],
  height = 600,
  className,
  showToolbar = true,
  allowFullscreen = true,
  showLegend = true,
  onTimeframeChange,
  onSymbolChange,
  onIndicatorChange: _onIndicatorChange,
  onRangeChange,
  onChartTypeChange,
  onAnalysisToolAdd: _onAnalysisToolAdd,
  onAnalysisToolRemove: _onAnalysisToolRemove,
  availableSymbols = [],
  availableTimeframes = ALL_TIMEFRAMES.map(t => t.value),
}: AdvancedChartProps) {
  const { resolvedTheme } = useTheme();
  const colors = CHART_COLORS[resolvedTheme];

  // Refs
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const mainChartRef = useRef<IChartApi | null>(null);
  const subpanelChartsRef = useRef<Map<string, IChartApi>>(new Map());
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const mainIndicatorSeriesRef = useRef<Map<string, ISeriesApi<SeriesType>>>(new Map());
  const subpanelSeriesRef = useRef<Map<string, ISeriesApi<SeriesType>>>(new Map());
  const correlatedSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map());
  const tradeLinesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map());
  const srLinesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map());
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  // State
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [chartType, setChartType] = useState<ChartType>('candlestick');
  const [showVolume, setShowVolume] = useState(true);
  const [showCrosshair, setShowCrosshair] = useState(true);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [subpanelHeight, setSubpanelHeight] = useState(120);
  const [hoveredPrice, setHoveredPrice] = useState<number | null>(null);
  const [hoveredTime, setHoveredTime] = useState<Time | null>(null);
  const [, setVisibleRange] = useState<{ from: Date; to: Date } | null>(null);

  // Derived state
  const filteredCorrelations = useMemo(() => {
    if (hideWeakCorrelations) {
      return correlatedAssets.filter(a => Math.abs(a.correlation) >= (minCorrelation || 0.3));
    }
    return correlatedAssets;
  }, [correlatedAssets, hideWeakCorrelations, minCorrelation]);

  const mainIndicators = useMemo(() => 
    activeIndicators.filter(ind => !isSubpanelIndicator(ind)),
    [activeIndicators]
  );

  const subpanelIndicators = useMemo(() => 
    activeIndicators.filter(ind => isSubpanelIndicator(ind)),
    [activeIndicators]
  );

  // =============================================================================
  // CHART INITIALIZATION
  // =============================================================================

  const createChartOptions = useCallback((): DeepPartial<ChartOptions> => {
    const baseOptions: DeepPartial<ChartOptions> = {
      layout: {
        background: { color: colors.background },
        textColor: colors.text,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      crosshair: {
        mode: showCrosshair ? CrosshairMode.Normal : CrosshairMode.Magnet,
        vertLine: {
          color: colors.crosshair,
          width: 1,
          style: 2,
          labelBackgroundColor: colors.text,
          visible: showCrosshair,
        },
        horzLine: {
          color: colors.crosshair,
          width: 1,
          style: 2,
          labelBackgroundColor: colors.text,
          visible: showCrosshair,
        },
      },
      rightPriceScale: {
        borderColor: colors.border,
        scaleMargins: {
          top: 0.1,
          bottom: showVolume ? 0.2 : 0.1,
        },
      },
      timeScale: {
        borderColor: colors.border,
        timeVisible: ['1m', '5m', '15m', '30m', '1h'].includes(timeframe),
        secondsVisible: false,
        rightOffset: 10,
        barSpacing: 6,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      handleScroll: {
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
      },
    };
    return baseOptions;
  }, [colors, showCrosshair, timeframe, showVolume]);

  // Initialize main chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Cleanup existing
    if (mainChartRef.current) {
      mainChartRef.current.remove();
      mainChartRef.current = null;
    }

    // Create main chart
    const chart = createChart(chartContainerRef.current, createChartOptions());
    mainChartRef.current = chart;

    // Subscribe to crosshair move
    chart.subscribeCrosshairMove(param => {
      if (param.time) {
        setHoveredTime(param.time);
        if (param.point?.y !== undefined) {
          const price = candlestickSeriesRef.current?.coordinateToPrice(param.point.y);
          if (price !== null && price !== undefined) {
            setHoveredPrice(price);
          }
        }
      } else {
        setHoveredPrice(null);
        setHoveredTime(null);
      }
    });

    // Subscribe to visible range changes
    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      const range = chart.timeScale().getVisibleLogicalRange();
      if (range) {
        // Convert logical range to time range
        const fromTime = chart.timeScale().coordinateToTime(0);
        const toTime = chart.timeScale().coordinateToTime(chart.timeScale().width());
        if (fromTime && toTime) {
          const from = new Date((fromTime as number) * 1000);
          const to = new Date((toTime as number) * 1000);
          setVisibleRange({ from, to });
          onRangeChange?.(from, to);
        }
      }
    });

    // Create candlestick series
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: colors.up,
      downColor: colors.down,
      borderUpColor: colors.up,
      borderDownColor: colors.down,
      wickUpColor: colors.wickUp,
      wickDownColor: colors.wickDown,
      borderVisible: true,
      wickVisible: true,
    });
    candlestickSeriesRef.current = candlestickSeries;

    // Create volume series (if enabled)
    if (showVolume) {
      const volumeSeries = chart.addHistogramSeries({
        color: colors.volume,
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
      });
      volumeSeries.priceScale().applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
        visible: false,
      });
      volumeSeriesRef.current = volumeSeries;
    }

    // Setup resize observer
    const handleResize = () => {
      if (chartContainerRef.current && mainChartRef.current) {
        const width = chartContainerRef.current.clientWidth;
        const mainHeight = calculateMainChartHeight();
        mainChartRef.current.applyOptions({ width, height: mainHeight });
        
        // Resize subpanels
        subpanelChartsRef.current.forEach(subChart => {
          subChart.applyOptions({ width, height: subpanelHeight });
        });
      }
    };

    resizeObserverRef.current = new ResizeObserver(handleResize);
    resizeObserverRef.current.observe(chartContainerRef.current);
    handleResize();

    return () => {
      resizeObserverRef.current?.disconnect();
      chart.remove();
      mainChartRef.current = null;
      candlestickSeriesRef.current = null;
      volumeSeriesRef.current = null;
      mainIndicatorSeriesRef.current.clear();
    };
  }, [colors, createChartOptions, showVolume]);

  // Calculate main chart height based on subpanels
  const calculateMainChartHeight = useCallback(() => {
    const baseHeight = isFullscreen ? window.innerHeight - 150 : height;
    const subpanelCount = subpanelIndicators.length;
    return Math.max(200, baseHeight - subpanelCount * (subpanelHeight + 8));
  }, [height, isFullscreen, subpanelIndicators.length, subpanelHeight]);

  // =============================================================================
  // DATA UPDATE
  // =============================================================================

  // Update main chart data
  useEffect(() => {
    if (!candlestickSeriesRef.current || !data.length) return;

    const chartData: CandlestickData<Time>[] = sortAndDeduplicateData(
      data.map(d => ({
        time: parseTime(d.timestamp),
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }))
    );

    candlestickSeriesRef.current.setData(chartData);

    // Update volume data
    if (volumeSeriesRef.current && showVolume) {
      const volumeData: HistogramData<Time>[] = data.map((d) => ({
        time: parseTime(d.timestamp),
        value: d.volume,
        color: d.close >= d.open ? colors.up : colors.down,
      }));
      volumeSeriesRef.current.setData(sortAndDeduplicateData(volumeData));
    }

    // Fit content
    if (mainChartRef.current) {
      mainChartRef.current.timeScale().fitContent();
    }
  }, [data, showVolume, colors]);

  // =============================================================================
  // INDICATORS
  // =============================================================================

  // Update main chart indicators
  useEffect(() => {
    if (!mainChartRef.current) return;

    // Clear existing main indicators
    mainIndicatorSeriesRef.current.forEach((series) => {
      mainChartRef.current?.removeSeries(series);
    });
    mainIndicatorSeriesRef.current.clear();

    // Add main indicators
    mainIndicators.forEach((indicator, index) => {
      if (!mainChartRef.current) return;

      const color = indicator.color || INDICATOR_COLORS[index % INDICATOR_COLORS.length];

      // Handle multi-line indicators (Bollinger Bands)
      if (indicator.upper && indicator.middle && indicator.lower) {
        const upperSeries = mainChartRef.current.addLineSeries({
          color: color,
          lineWidth: 1,
          title: `${indicator.name} Upper`,
          lastValueVisible: false,
        });
        const lowerSeries = mainChartRef.current.addLineSeries({
          color: color,
          lineWidth: 1,
          title: `${indicator.name} Lower`,
          lastValueVisible: false,
        });
        const middleSeries = mainChartRef.current.addLineSeries({
          color: color,
          lineWidth: 2,
          title: `${indicator.name} Middle`,
        });

        const timestamps = indicator.timestamps || data.map(d => d.timestamp);
        
        upperSeries.setData(
          indicator.upper.map((v, i) => ({
            time: parseTime(timestamps[i]),
            value: v || 0,
          })).filter(d => d.value !== 0)
        );
        lowerSeries.setData(
          indicator.lower.map((v, i) => ({
            time: parseTime(timestamps[i]),
            value: v || 0,
          })).filter(d => d.value !== 0)
        );
        middleSeries.setData(
          indicator.middle.map((v, i) => ({
            time: parseTime(timestamps[i]),
            value: v || 0,
          })).filter(d => d.value !== 0)
        );

        mainIndicatorSeriesRef.current.set(`${indicator.id}-upper`, upperSeries as ISeriesApi<SeriesType>);
        mainIndicatorSeriesRef.current.set(`${indicator.id}-lower`, lowerSeries as ISeriesApi<SeriesType>);
        mainIndicatorSeriesRef.current.set(`${indicator.id}-middle`, middleSeries as ISeriesApi<SeriesType>);
      } else if (indicator.values) {
        // Single line indicator
        const series = mainChartRef.current.addLineSeries({
          color: color,
          lineWidth: 2,
          title: indicator.name,
        });

        const timestamps = indicator.timestamps || data.map(d => d.timestamp);
        const lineData = indicator.values.map((v, i) => ({
          time: parseTime(timestamps[i]),
          value: v || 0,
        })).filter(d => d.value !== 0);

        series.setData(lineData);
        mainIndicatorSeriesRef.current.set(indicator.id, series as ISeriesApi<SeriesType>);
      }
    });
  }, [mainIndicators, data]);

  // Initialize subpanel charts
  useEffect(() => {
    // Cleanup removed subpanels
    const currentIds = new Set(subpanelIndicators.map(ind => ind.id));
    subpanelChartsRef.current.forEach((chart, id) => {
      if (!currentIds.has(id)) {
        chart.remove();
        subpanelChartsRef.current.delete(id);
      }
    });

    // Create new subpanels
    subpanelIndicators.forEach((indicator, idx) => {
      if (subpanelChartsRef.current.has(indicator.id)) return;

      const subContainer = document.getElementById(`subpanel-${indicator.id}`);
      if (!subContainer) return;

      const subChart = createChart(subContainer, {
        layout: {
          background: { color: colors.background },
          textColor: colors.text,
          fontSize: 11,
        },
        grid: {
          vertLines: { color: colors.grid },
          horzLines: { color: colors.grid },
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: { visible: false, labelVisible: false },
          horzLine: { visible: false, labelVisible: false },
        },
        rightPriceScale: {
          borderColor: colors.border,
          scaleMargins: { top: 0.1, bottom: 0.1 },
        },
        timeScale: {
          visible: idx === subpanelIndicators.length - 1, // Only show time on last subpanel
          borderColor: colors.border,
          timeVisible: ['1m', '5m', '15m', '30m', '1h'].includes(timeframe),
        },
        handleScroll: { vertTouchDrag: false },
      });

      // Sync time scale with main chart
      if (mainChartRef.current) {
        subChart.timeScale().applyOptions({
          rightOffset: mainChartRef.current.timeScale().options().rightOffset,
          barSpacing: mainChartRef.current.timeScale().options().barSpacing,
        });
      }

      subpanelChartsRef.current.set(indicator.id, subChart);
    });

    return () => {
      subpanelChartsRef.current.forEach(chart => chart.remove());
      subpanelChartsRef.current.clear();
    };
  }, [subpanelIndicators, colors, timeframe]);

  // Update subpanel data
  useEffect(() => {
    subpanelIndicators.forEach((indicator, index) => {
      const chart = subpanelChartsRef.current.get(indicator.id);
      if (!chart) return;

      // Remove existing series
      const existingKey = `subpanel-${indicator.id}`;
      const existingSeries = subpanelSeriesRef.current.get(existingKey);
      if (existingSeries) {
        chart.removeSeries(existingSeries);
        subpanelSeriesRef.current.delete(existingKey);
      }

      const color = indicator.color || INDICATOR_COLORS[index % INDICATOR_COLORS.length];
      const timestamps = indicator.timestamps || data.map(d => d.timestamp);

      // Handle different subpanel indicator types
      if (indicator.histogram) {
        // MACD-style histogram
        const histogramSeries = chart.addHistogramSeries({
          color: color,
          base: 0,
        });

        const histData = indicator.histogram.map((v, i) => ({
          time: parseTime(timestamps[i]),
          value: v || 0,
          color: (v || 0) >= 0 ? colors.up : colors.down,
        }));
        histogramSeries.setData(sortAndDeduplicateData(histData));
        subpanelSeriesRef.current.set(existingKey, histogramSeries as ISeriesApi<SeriesType>);

        // Add signal line if present
        if (indicator.signal) {
          const signalSeries = chart.addLineSeries({
            color: INDICATOR_COLORS[(index + 1) % INDICATOR_COLORS.length],
            lineWidth: 1,
          });
          const signalData = indicator.signal.map((v, i) => ({
            time: parseTime(timestamps[i]),
            value: v || 0,
          })).filter(d => d.value !== 0);
          signalSeries.setData(sortAndDeduplicateData(signalData));
        }
      } else if (indicator.values) {
        // Line indicator (RSI, etc.)
        const series = chart.addLineSeries({
          color: color,
          lineWidth: 2,
          title: indicator.name,
        });

        const lineData = indicator.values.map((v, i) => ({
          time: parseTime(timestamps[i]),
          value: v || 0,
        })).filter(d => d.value !== 0);

        series.setData(sortAndDeduplicateData(lineData));
        subpanelSeriesRef.current.set(existingKey, series as ISeriesApi<SeriesType>);

        // Add overbought/oversold lines for RSI-like indicators
        if (indicator.id.toLowerCase().includes('rsi') || indicator.id.toLowerCase().includes('stochastic')) {
          const overbought = chart.addLineSeries({
            color: colors.down,
            lineWidth: 1,
            lineStyle: 2,
            lastValueVisible: false,
            title: 'OB',
          });
          const oversold = chart.addLineSeries({
            color: colors.up,
            lineWidth: 1,
            lineStyle: 2,
            lastValueVisible: false,
            title: 'OS',
          });

          const obLevel = indicator.params?.overbought || 70;
          const osLevel = indicator.params?.oversold || 30;

          if (timestamps.length > 0) {
            const obData = timestamps.map(t => ({ time: parseTime(t), value: obLevel }));
            const osData = timestamps.map(t => ({ time: parseTime(t), value: osLevel }));
            overbought.setData(obData);
            oversold.setData(osData);
          }
        }
      }
    });
  }, [subpanelIndicators, data, colors]);

  // =============================================================================
  // OVERLAYS
  // =============================================================================

  // Update correlated assets overlay
  useEffect(() => {
    if (!mainChartRef.current) return;

    // Remove existing correlated series
    correlatedSeriesRef.current.forEach((series) => {
      mainChartRef.current?.removeSeries(series);
    });
    correlatedSeriesRef.current.clear();

    // Add correlated assets
    filteredCorrelations.forEach((asset, corrIdx) => {
      if (!mainChartRef.current) return;

      const series = mainChartRef.current.addLineSeries({
        color: asset.color || INDICATOR_COLORS[(corrIdx + 5) % INDICATOR_COLORS.length],
        lineWidth: 1,
        title: asset.symbol,
        priceScaleId: 'correlation-' + asset.symbol,
        lastValueVisible: true,
      });

      // Normalize data to percentage change for comparison
      const firstPrice = asset.data[0]?.close;
      if (firstPrice) {
        const normalizedData = asset.data.map(d => ({
          time: parseTime(d.timestamp),
          value: ((d.close - firstPrice) / firstPrice) * 100,
        }));
        series.setData(sortAndDeduplicateData(normalizedData));
      }

      correlatedSeriesRef.current.set(asset.symbol, series);
    });
  }, [filteredCorrelations]);

  // Update trade lines
  useEffect(() => {
    if (!mainChartRef.current) return;

    // Remove existing trade lines
    tradeLinesRef.current.forEach((series) => {
      mainChartRef.current?.removeSeries(series);
    });
    tradeLinesRef.current.clear();

    if (!showLiveTradeLines) return;

    const allTrades = [...liveTradeLines, ...(showStrategy ? strategyTrades : [])];

    allTrades.forEach((trade) => {
      if (!mainChartRef.current) return;

      const lineColor = trade.color || TRADE_LINE_COLORS[trade.type];
      const series = mainChartRef.current.addLineSeries({
        color: lineColor,
        lineWidth: 2,
        lineStyle: 2, // Dashed
        title: trade.label || trade.type.toUpperCase(),
        lastValueVisible: true,
      });

      // Create horizontal line at price level
      const data: LineData<Time>[] = [
        { time: trade.time, value: trade.price },
      ];

      // Extend to current time
      const lastCandle = data[data.length - 1];
      if (lastCandle && mainChartRef.current) {
        const currentTime = mainChartRef.current.timeScale().getVisibleLogicalRange();
        if (currentTime) {
          // Add endpoint at right edge
          data.push({ time: trade.time, value: trade.price });
        }
      }

      series.setData(data);
      tradeLinesRef.current.set(trade.id, series);
    });
  }, [liveTradeLines, strategyTrades, showLiveTradeLines, showStrategy]);

  // Update support/resistance levels
  useEffect(() => {
    if (!mainChartRef.current) return;

    // Remove existing S/R lines
    srLinesRef.current.forEach((series) => {
      mainChartRef.current?.removeSeries(series);
    });
    srLinesRef.current.clear();

    if (!showSupportResistance) return;

    supportResistanceLevels.forEach((level, levelIdx) => {
      if (!mainChartRef.current) return;

      const lineColor = level.type === 'support' ? colors.up : colors.down;
      const opacity = Math.max(0.3, level.strength);
      
      const series = mainChartRef.current.addLineSeries({
        color: lineColor.replace(')', `, ${opacity})`).replace('rgb', 'rgba').replace('#', ''),
        lineWidth: Math.min(4, 1 + Math.round(level.strength * 2)) as 1 | 2 | 3 | 4,
        lineStyle: 3, // Dotted
        lastValueVisible: false,
      });

      // Create horizontal line
      const timestamps = data.map(d => parseTime(d.timestamp));
      const lineData = timestamps.map(t => ({
        time: t,
        value: level.price,
      }));

      series.setData(lineData);
      srLinesRef.current.set(`sr-${levelIdx}`, series);
    });
  }, [supportResistanceLevels, showSupportResistance, data, colors]);

  // =============================================================================
  // CHART TYPE CHANGE
  // =============================================================================

  useEffect(() => {
    if (!mainChartRef.current || !candlestickSeriesRef.current) return;

    // Note: Chart type switching would require removing and re-adding series
    // For now, we'll keep candlestick as the main type and note this for future enhancement
    onChartTypeChange?.(chartType);
  }, [chartType, onChartTypeChange]);

  // =============================================================================
  // EXPORT & FULLSCREEN
  // =============================================================================

  const exportChartImage = useCallback(() => {
    if (!mainChartRef.current) return;

    const dataUrl = mainChartRef.current.takeScreenshot();
    const link = document.createElement('a');
    link.download = `${symbol}_${timeframe}_${new Date().toISOString().split('T')[0]}.png`;
    link.href = (dataUrl as unknown) as string;
    link.click();
  }, [symbol, timeframe]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev);
  }, []);

  // =============================================================================
  // RENDER HELPERS
  // =============================================================================

  const timeframeOptions = ALL_TIMEFRAMES.filter(tf => availableTimeframes.includes(tf.value));

  const getIndicatorCategory = (indicator: IndicatorData): string => {
    if (indicator.category) return indicator.category;
    const id = indicator.id.toLowerCase();
    if (id.includes('sma') || id.includes('ema') || id.includes('macd')) return 'trend';
    if (id.includes('rsi') || id.includes('stochastic')) return 'momentum';
    if (id.includes('bollinger') || id.includes('atr')) return 'volatility';
    if (id.includes('obv') || id.includes('volume')) return 'volume';
    return 'trend';
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'trend': return <TrendingUp className="h-3.5 w-3.5" />;
      case 'momentum': return <Activity className="h-3.5 w-3.5" />;
      case 'volatility': return <BarChart3 className="h-3.5 w-3.5" />;
      case 'volume': return <Layers className="h-3.5 w-3.5" />;
      default: return <Activity className="h-3.5 w-3.5" />;
    }
  };

  // =============================================================================
  // RENDER
  // =============================================================================

  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border border-border overflow-hidden bg-background",
        isFullscreen && "fixed inset-0 z-50 rounded-none",
        className
      )}
    >
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
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="font-mono text-sm">
                  {symbol}
                </Badge>
                <Badge variant="outline" className="text-xs">
                  {timeframe}
                </Badge>
              </div>
            )}

            {/* Timeframe Selector */}
            {onTimeframeChange && (
              <Select value={timeframe} onValueChange={(v) => onTimeframeChange(v as Granularity)}>
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

            {/* Data Source Badge */}
            <Badge variant="outline" className="text-xs capitalize">
              {dataSource}
            </Badge>
          </div>

          <div className="flex items-center gap-2">
            {/* Chart Type Toggle */}
            <div className="flex items-center gap-1 bg-muted rounded-md p-1">
              <Toggle
                pressed={chartType === 'candlestick'}
                onPressedChange={() => setChartType('candlestick')}
                className="h-6 w-6 p-0 data-[state=on]:bg-background"
                aria-label="Candlestick"
              >
                <BarChart3 className="h-3.5 w-3.5" />
              </Toggle>
              <Toggle
                pressed={chartType === 'line'}
                onPressedChange={() => setChartType('line')}
                className="h-6 w-6 p-0 data-[state=on]:bg-background"
                aria-label="Line"
              >
                <LineChart className="h-3.5 w-3.5" />
              </Toggle>
            </div>

            <Separator orientation="vertical" className="h-6" />

            {/* Volume Toggle */}
            <Toggle
              pressed={showVolume}
              onPressedChange={setShowVolume}
              className="h-8 px-2 gap-1"
              aria-label="Volume"
            >
              <Layers className="h-4 w-4" />
              <span className="text-xs hidden sm:inline">Vol</span>
            </Toggle>

            {/* Crosshair Toggle */}
            <Toggle
              pressed={showCrosshair}
              onPressedChange={setShowCrosshair}
              className="h-8 px-2 gap-1"
              aria-label="Crosshair"
            >
              <Crosshair className="h-4 w-4" />
            </Toggle>

            {/* Settings */}
            <Dialog open={isSettingsOpen} onOpenChange={setIsSettingsOpen}>
              <DialogTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <Settings className="h-4 w-4" />
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle>Chart Settings</DialogTitle>
                </DialogHeader>
                <Tabs defaultValue="indicators" className="w-full">
                  <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="indicators">Indicators</TabsTrigger>
                    <TabsTrigger value="overlays">Overlays</TabsTrigger>
                    <TabsTrigger value="display">Display</TabsTrigger>
                  </TabsList>

                  <TabsContent value="indicators" className="space-y-4 mt-4">
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <Label>Active Indicators ({activeIndicators.length})</Label>
                        <ScrollArea className="h-48 border rounded-md p-2">
                          {activeIndicators.length === 0 ? (
                            <p className="text-sm text-muted-foreground text-center py-4">
                              No active indicators
                            </p>
                          ) : (
                            <div className="space-y-2">
                              {activeIndicators.map((ind, i) => (
                                <div
                                  key={ind.id}
                                  className="flex items-center justify-between p-2 rounded bg-muted"
                                >
                                  <div className="flex items-center gap-2">
                                    {getCategoryIcon(getIndicatorCategory(ind))}
                                    <span className="text-sm">{ind.name}</span>
                                    {ind.subpanel && (
                                      <Badge variant="outline" className="text-xs">Sub</Badge>
                                    )}
                                  </div>
                                  <div
                                    className="w-3 h-3 rounded-full"
                                    style={{ backgroundColor: ind.color || INDICATOR_COLORS[i % INDICATOR_COLORS.length] }}
                                  />
                                </div>
                              ))}
                            </div>
                          )}
                        </ScrollArea>
                      </div>

                      <div className="space-y-2">
                        <Label>Subpanel Height</Label>
                        <Slider
                          value={[subpanelHeight]}
                          onValueChange={([v]) => setSubpanelHeight(v)}
                          min={80}
                          max={200}
                          step={10}
                        />
                        <span className="text-xs text-muted-foreground">{subpanelHeight}px</span>
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="overlays" className="space-y-4 mt-4">
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <Label className="flex items-center gap-2">
                          <Target className="h-4 w-4" />
                          Strategy Overlay
                        </Label>
                        <Switch checked={showStrategy} onCheckedChange={() => {}} />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label className="flex items-center gap-2">
                          <GitBranch className="h-4 w-4" />
                          Trade Lines
                        </Label>
                        <Switch checked={showLiveTradeLines} onCheckedChange={() => {}} />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label className="flex items-center gap-2">
                          <TrendingUp className="h-4 w-4" />
                          Support/Resistance
                        </Label>
                        <Switch checked={showSupportResistance} onCheckedChange={() => {}} />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label className="flex items-center gap-2">
                          <Activity className="h-4 w-4" />
                          Volume Profile
                        </Label>
                        <Switch checked={showVolumeProfile} onCheckedChange={() => {}} />
                      </div>

                      <Separator />

                      <div className="space-y-2">
                        <Label>Correlation Filter</Label>
                        <div className="flex items-center gap-2">
                          <Switch checked={hideWeakCorrelations} onCheckedChange={() => {}} />
                          <span className="text-sm">Hide weak correlations</span>
                        </div>
                        {hideWeakCorrelations && (
                          <div className="pt-2">
                            <Label className="text-xs">Min Correlation: {minCorrelation}</Label>
                            <Slider
                              value={[minCorrelation || 0.3]}
                              min={0}
                              max={1}
                              step={0.1}
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="display" className="space-y-4 mt-4">
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <Label>Show Volume</Label>
                        <Switch checked={showVolume} onCheckedChange={setShowVolume} />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label>Show Crosshair</Label>
                        <Switch checked={showCrosshair} onCheckedChange={setShowCrosshair} />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label>Show Legend</Label>
                        <Switch checked={showLegend} onCheckedChange={() => {}} />
                      </div>
                    </div>
                  </TabsContent>
                </Tabs>
              </DialogContent>
            </Dialog>

            {/* Export Image */}
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={exportChartImage}>
              <Camera className="h-4 w-4" />
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

      {/* Price/Time Tooltip */}
      {(hoveredPrice || hoveredTime) && (
        <div className="absolute top-14 right-4 z-10 bg-card/95 border rounded-md px-3 py-2 text-sm shadow-lg">
          {hoveredPrice && (
            <div className="font-mono font-medium">
              {formatPrice(hoveredPrice)}
            </div>
          )}
          {hoveredTime && (
            <div className="text-xs text-muted-foreground">
              {new Date((hoveredTime as number) * 1000).toLocaleString()}
            </div>
          )}
        </div>
      )}

      {/* Chart Container */}
      <div className="relative flex-1 overflow-hidden">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-20">
            <div className="flex flex-col items-center gap-3">
              <Loader2 className="h-10 w-10 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Loading chart data...</p>
            </div>
          </div>
        )}

        {!isLoading && data.length === 0 && (
          <div className="w-full h-full flex items-center justify-center">
            <div className="text-center">
              <BarChart3 className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground text-lg">
                No chart data available
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                {symbol} @ {timeframe}
              </p>
            </div>
          </div>
        )}

        {/* Main Chart */}
        <div className="flex flex-col h-full">
          <div
            ref={chartContainerRef}
            style={{ height: calculateMainChartHeight() }}
            className="w-full"
          />

          {/* Subpanels */}
          {subpanelIndicators.map((indicator) => (
            <div
              key={indicator.id}
              id={`subpanel-${indicator.id}`}
              style={{ height: subpanelHeight }}
              className="w-full border-t border-border relative group"
            >
              {/* Subpanel Header */}
              <div className="absolute top-1 left-2 z-10 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <Badge variant="secondary" className="text-xs px-1.5 py-0 h-5">
                  {getCategoryIcon(getIndicatorCategory(indicator))}
                  <span className="ml-1">{indicator.name}</span>
                </Badge>
              </div>

              {/* Resize Handle */}
              <div className="absolute bottom-0 left-0 right-0 h-1 cursor-ns-resize hover:bg-primary/50 transition-colors" />
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      {showLegend && (activeIndicators.length > 0 || filteredCorrelations.length > 0) && (
        <div className="flex items-center flex-wrap gap-x-4 gap-y-1 px-3 py-2 border-t border-border bg-card text-xs">
          {/* Main Symbol */}
          <span className="font-semibold flex items-center gap-1">
            <BarChart3 className="h-3 w-3" />
            {symbol}
          </span>

          {/* Indicators */}
          {mainIndicators.map((ind, i) => (
            <span key={ind.id} className="flex items-center gap-1 text-muted-foreground">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: ind.color || INDICATOR_COLORS[i % INDICATOR_COLORS.length] }}
              />
              {ind.name}
            </span>
          ))}

          {/* Subpanel Indicators */}
          {subpanelIndicators.length > 0 && (
            <span className="flex items-center gap-1 text-muted-foreground">
              <Layers className="h-3 w-3" />
              {subpanelIndicators.length} subpanel
            </span>
          )}

          {/* Correlations */}
          {filteredCorrelations.map((asset, i) => (
            <span key={asset.symbol} className="flex items-center gap-1 text-muted-foreground">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: asset.color || INDICATOR_COLORS[(i + 5) % INDICATOR_COLORS.length] }}
              />
              {asset.symbol} ({(asset.correlation * 100).toFixed(0)}%)
            </span>
          ))}

          {/* Strategy */}
          {showStrategy && strategyName && (
            <span className="flex items-center gap-1 text-muted-foreground">
              <Target className="h-3 w-3" />
              {strategyName}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// EXPORTS
// =============================================================================

export default AdvancedChart;
