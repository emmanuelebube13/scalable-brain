/**
 * CustomChart - HTML5 Canvas-based chart component for financial data.
 *
 * Features:
 * - Candlestick and line chart rendering
 * - Technical indicators overlay (SMA, EMA, Bollinger Bands)
 * - Volume bars
 * - Trade entry/SL/TP visualization
 * - Support/resistance levels
 * - Zoom and pan
 * - Trend line drawing
 * - Real-time price updates
 */

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
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
  ZoomIn,
  ZoomOut,
  Move,
  Pencil,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// =============================================================================
// TYPES
// =============================================================================

export type Granularity = '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d';
export type ChartType = 'candlestick' | 'line';

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
  values?: (number | null)[];
  upper?: (number | null)[];
  middle?: (number | null)[];
  lower?: (number | null)[];
  signal?: (number | null)[];
  histogram?: (number | null)[];
  timestamps?: string[];
}

export interface TradeMarker {
  id: string;
  type: 'entry' | 'sl' | 'tp' | 'win' | 'loss';
  price: number;
  timestamp: string;
  side?: 'long' | 'short';
  label?: string;
}

export interface SupportResistanceLevel {
  price: number;
  strength: number;
  type: 'support' | 'resistance';
  touches: number;
}

export interface ChartTool {
  id: string;
  type: 'trendline' | 'horizontal' | 'fibonacci' | 'rectangle';
  points: { x: number; y: number; price: number; timestamp: string }[];
  color?: string;
}

export interface CustomChartProps {
  symbol: string;
  timeframe: Granularity;
  data: OHLCData[];
  isLoading?: boolean;
  currentPrice?: number;
  
  // Indicators
  activeIndicators?: IndicatorData[];
  
  // Overlays
  tradeMarkers?: TradeMarker[];
  showTradeMarkers?: boolean;
  supportResistanceLevels?: SupportResistanceLevel[];
  showSupportResistance?: boolean;
  
  // Tools
  activeTool?: 'cursor' | 'trendline' | 'horizontal' | 'fibonacci' | 'pan' | null;
  onToolChange?: (tool: 'cursor' | 'trendline' | 'horizontal' | 'fibonacci' | 'pan' | null) => void;
  onDrawTool?: (tool: ChartTool) => void;
  drawnTools?: ChartTool[];
  onRemoveTool?: (id: string) => void;
  
  // Appearance
  height?: number;
  className?: string;
  showToolbar?: boolean;
  allowFullscreen?: boolean;
  
  // Callbacks
  onTimeframeChange?: (timeframe: Granularity) => void;
  onChartTypeChange?: (type: ChartType) => void;
  onZoom?: (direction: 'in' | 'out') => void;
  onPan?: (direction: 'left' | 'right') => void;
  
  // Options
  availableTimeframes?: Granularity[];
}

// =============================================================================
// CONSTANTS
// =============================================================================

const ALLOWED_PAIRS = ['EUR_USD', 'GBP_USD', 'USD_JPY', 'AUD_USD', 'USD_CAD'];

const ALL_TIMEFRAMES: { value: Granularity; label: string }[] = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '30m', label: '30m' },
  { value: '1h', label: '1H' },
  { value: '4h', label: '4H' },
  { value: '1d', label: '1D' },
];

const CHART_COLORS = {
  dark: {
    background: '#0B0C0F',
    grid: 'rgba(255, 255, 255, 0.08)',
    text: '#9CA3AF',
    textStrong: '#E5E7EB',
    up: '#22C55E',
    down: '#EF4444',
    wickUp: '#22C55E',
    wickDown: '#EF4444',
    border: 'rgba(255, 255, 255, 0.1)',
    crosshair: 'rgba(255, 255, 255, 0.3)',
    volume: 'rgba(59, 130, 246, 0.4)',
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
    crosshair: 'rgba(0, 0, 0, 0.3)',
    volume: 'rgba(59, 130, 246, 0.4)',
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
];

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

function parseTime(timestamp: string): number {
  return new Date(timestamp).getTime();
}

function formatPrice(price: number, decimals = 5): string {
  return price.toFixed(decimals);
}

function getDecimalPlaces(symbol: string): number {
  // JPY pairs typically have 3 decimal places, others have 5
  return symbol.includes('JPY') ? 3 : 5;
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function CustomChart({
  symbol,
  timeframe,
  data,
  isLoading = false,
  currentPrice,
  activeIndicators = [],
  tradeMarkers = [],
  showTradeMarkers = true,
  supportResistanceLevels = [],
  showSupportResistance = false,
  activeTool = 'cursor',
  onToolChange,
  onDrawTool,
  drawnTools = [],
  onRemoveTool,
  height = 500,
  className,
  showToolbar = true,
  allowFullscreen = true,
  onTimeframeChange,
  onChartTypeChange,
  onZoom,
  onPan,
  availableTimeframes = ALL_TIMEFRAMES.map(t => t.value),
}: CustomChartProps) {
  const { resolvedTheme } = useTheme();
  const colors = CHART_COLORS[resolvedTheme];
  const decimals = getDecimalPlaces(symbol);

  // Refs
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // State
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [chartType, setChartType] = useState<ChartType>('candlestick');
  const [showVolume, setShowVolume] = useState(true);
  const [showCrosshair, setShowCrosshair] = useState(true);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState(0);
  const [hoverData, setHoverData] = useState<{ price: number; timestamp: string; x: number; y: number } | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawingPoints, setDrawingPoints] = useState<{ x: number; y: number; price: number; timestamp: string }[]>([]);
  
  // Canvas dimensions
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 500 });
  
  // Margins for axes
  const margin = { top: 10, right: 60, bottom: 40, left: 10 };
  const volumeHeight = showVolume ? 80 : 0;
  const chartHeight = canvasSize.height - margin.top - margin.bottom - volumeHeight;
  const chartWidth = canvasSize.width - margin.left - margin.right;

  // =============================================================================
  // DATA PREPARATION
  // =============================================================================

  const visibleData = useMemo(() => {
    if (!data.length) return [];
    
    const visibleCount = Math.floor(data.length * zoomLevel);
    const startIndex = Math.max(0, data.length - visibleCount - panOffset);
    const endIndex = Math.min(data.length, startIndex + visibleCount);
    
    return data.slice(startIndex, endIndex);
  }, [data, zoomLevel, panOffset]);

  const priceRange = useMemo(() => {
    if (!visibleData.length) return { min: 0, max: 1, range: 1 };
    
    let min = Infinity;
    let max = -Infinity;
    
    visibleData.forEach(d => {
      min = Math.min(min, d.low);
      max = Math.max(max, d.high);
    });
    
    // Include indicator values in range
    activeIndicators.forEach(ind => {
      if (ind.values) {
        ind.values.forEach(v => {
          if (v !== null) {
            min = Math.min(min, v);
            max = Math.max(max, v);
          }
        });
      }
      if (ind.upper) {
        ind.upper.forEach(v => { if (v !== null) max = Math.max(max, v); });
      }
      if (ind.lower) {
        ind.lower.forEach(v => { if (v !== null) min = Math.min(min, v); });
      }
    });
    
    // Add padding
    const range = max - min;
    const padding = range * 0.1;
    
    return { min: min - padding, max: max + padding, range: range + padding * 2 };
  }, [visibleData, activeIndicators]);

  // =============================================================================
  // CANVAS RENDERING
  // =============================================================================

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    // Clear canvas
    ctx.fillStyle = colors.background;
    ctx.fillRect(0, 0, canvasSize.width, canvasSize.height);
    
    if (!visibleData.length) {
      // Draw "No data" message
      ctx.fillStyle = colors.text;
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('No data available', canvasSize.width / 2, canvasSize.height / 2);
      return;
    }
    
    const candleWidth = chartWidth / visibleData.length * 0.7;
    const candleSpacing = chartWidth / visibleData.length;
    
    // Draw grid
    drawGrid(ctx);
    
    // Draw price axis
    drawPriceAxis(ctx);
    
    // Draw time axis
    drawTimeAxis(ctx, candleSpacing);
    
    // Draw volume
    if (showVolume) {
      drawVolume(ctx, candleSpacing, candleWidth);
    }
    
    // Draw candles/line
    if (chartType === 'candlestick') {
      drawCandles(ctx, candleSpacing, candleWidth);
    } else {
      drawLine(ctx, candleSpacing);
    }
    
    // Draw indicators
    drawIndicators(ctx, candleSpacing);
    
    // Draw support/resistance
    if (showSupportResistance) {
      drawSupportResistance(ctx);
    }
    
    // Draw trade markers
    if (showTradeMarkers) {
      drawTradeMarkers(ctx, candleSpacing);
    }
    
    // Draw drawn tools
    drawTools(ctx);
    
    // Draw crosshair
    if (showCrosshair && hoverData) {
      drawCrosshair(ctx);
    }
    
    // Draw current price line
    if (currentPrice) {
      drawCurrentPriceLine(ctx);
    }
  }, [visibleData, priceRange, colors, chartType, showVolume, showCrosshair, hoverData, currentPrice, activeIndicators, supportResistanceLevels, tradeMarkers, showSupportResistance, showTradeMarkers, drawnTools, drawingPoints]);

  const drawGrid = (ctx: CanvasRenderingContext2D) => {
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 1;
    
    // Horizontal grid lines (price)
    const gridCount = 6;
    for (let i = 0; i <= gridCount; i++) {
      const y = margin.top + (chartHeight / gridCount) * i;
      ctx.beginPath();
      ctx.moveTo(margin.left, y);
      ctx.lineTo(margin.left + chartWidth, y);
      ctx.stroke();
    }
    
    // Vertical grid lines (time)
    const timeGridCount = 8;
    for (let i = 0; i <= timeGridCount; i++) {
      const x = margin.left + (chartWidth / timeGridCount) * i;
      ctx.beginPath();
      ctx.moveTo(x, margin.top);
      ctx.lineTo(x, margin.top + chartHeight);
      ctx.stroke();
    }
  };

  const drawPriceAxis = (ctx: CanvasRenderingContext2D) => {
    ctx.fillStyle = colors.text;
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'left';
    
    const gridCount = 6;
    for (let i = 0; i <= gridCount; i++) {
      const price = priceRange.max - (priceRange.range / gridCount) * i;
      const y = margin.top + (chartHeight / gridCount) * i;
      ctx.fillText(formatPrice(price, decimals), margin.left + chartWidth + 8, y + 4);
    }
  };

  const drawTimeAxis = (ctx: CanvasRenderingContext2D, candleSpacing: number) => {
    ctx.fillStyle = colors.text;
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'center';
    
    const timeGridCount = Math.min(8, visibleData.length);
    const step = Math.ceil(visibleData.length / timeGridCount);
    
    for (let i = 0; i < visibleData.length; i += step) {
      const x = margin.left + candleSpacing * i + candleSpacing / 2;
      const date = new Date(visibleData[i].timestamp);
      const timeStr = timeframe === '1d' 
        ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
        : date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
      ctx.fillText(timeStr, x, margin.top + chartHeight + volumeHeight + 20);
    }
  };

  const drawCandles = (ctx: CanvasRenderingContext2D, candleSpacing: number, candleWidth: number) => {
    visibleData.forEach((candle, i) => {
      const x = margin.left + candleSpacing * i + candleSpacing / 2;
      const isUp = candle.close >= candle.open;
      
      const openY = margin.top + ((priceRange.max - candle.open) / priceRange.range) * chartHeight;
      const closeY = margin.top + ((priceRange.max - candle.close) / priceRange.range) * chartHeight;
      const highY = margin.top + ((priceRange.max - candle.high) / priceRange.range) * chartHeight;
      const lowY = margin.top + ((priceRange.max - candle.low) / priceRange.range) * chartHeight;
      
      // Wick
      ctx.strokeStyle = isUp ? colors.wickUp : colors.wickDown;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();
      
      // Body
      ctx.fillStyle = isUp ? colors.up : colors.down;
      const bodyTop = Math.min(openY, closeY);
      const bodyHeight = Math.max(Math.abs(openY - closeY), 1);
      ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
    });
  };

  const drawLine = (ctx: CanvasRenderingContext2D, candleSpacing: number) => {
    if (visibleData.length < 2) return;
    
    ctx.strokeStyle = colors.up;
    ctx.lineWidth = 2;
    ctx.beginPath();
    
    visibleData.forEach((candle, i) => {
      const x = margin.left + candleSpacing * i + candleSpacing / 2;
      const y = margin.top + ((priceRange.max - candle.close) / priceRange.range) * chartHeight;
      
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    
    ctx.stroke();
  };

  const drawVolume = (ctx: CanvasRenderingContext2D, candleSpacing: number, candleWidth: number) => {
    const maxVolume = Math.max(...visibleData.map(d => d.volume), 1);
    const volumeY = margin.top + chartHeight + 10;
    
    visibleData.forEach((candle, i) => {
      const x = margin.left + candleSpacing * i + candleSpacing / 2;
      const isUp = candle.close >= candle.open;
      const volHeight = (candle.volume / maxVolume) * (volumeHeight - 20);
      
      ctx.fillStyle = isUp ? colors.up : colors.down;
      ctx.globalAlpha = 0.4;
      ctx.fillRect(x - candleWidth / 2, volumeY + (volumeHeight - 20) - volHeight, candleWidth, volHeight);
      ctx.globalAlpha = 1;
    });
  };

  const drawIndicators = (ctx: CanvasRenderingContext2D, candleSpacing: number) => {
    activeIndicators.forEach((ind, idx) => {
      const color = ind.color || INDICATOR_COLORS[idx % INDICATOR_COLORS.length];
      
      // Draw Bollinger Bands
      if (ind.upper && ind.middle && ind.lower) {
        drawIndicatorLine(ctx, ind.upper, color, candleSpacing, 1, ind.timestamps);
        drawIndicatorLine(ctx, ind.middle, color, candleSpacing, 2, ind.timestamps);
        drawIndicatorLine(ctx, ind.lower, color, candleSpacing, 1, ind.timestamps);
      }
      // Draw single line
      else if (ind.values) {
        drawIndicatorLine(ctx, ind.values, color, candleSpacing, 2, ind.timestamps);
      }
    });
  };

  const drawIndicatorLine = (
    ctx: CanvasRenderingContext2D, 
    values: (number | null)[], 
    color: string, 
    candleSpacing: number,
    lineWidth: number,
    timestamps?: string[]
  ) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    
    let started = false;
    values.forEach((value, i) => {
      if (value === null) {
        started = false;
        return;
      }
      
      // Match values to visible data
      const dataIndex = timestamps 
        ? visibleData.findIndex(d => timestamps[i] === d.timestamp)
        : i;
      
      if (dataIndex === -1) return;
      
      const x = margin.left + candleSpacing * dataIndex + candleSpacing / 2;
      const y = margin.top + ((priceRange.max - value) / priceRange.range) * chartHeight;
      
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    });
    
    ctx.stroke();
  };

  const drawSupportResistance = (ctx: CanvasRenderingContext2D) => {
    supportResistanceLevels.forEach(level => {
      const y = margin.top + ((priceRange.max - level.price) / priceRange.range) * chartHeight;
      
      ctx.strokeStyle = level.type === 'support' ? colors.up : colors.down;
      ctx.lineWidth = Math.max(1, level.strength * 3);
      ctx.setLineDash([5, 5]);
      ctx.globalAlpha = Math.max(0.3, level.strength);
      
      ctx.beginPath();
      ctx.moveTo(margin.left, y);
      ctx.lineTo(margin.left + chartWidth, y);
      ctx.stroke();
      
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      
      // Draw label
      ctx.fillStyle = level.type === 'support' ? colors.up : colors.down;
      ctx.font = '10px sans-serif';
      ctx.fillText(
        `${level.type === 'support' ? 'S' : 'R'} ${formatPrice(level.price, decimals)}`,
        margin.left + chartWidth - 70,
        y - 3
      );
    });
  };

  const drawTradeMarkers = (ctx: CanvasRenderingContext2D, candleSpacing: number) => {
    tradeMarkers.forEach(marker => {
      const dataIndex = visibleData.findIndex(d => d.timestamp === marker.timestamp);
      if (dataIndex === -1) return;
      
      const x = margin.left + candleSpacing * dataIndex + candleSpacing / 2;
      const y = margin.top + ((priceRange.max - marker.price) / priceRange.range) * chartHeight;
      
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      
      switch (marker.type) {
        case 'entry':
          ctx.fillStyle = marker.side === 'long' ? colors.up : colors.down;
          ctx.fillText(marker.side === 'long' ? '▲' : '▼', x, y);
          break;
        case 'sl':
          ctx.fillStyle = colors.down;
          ctx.fillText('—', x, y);
          // Draw dashed line
          ctx.strokeStyle = colors.down;
          ctx.setLineDash([3, 3]);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(margin.left, y);
          ctx.lineTo(margin.left + chartWidth, y);
          ctx.stroke();
          ctx.setLineDash([]);
          break;
        case 'tp':
          ctx.fillStyle = colors.up;
          ctx.fillText('—', x, y);
          // Draw dashed line
          ctx.strokeStyle = colors.up;
          ctx.setLineDash([3, 3]);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(margin.left, y);
          ctx.lineTo(margin.left + chartWidth, y);
          ctx.stroke();
          ctx.setLineDash([]);
          break;
        case 'win':
          ctx.fillStyle = colors.up;
          ctx.fillText('✓', x, y);
          break;
        case 'loss':
          ctx.fillStyle = colors.down;
          ctx.fillText('✗', x, y);
          break;
      }
    });
  };

  const drawTools = (ctx: CanvasRenderingContext2D) => {
    drawnTools.forEach(tool => {
      if (tool.points.length < 2) return;
      
      ctx.strokeStyle = tool.color || colors.text;
      ctx.lineWidth = 2;
      
      switch (tool.type) {
        case 'trendline':
          drawTrendLine(ctx, tool.points);
          break;
        case 'horizontal':
          drawHorizontalLine(ctx, tool.points[0]);
          break;
        case 'fibonacci':
          drawFibonacci(ctx, tool.points);
          break;
      }
    });
    
    // Draw in-progress drawing
    if (isDrawing && drawingPoints.length > 0) {
      ctx.strokeStyle = colors.text;
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      
      const lastPoint = drawingPoints[drawingPoints.length - 1];
      const startX = margin.left + ((parseTime(lastPoint.timestamp) - parseTime(visibleData[0].timestamp)) / (parseTime(visibleData[visibleData.length - 1].timestamp) - parseTime(visibleData[0].timestamp))) * chartWidth;
      const startY = margin.top + ((priceRange.max - lastPoint.price) / priceRange.range) * chartHeight;
      
      // This is a simplified preview - in real implementation you'd track mouse position
      ctx.beginPath();
      ctx.arc(startX, startY, 3, 0, Math.PI * 2);
      ctx.stroke();
      
      ctx.setLineDash([]);
    }
  };

  const drawTrendLine = (ctx: CanvasRenderingContext2D, points: typeof drawingPoints) => {
    if (points.length < 2) return;
    
    const p1 = points[0];
    const p2 = points[1];
    
    // Convert data coordinates to canvas coordinates
    const timeRange = parseTime(visibleData[visibleData.length - 1].timestamp) - parseTime(visibleData[0].timestamp);
    const x1 = margin.left + ((parseTime(p1.timestamp) - parseTime(visibleData[0].timestamp)) / timeRange) * chartWidth;
    const y1 = margin.top + ((priceRange.max - p1.price) / priceRange.range) * chartHeight;
    const x2 = margin.left + ((parseTime(p2.timestamp) - parseTime(visibleData[0].timestamp)) / timeRange) * chartWidth;
    const y2 = margin.top + ((priceRange.max - p2.price) / priceRange.range) * chartHeight;
    
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  };

  const drawHorizontalLine = (ctx: CanvasRenderingContext2D, point: typeof drawingPoints[0]) => {
    const y = margin.top + ((priceRange.max - point.price) / priceRange.range) * chartHeight;
    
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(margin.left + chartWidth, y);
    ctx.stroke();
    ctx.setLineDash([]);
  };

  const drawFibonacci = (ctx: CanvasRenderingContext2D, points: typeof drawingPoints) => {
    if (points.length < 2) return;
    
    const p1 = points[0];
    const p2 = points[1];
    
    const y1 = margin.top + ((priceRange.max - p1.price) / priceRange.range) * chartHeight;
    const y2 = margin.top + ((priceRange.max - p2.price) / priceRange.range) * chartHeight;
    
    const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
    const priceDiff = p2.price - p1.price;
    
    levels.forEach(level => {
      const price = p1.price + priceDiff * level;
      const y = margin.top + ((priceRange.max - price) / priceRange.range) * chartHeight;
      
      ctx.strokeStyle = colors.text;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      ctx.moveTo(margin.left, y);
      ctx.lineTo(margin.left + chartWidth, y);
      ctx.stroke();
      
      ctx.fillStyle = colors.text;
      ctx.font = '10px sans-serif';
      ctx.fillText(`${(level * 100).toFixed(1)}%`, margin.left + chartWidth - 40, y - 2);
    });
    
    ctx.globalAlpha = 1;
  };

  const drawCrosshair = (ctx: CanvasRenderingContext2D) => {
    if (!hoverData) return;
    
    ctx.strokeStyle = colors.crosshair;
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    
    // Vertical line
    ctx.beginPath();
    ctx.moveTo(hoverData.x, margin.top);
    ctx.lineTo(hoverData.x, margin.top + chartHeight + volumeHeight);
    ctx.stroke();
    
    // Horizontal line
    ctx.beginPath();
    ctx.moveTo(margin.left, hoverData.y);
    ctx.lineTo(margin.left + chartWidth, hoverData.y);
    ctx.stroke();
    
    ctx.setLineDash([]);
    
    // Price label
    ctx.fillStyle = colors.background;
    ctx.fillRect(margin.left + chartWidth + 2, hoverData.y - 10, 56, 20);
    ctx.strokeStyle = colors.border;
    ctx.strokeRect(margin.left + chartWidth + 2, hoverData.y - 10, 56, 20);
    ctx.fillStyle = colors.textStrong;
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(formatPrice(hoverData.price, decimals), margin.left + chartWidth + 6, hoverData.y + 4);
  };

  const drawCurrentPriceLine = (ctx: CanvasRenderingContext2D) => {
    if (!currentPrice || currentPrice < priceRange.min || currentPrice > priceRange.max) return;
    
    const y = margin.top + ((priceRange.max - currentPrice) / priceRange.range) * chartHeight;
    
    ctx.strokeStyle = colors.text;
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);
    
    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(margin.left + chartWidth, y);
    ctx.stroke();
    
    ctx.setLineDash([]);
    
    // Price label
    ctx.fillStyle = colors.text;
    ctx.fillRect(margin.left + chartWidth + 2, y - 10, 56, 20);
    ctx.fillStyle = colors.background;
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(formatPrice(currentPrice, decimals), margin.left + chartWidth + 6, y + 4);
  };

  // =============================================================================
  // EVENT HANDLERS
  // =============================================================================

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !visibleData.length) return;
    
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    // Check if within chart area
    if (x < margin.left || x > margin.left + chartWidth ||
        y < margin.top || y > margin.top + chartHeight) {
      setHoverData(null);
      return;
    }
    
    // Calculate price and timestamp
    const price = priceRange.max - ((y - margin.top) / chartHeight) * priceRange.range;
    
    const candleIndex = Math.floor((x - margin.left) / (chartWidth / visibleData.length));
    const candle = visibleData[Math.min(candleIndex, visibleData.length - 1)];
    
    setHoverData({
      price,
      timestamp: candle?.timestamp || '',
      x,
      y,
    });
    
    // Handle drawing
    if (isDrawing && (activeTool === 'trendline' || activeTool === 'fibonacci')) {
      // Update drawing preview
    }
  }, [visibleData, priceRange, chartWidth, chartHeight, isDrawing, activeTool]);

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!activeTool || activeTool === 'cursor' || activeTool === 'pan') return;
    
    const canvas = canvasRef.current;
    if (!canvas || !visibleData.length) return;
    
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const price = priceRange.max - ((y - margin.top) / chartHeight) * priceRange.range;
    const candleIndex = Math.floor((x - margin.left) / (chartWidth / visibleData.length));
    const candle = visibleData[Math.min(candleIndex, visibleData.length - 1)];
    
    if (activeTool === 'horizontal') {
      // Complete horizontal line immediately
      onDrawTool?.({
        id: `tool_${Date.now()}`,
        type: 'horizontal',
        points: [{ x, y, price, timestamp: candle.timestamp }],
        color: colors.text,
      });
    } else {
      setIsDrawing(true);
      setDrawingPoints([{ x, y, price, timestamp: candle.timestamp }]);
    }
  }, [activeTool, visibleData, priceRange, chartWidth, chartHeight, onDrawTool, colors]);

  const handleMouseUp = useCallback(() => {
    if (!isDrawing || drawingPoints.length === 0) return;
    
    if (drawingPoints.length >= 2) {
      onDrawTool?.({
        id: `tool_${Date.now()}`,
        type: activeTool as 'trendline' | 'fibonacci',
        points: drawingPoints,
        color: colors.text,
      });
    }
    
    setIsDrawing(false);
    setDrawingPoints([]);
  }, [isDrawing, drawingPoints, activeTool, onDrawTool, colors]);

  const handleMouseLeave = useCallback(() => {
    setHoverData(null);
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    
    if (e.deltaY < 0) {
      // Zoom in
      setZoomLevel(prev => Math.min(prev * 1.1, 3));
      onZoom?.('in');
    } else {
      // Zoom out
      setZoomLevel(prev => Math.max(prev * 0.9, 0.3));
      onZoom?.('out');
    }
  }, [onZoom]);

  // =============================================================================
  // CONTROLS
  // =============================================================================

  const handleZoomIn = () => {
    setZoomLevel(prev => Math.min(prev * 1.2, 3));
    onZoom?.('in');
  };

  const handleZoomOut = () => {
    setZoomLevel(prev => Math.max(prev * 0.8, 0.3));
    onZoom?.('out');
  };

  const handlePanLeft = () => {
    setPanOffset(prev => prev + Math.floor(visibleData.length * 0.2));
    onPan?.('left');
  };

  const handlePanRight = () => {
    setPanOffset(prev => Math.max(0, prev - Math.floor(visibleData.length * 0.2)));
    onPan?.('right');
  };

  const toggleFullscreen = () => {
    setIsFullscreen(prev => !prev);
  };

  const exportImage = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const link = document.createElement('a');
    link.download = `${symbol}_${timeframe}_${new Date().toISOString().split('T')[0]}.png`;
    link.href = canvas.toDataURL();
    link.click();
  };

  // =============================================================================
  // EFFECTS
  // =============================================================================

  // Update canvas size on resize
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setCanvasSize({
          width: rect.width,
          height: isFullscreen ? window.innerHeight - 150 : height,
        });
      }
    };

    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, [height, isFullscreen]);

  // Redraw on data change
  useEffect(() => {
    draw();
  }, [draw]);

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
        <div className="flex items-center justify-between p-2 border-b border-border bg-card">
          <div className="flex items-center gap-2">
            {/* Symbol Badge */}
            <Badge variant="secondary" className="font-mono text-sm">
              {symbol.replace('_', '/')}
            </Badge>

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

            {/* Chart Type Toggle */}
            <div className="flex items-center gap-1 bg-muted rounded-md p-1">
              <Toggle
                pressed={chartType === 'candlestick'}
                onPressedChange={() => {
                  setChartType('candlestick');
                  onChartTypeChange?.('candlestick');
                }}
                className="h-6 w-6 p-0 data-[state=on]:bg-background"
                aria-label="Candlestick"
              >
                <BarChart3 className="h-3.5 w-3.5" />
              </Toggle>
              <Toggle
                pressed={chartType === 'line'}
                onPressedChange={() => {
                  setChartType('line');
                  onChartTypeChange?.('line');
                }}
                className="h-6 w-6 p-0 data-[state=on]:bg-background"
                aria-label="Line"
              >
                <LineChart className="h-3.5 w-3.5" />
              </Toggle>
            </div>

            <Separator orientation="vertical" className="h-6" />

            {/* Drawing Tools */}
            <div className="flex items-center gap-1">
              <Toggle
                pressed={activeTool === 'cursor'}
                onPressedChange={() => onToolChange?.('cursor')}
                className="h-8 w-8 p-0"
                aria-label="Cursor"
              >
                <Crosshair className="h-4 w-4" />
              </Toggle>
              <Toggle
                pressed={activeTool === 'pan'}
                onPressedChange={() => onToolChange?.('pan')}
                className="h-8 w-8 p-0"
                aria-label="Pan"
              >
                <Move className="h-4 w-4" />
              </Toggle>
              <Toggle
                pressed={activeTool === 'trendline'}
                onPressedChange={() => onToolChange?.('trendline')}
                className="h-8 w-8 p-0"
                aria-label="Trendline"
              >
                <TrendingUp className="h-4 w-4" />
              </Toggle>
              <Toggle
                pressed={activeTool === 'horizontal'}
                onPressedChange={() => onToolChange?.('horizontal')}
                className="h-8 w-8 p-0"
                aria-label="Horizontal"
              >
                <Pencil className="h-4 w-4" />
              </Toggle>
            </div>

            <Separator orientation="vertical" className="h-6" />

            {/* Zoom Controls */}
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleZoomIn}>
                <ZoomIn className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleZoomOut}>
                <ZoomOut className="h-4 w-4" />
              </Button>
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
          </div>

          <div className="flex items-center gap-2">
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
                <Tabs defaultValue="display" className="w-full">
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="display">Display</TabsTrigger>
                    <TabsTrigger value="indicators">Indicators</TabsTrigger>
                  </TabsList>

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
                        <Label>Show Trade Markers</Label>
                        <Switch checked={showTradeMarkers} onCheckedChange={() => {}} />
                      </div>
                      <div className="flex items-center justify-between">
                        <Label>Show S/R Levels</Label>
                        <Switch checked={showSupportResistance} onCheckedChange={() => {}} />
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="indicators" className="space-y-4 mt-4">
                    <div className="space-y-2">
                      <Label>Active Indicators ({activeIndicators.length})</Label>
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
                              </div>
                              <div
                                className="w-3 h-3 rounded-full"
                                style={{ backgroundColor: ind.color || INDICATOR_COLORS[i % INDICATOR_COLORS.length] }}
                              />
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </TabsContent>
                </Tabs>
              </DialogContent>
            </Dialog>

            {/* Export Image */}
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={exportImage}>
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

      {/* Chart Container */}
      <div ref={containerRef} className="relative flex-1 overflow-hidden">
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

        <canvas
          ref={canvasRef}
          width={canvasSize.width}
          height={canvasSize.height}
          className="cursor-crosshair"
          onMouseMove={handleMouseMove}
          onMouseDown={handleMouseDown}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
          onWheel={handleWheel}
        />

        {/* Hover Tooltip */}
        {hoverData && (
          <div 
            className="absolute top-2 left-2 bg-card/95 border rounded-md px-3 py-2 text-sm shadow-lg pointer-events-none"
          >
            <div className="font-mono font-medium">
              {formatPrice(hoverData.price, decimals)}
            </div>
            <div className="text-xs text-muted-foreground">
              {new Date(hoverData.timestamp).toLocaleString()}
            </div>
          </div>
        )}

        {/* Current Price */}
        {currentPrice && currentPrice > 0 && (
          <div className="absolute top-2 right-16 bg-primary/10 border border-primary/30 rounded-md px-3 py-1 text-sm">
            <span className="text-muted-foreground text-xs">Live: </span>
            <span className="font-mono font-medium">{formatPrice(currentPrice, decimals)}</span>
          </div>
        )}

        {/* Legend */}
        {activeIndicators.length > 0 && (
          <div className="absolute bottom-2 left-2 flex items-center flex-wrap gap-x-4 gap-y-1 bg-card/90 px-2 py-1 rounded text-xs">
            <span className="font-semibold flex items-center gap-1">
              <BarChart3 className="h-3 w-3" />
              {symbol}
            </span>
            {activeIndicators.map((ind, i) => (
              <span key={ind.id} className="flex items-center gap-1 text-muted-foreground">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: ind.color || INDICATOR_COLORS[i % INDICATOR_COLORS.length] }}
                />
                {ind.name}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default CustomChart;
