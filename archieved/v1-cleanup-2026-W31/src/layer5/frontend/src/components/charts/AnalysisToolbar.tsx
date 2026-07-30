import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { IChartApi, ISeriesApi, Time, MouseEventParams } from 'lightweight-charts';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import {
  TrendingUp,
  Target,
  Percent,
  ScanLine,
  ArrowLeftRight,
  Layers,
  BarChart3,
  GitCompare,
  Clock,
  Trash2,
  Undo2,
  Redo2,
  MousePointer2,
} from 'lucide-react';

// ============================================================================
// Types - AnalysisTool enum is imported from @/types
// ============================================================================

import { AnalysisTool } from '@/types';
export { AnalysisTool };

export interface Pattern {
  id: string;
  type: 'head_and_shoulders' | 'inverse_head_and_shoulders' | 'ascending_triangle' | 'descending_triangle' | 'symmetrical_triangle' | 'channel_up' | 'channel_down' | 'channel_flat';
  name: string;
  confidence: number;
  startTime: number;
  endTime: number;
  priceLevel: number;
  direction: 'bullish' | 'bearish' | 'neutral';
  points: { time: number; price: number }[];
}

export interface Divergence {
  id: string;
  type: 'bullish' | 'bearish';
  indicator: string;
  startTime: number;
  endTime: number;
  priceStart: number;
  priceEnd: number;
  indicatorStart: number;
  indicatorEnd: number;
  strength: 'weak' | 'medium' | 'strong';
}

export interface OrderBlock {
  id: string;
  type: 'bullish' | 'bearish';
  time: number;
  high: number;
  low: number;
  volume: number;
  mitigationLevel: number;
}

export interface SRLevel {
  price: number;
  strength: number;
  touches: number;
  type: 'support' | 'resistance';
}

export interface Trendline {
  id: string;
  startTime: number;
  startPrice: number;
  endTime: number;
  endPrice: number;
  color: string;
  lineWidth: number;
}

export interface FibonacciLevel {
  id: string;
  startTime: number;
  startPrice: number;
  endTime: number;
  endPrice: number;
  levels: { ratio: number; price: number }[];
}

export interface AnalysisObject {
  id: string;
  type: AnalysisTool;
  data: Trendline | FibonacciLevel | SRLevel | Pattern | Divergence | OrderBlock;
  visible: boolean;
  createdAt: number;
}

export interface AnalysisState {
  objects: AnalysisObject[];
  undoStack: AnalysisObject[][];
  redoStack: AnalysisObject[][];
}

export interface AnalysisToolbarProps {
  chart: IChartApi | null;
  candlestickSeries: ISeriesApi<'Candlestick'> | null;
  activeTool: AnalysisTool | null;
  onToolChange: (tool: AnalysisTool | null) => void;
  onSupportResistanceDetected?: (levels: { support: SRLevel[]; resistance: SRLevel[] }) => void;
  onPatternDetected?: (patterns: Pattern[]) => void;
  onDivergenceDetected?: (divergences: Divergence[]) => void;
  onOrderBlocksDetected?: (blocks: OrderBlock[]) => void;
  symbol: string;
  timeframe: string;
  className?: string;
}

// ============================================================================
// Support/Resistance Detection Algorithm
// ============================================================================

export interface OHLC {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * Detect support and resistance levels using pivot algorithm
 * @param data - Array of OHLC data points
 * @param leftBars - Number of bars to look back for pivot (default: 5)
 * @param rightBars - Number of bars to look ahead for pivot (default: 5)
 * @param zoneThreshold - Price proximity threshold for clustering (default: 0.5%)
 * @returns Object with support and resistance levels
 */
export function detectSupportResistance(
  data: OHLC[],
  leftBars: number = 5,
  rightBars: number = 5,
  zoneThreshold: number = 0.005
): { support: SRLevel[]; resistance: SRLevel[] } {
  if (data.length < leftBars + rightBars + 1) {
    return { support: [], resistance: [] };
  }

  const pivots: { index: number; price: number; type: 'high' | 'low' }[] = [];

  // Find pivot highs and lows
  for (let i = leftBars; i < data.length - rightBars; i++) {
    const current = data[i];
    
    // Check for pivot high
    let isPivotHigh = true;
    for (let j = 1; j <= leftBars; j++) {
      if (data[i - j].high >= current.high) {
        isPivotHigh = false;
        break;
      }
    }
    for (let j = 1; j <= rightBars; j++) {
      if (data[i + j].high > current.high) {
        isPivotHigh = false;
        break;
      }
    }
    
    if (isPivotHigh) {
      pivots.push({ index: i, price: current.high, type: 'high' });
      continue;
    }

    // Check for pivot low
    let isPivotLow = true;
    for (let j = 1; j <= leftBars; j++) {
      if (data[i - j].low <= current.low) {
        isPivotLow = false;
        break;
      }
    }
    for (let j = 1; j <= rightBars; j++) {
      if (data[i + j].low < current.low) {
        isPivotLow = false;
        break;
      }
    }
    
    if (isPivotLow) {
      pivots.push({ index: i, price: current.low, type: 'low' });
    }
  }

  // Cluster nearby levels
  const clusterLevels = (pivotList: typeof pivots): SRLevel[] => {
    if (pivotList.length === 0) return [];

    const clusters: { price: number; touches: number; indices: number[] }[] = [];
    
    for (const pivot of pivotList) {
      let addedToCluster = false;
      
      for (const cluster of clusters) {
        const priceDiff = Math.abs(pivot.price - cluster.price) / cluster.price;
        if (priceDiff <= zoneThreshold) {
          cluster.price = (cluster.price * cluster.touches + pivot.price) / (cluster.touches + 1);
          cluster.touches++;
          cluster.indices.push(pivot.index);
          addedToCluster = true;
          break;
        }
      }
      
      if (!addedToCluster) {
        clusters.push({ price: pivot.price, touches: 1, indices: [pivot.index] });
      }
    }

    // Calculate strength based on touches and recency
    const currentIndex = data.length - 1;
    return clusters.map(cluster => {
      const avgDistance = cluster.indices.reduce((sum, idx) => sum + (currentIndex - idx), 0) / cluster.indices.length;
      const recencyFactor = Math.max(0, 1 - avgDistance / 100); // Higher for recent touches
      const strength = Math.min(100, cluster.touches * 20 + recencyFactor * 30);
      
      const levelType: 'support' | 'resistance' = pivotList[0].type === 'high' ? 'resistance' : 'support';
      return {
        price: cluster.price,
        strength: Math.round(strength),
        touches: cluster.touches,
        type: levelType,
      };
    }).sort((a, b) => b.strength - a.strength);
  };

  const highPivots = pivots.filter(p => p.type === 'high');
  const lowPivots = pivots.filter(p => p.type === 'low');

  return {
    resistance: clusterLevels(highPivots),
    support: clusterLevels(lowPivots),
  };
}

/**
 * Simple pattern detection algorithm (mock implementation)
 * In production, this would use more sophisticated algorithms
 */
export function detectPatterns(data: OHLC[]): Pattern[] {
  if (data.length < 20) return [];
  
  const patterns: Pattern[] = [];
  const recent = data.slice(-50);
  
  // Detect channels using linear regression on highs and lows
  const highs = recent.map(d => d.high);
  const lows = recent.map(d => d.low);
  const times = recent.map((_, i) => i);
  
  const slopeHigh = calculateSlope(times, highs);
  const slopeLow = calculateSlope(times, lows);
  
  // Channel detection
  if (Math.abs(slopeHigh.slope - slopeLow.slope) < 0.001) {
    const isAscending = slopeHigh.slope > 0.001;
    const isDescending = slopeHigh.slope < -0.001;
    
    const pattern: Pattern = {
      id: `channel_${Date.now()}`,
      type: isAscending ? 'channel_up' : isDescending ? 'channel_down' : 'channel_flat',
      name: isAscending ? 'Ascending Channel' : isDescending ? 'Descending Channel' : 'Horizontal Channel',
      confidence: Math.round(70 + Math.random() * 20),
      startTime: recent[0].time,
      endTime: recent[recent.length - 1].time,
      priceLevel: (recent[recent.length - 1].high + recent[recent.length - 1].low) / 2,
      direction: isAscending ? 'bullish' : isDescending ? 'bearish' : 'neutral',
      points: [
        { time: recent[0].time, price: slopeHigh.intercept },
        { time: recent[recent.length - 1].time, price: slopeHigh.predict(recent.length - 1) },
        { time: recent[recent.length - 1].time, price: slopeLow.predict(recent.length - 1) },
        { time: recent[0].time, price: slopeLow.intercept },
      ],
    };
    patterns.push(pattern);
  }
  
  // Triangle detection
  const highSlopeMag = Math.abs(slopeHigh.slope);
  const lowSlopeMag = Math.abs(slopeLow.slope);
  
  if (highSlopeMag < 0.0005 && lowSlopeMag > 0.001) {
    patterns.push({
      id: `asc_tri_${Date.now()}`,
      type: 'ascending_triangle',
      name: 'Ascending Triangle',
      confidence: Math.round(60 + Math.random() * 25),
      startTime: recent[0].time,
      endTime: recent[recent.length - 1].time,
      priceLevel: recent[recent.length - 1].close,
      direction: 'bullish',
      points: [],
    });
  } else if (lowSlopeMag < 0.0005 && highSlopeMag > 0.001) {
    patterns.push({
      id: `desc_tri_${Date.now()}`,
      type: 'descending_triangle',
      name: 'Descending Triangle',
      confidence: Math.round(60 + Math.random() * 25),
      startTime: recent[0].time,
      endTime: recent[recent.length - 1].time,
      priceLevel: recent[recent.length - 1].close,
      direction: 'bearish',
      points: [],
    });
  }
  
  return patterns;
}

function calculateSlope(x: number[], y: number[]) {
  const n = x.length;
  const sumX = x.reduce((a, b) => a + b, 0);
  const sumY = y.reduce((a, b) => a + b, 0);
  const sumXY = x.reduce((total, xi, i) => total + xi * y[i], 0);
  const sumXX = x.reduce((total, xi) => total + xi * xi, 0);
  
  const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;
  
  return {
    slope,
    intercept,
    predict: (xVal: number) => slope * xVal + intercept,
  };
}

// ============================================================================
// LocalStorage Persistence
// ============================================================================

const STORAGE_KEY = 'chart_analysis_objects';

function loadObjects(symbol: string, timeframe: string): AnalysisObject[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];
    
    const allData = JSON.parse(stored);
    const key = `${symbol}_${timeframe}`;
    return allData[key] || [];
  } catch {
    return [];
  }
}

function saveObjects(symbol: string, timeframe: string, objects: AnalysisObject[]) {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    const allData = stored ? JSON.parse(stored) : {};
    const key = `${symbol}_${timeframe}`;
    allData[key] = objects;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(allData));
  } catch (error) {
    console.error('Failed to save analysis objects:', error);
  }
}

// ============================================================================
// Tool Definitions
// ============================================================================

interface ToolConfig {
  id: AnalysisTool;
  name: string;
  icon: React.ReactNode;
  shortcut: string;
  group: 'drawing' | 'analysis' | 'view';
  description: string;
}

const TOOLS: ToolConfig[] = [
  {
    id: AnalysisTool.TRENDLINE,
    name: 'Trendline',
    icon: <TrendingUp className="h-4 w-4" />,
    shortcut: 'T',
    group: 'drawing',
    description: 'Draw trend lines by clicking and dragging',
  },
  {
    id: AnalysisTool.FIBONACCI,
    name: 'Fibonacci',
    icon: <Percent className="h-4 w-4" />,
    shortcut: 'F',
    group: 'drawing',
    description: 'Draw Fibonacci retracement levels',
  },
  {
    id: AnalysisTool.SUPPORT_RESISTANCE,
    name: 'S/R Levels',
    icon: <Target className="h-4 w-4" />,
    shortcut: 'R',
    group: 'analysis',
    description: 'Auto-detect support and resistance levels',
  },
  {
    id: AnalysisTool.PATTERN_DETECTION,
    name: 'Patterns',
    icon: <ScanLine className="h-4 w-4" />,
    shortcut: 'P',
    group: 'analysis',
    description: 'Detect chart patterns (H&S, triangles, channels)',
  },
  {
    id: AnalysisTool.DIVERGENCE,
    name: 'Divergence',
    icon: <ArrowLeftRight className="h-4 w-4" />,
    shortcut: 'D',
    group: 'analysis',
    description: 'Detect price/indicator divergences',
  },
  {
    id: AnalysisTool.ORDER_BLOCKS,
    name: 'Order Blocks',
    icon: <Layers className="h-4 w-4" />,
    shortcut: 'B',
    group: 'analysis',
    description: 'Highlight order blocks and consolidation zones',
  },
  {
    id: AnalysisTool.VOLUME_ANALYSIS,
    name: 'Volume',
    icon: <BarChart3 className="h-4 w-4" />,
    shortcut: 'V',
    group: 'view',
    description: 'Toggle volume profile display',
  },
  {
    id: AnalysisTool.CORRELATION,
    name: 'Correlation',
    icon: <GitCompare className="h-4 w-4" />,
    shortcut: 'C',
    group: 'view',
    description: 'Show correlation analysis panel',
  },
  {
    id: AnalysisTool.MTF_ANALYSIS,
    name: 'MTF',
    icon: <Clock className="h-4 w-4" />,
    shortcut: 'M',
    group: 'view',
    description: 'Multi-timeframe confirmation signals',
  },
];

// ============================================================================
// Main Component
// ============================================================================

export function AnalysisToolbar({
  chart,
  candlestickSeries,
  activeTool,
  onToolChange,
  onSupportResistanceDetected,
  onPatternDetected,
  onDivergenceDetected,
  onOrderBlocksDetected,
  symbol,
  timeframe,
  className,
}: AnalysisToolbarProps) {
  // State
  const [objects, setObjects] = useState<AnalysisObject[]>([]);
  const [undoStack, setUndoStack] = useState<AnalysisObject[][]>([]);
  const [redoStack, setRedoStack] = useState<AnalysisObject[][]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawingStart, setDrawingStart] = useState<{ time: number; price: number } | null>(null);
  const [showVolume, setShowVolume] = useState(false);
  const [showCorrelation, setShowCorrelation] = useState(false);
  const [showMTF, setShowMTF] = useState(false);
  
  // Refs for series management
  const seriesRefs = useRef<Map<string, ISeriesApi<'Line'> | ISeriesApi<'Histogram'>>>(new Map());
  const drawingSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  // Load persisted objects on mount or symbol/timeframe change
  useEffect(() => {
    const loaded = loadObjects(symbol, timeframe);
    setObjects(loaded);
    renderAllObjects(loaded);
  }, [symbol, timeframe]);

  // Persist objects when they change
  useEffect(() => {
    saveObjects(symbol, timeframe, objects);
  }, [objects, symbol, timeframe]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      const key = e.key.toUpperCase();
      
      switch (key) {
        case 'T':
          onToolChange(activeTool === AnalysisTool.TRENDLINE ? null : AnalysisTool.TRENDLINE);
          break;
        case 'F':
          onToolChange(activeTool === AnalysisTool.FIBONACCI ? null : AnalysisTool.FIBONACCI);
          break;
        case 'R':
          handleSupportResistance();
          break;
        case 'P':
          handlePatternDetection();
          break;
        case 'D':
          handleDivergenceDetection();
          break;
        case 'B':
          handleOrderBlocks();
          break;
        case 'V':
          handleVolumeToggle();
          break;
        case 'C':
          handleCorrelationToggle();
          break;
        case 'M':
          handleMTFToggle();
          break;
        case 'ESCAPE':
          onToolChange(null);
          break;
        case 'DELETE':
        case 'BACKSPACE':
          if (e.ctrlKey || e.metaKey) {
            clearAllObjects();
          }
          break;
        case 'Z':
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            if (e.shiftKey) {
              handleRedo();
            } else {
              handleUndo();
            }
          }
          break;
        case 'Y':
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            handleRedo();
          }
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTool, objects, undoStack, redoStack]);

  // Chart click handler for drawing tools
  useEffect(() => {
    if (!chart || !candlestickSeries) return;

    const handleClick = (param: MouseEventParams) => {
      if (!param.time || !param.point) return;
      
      const price = candlestickSeries.coordinateToPrice(param.point.y);
      if (price === null) return;

      const time = param.time as number;

      if (activeTool === AnalysisTool.TRENDLINE) {
        handleTrendlineClick(time, price);
      } else if (activeTool === AnalysisTool.FIBONACCI) {
        handleFibonacciClick(time, price);
      }
    };

    const handleCrosshairMove = (param: MouseEventParams) => {
      if (!isDrawing || !drawingStart || !param.point || !chart) return;
      
      const price = candlestickSeries.coordinateToPrice(param.point.y);
      const time = param.time as number;
      
      if (price !== null && time) {
        updatePreviewLine(drawingStart.time, drawingStart.price, time, price);
      }
    };

    chart.subscribeClick(handleClick);
    chart.subscribeCrosshairMove(handleCrosshairMove);

    return () => {
      chart.unsubscribeClick(handleClick);
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
    };
  }, [chart, candlestickSeries, activeTool, isDrawing, drawingStart]);

  // Drawing handlers
  const handleTrendlineClick = useCallback((time: number, price: number) => {
    if (!isDrawing) {
      setIsDrawing(true);
      setDrawingStart({ time, price });
      createPreviewLine(time, price);
    } else if (drawingStart) {
      setIsDrawing(false);
      removePreviewLine();
      
      const trendline: Trendline = {
        id: `trend_${Date.now()}`,
        startTime: drawingStart.time,
        startPrice: drawingStart.price,
        endTime: time,
        endPrice: price,
        color: '#3B82F6',
        lineWidth: 2,
      };
      
      addObject({
        id: trendline.id,
        type: AnalysisTool.TRENDLINE,
        data: trendline,
        visible: true,
        createdAt: Date.now(),
      });
      
      setDrawingStart(null);
      onToolChange(null);
    }
  }, [isDrawing, drawingStart]);

  const handleFibonacciClick = useCallback((time: number, price: number) => {
    if (!isDrawing) {
      setIsDrawing(true);
      setDrawingStart({ time, price });
      createPreviewLine(time, price);
    } else if (drawingStart) {
      setIsDrawing(false);
      removePreviewLine();
      
      const fibLevels = calculateFibonacciLevels(
        drawingStart.price,
        price,
        drawingStart.time,
        time
      );
      
      const fibonacci: FibonacciLevel = {
        id: `fib_${Date.now()}`,
        startTime: drawingStart.time,
        startPrice: drawingStart.price,
        endTime: time,
        endPrice: price,
        levels: fibLevels,
      };
      
      addObject({
        id: fibonacci.id,
        type: AnalysisTool.FIBONACCI,
        data: fibonacci,
        visible: true,
        createdAt: Date.now(),
      });
      
      setDrawingStart(null);
      onToolChange(null);
    }
  }, [isDrawing, drawingStart]);

  const createPreviewLine = (time: number, price: number) => {
    if (!chart) return;
    
    const series = chart.addLineSeries({
      color: '#3B82F6',
      lineWidth: 2,
      lineStyle: 2, // Dashed
      lastValueVisible: false,
      title: '',
    });
    
    series.setData([{ time: time as Time, value: price }]);
    drawingSeriesRef.current = series;
  };

  const updatePreviewLine = (startTime: number, startPrice: number, endTime: number, endPrice: number) => {
    if (!drawingSeriesRef.current) return;
    
    drawingSeriesRef.current.setData([
      { time: startTime as Time, value: startPrice },
      { time: endTime as Time, value: endPrice },
    ]);
  };

  const removePreviewLine = () => {
    if (drawingSeriesRef.current && chart) {
      chart.removeSeries(drawingSeriesRef.current);
      drawingSeriesRef.current = null;
    }
  };

  const calculateFibonacciLevels = (startPrice: number, endPrice: number, _startTime: number, _endTime: number) => {
    const diff = endPrice - startPrice;
    const ratios = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
    
    return ratios.map(ratio => ({
      ratio,
      price: startPrice + diff * ratio,
    }));
  };

  // Object management
  const addObject = (obj: AnalysisObject) => {
    setUndoStack(prev => [...prev, objects]);
    setRedoStack([]);
    setObjects(prev => [...prev, obj]);
    renderObject(obj);
  };

  const removeObject = (id: string) => {
    setUndoStack(prev => [...prev, objects]);
    setRedoStack([]);
    
    const obj = objects.find(o => o.id === id);
    if (obj) {
      removeObjectFromChart(obj);
    }
    
    setObjects(prev => prev.filter(o => o.id !== id));
  };

  const clearAllObjects = () => {
    if (objects.length === 0) return;
    
    setUndoStack(prev => [...prev, objects]);
    setRedoStack([]);
    
    objects.forEach(removeObjectFromChart);
    setObjects([]);
  };

  const handleUndo = () => {
    if (undoStack.length === 0) return;
    
    const previous = undoStack[undoStack.length - 1];
    setRedoStack(prev => [...prev, objects]);
    setUndoStack(prev => prev.slice(0, -1));
    
    objects.forEach(removeObjectFromChart);
    setObjects(previous);
    renderAllObjects(previous);
  };

  const handleRedo = () => {
    if (redoStack.length === 0) return;
    
    const next = redoStack[redoStack.length - 1];
    setUndoStack(prev => [...prev, objects]);
    setRedoStack(prev => prev.slice(0, -1));
    
    objects.forEach(removeObjectFromChart);
    setObjects(next);
    renderAllObjects(next);
  };

  // Chart rendering
  const renderObject = (obj: AnalysisObject) => {
    if (!chart || !obj.visible) return;

    switch (obj.type) {
      case AnalysisTool.TRENDLINE:
        renderTrendline(obj.data as Trendline, obj.id);
        break;
      case AnalysisTool.FIBONACCI:
        renderFibonacci(obj.data as FibonacciLevel, obj.id);
        break;
      case AnalysisTool.SUPPORT_RESISTANCE:
        renderSRLevel(obj.data as SRLevel, obj.id);
        break;
    }
  };

  const renderAllObjects = (objs: AnalysisObject[]) => {
    // Clear existing series
    seriesRefs.current.forEach(series => {
      if (chart) chart.removeSeries(series);
    });
    seriesRefs.current.clear();

    objs.forEach(renderObject);
  };

  const renderTrendline = (trendline: Trendline, id: string) => {
    if (!chart) return;

    const series = chart.addLineSeries({
      color: trendline.color,
      lineWidth: trendline.lineWidth as 1 | 2 | 3 | 4,
      lastValueVisible: false,
      title: '',
    });

    series.setData([
      { time: trendline.startTime as Time, value: trendline.startPrice },
      { time: trendline.endTime as Time, value: trendline.endPrice },
    ]);

    seriesRefs.current.set(id, series);
  };

  const renderFibonacci = (fib: FibonacciLevel, id: string) => {
    if (!chart) return;

    const colors = ['#22C55E', '#84CC16', '#EAB308', '#F97316', '#EF4444', '#DC2626', '#991B1B'];
    
    fib.levels.forEach((level, index) => {
      const series = chart.addLineSeries({
        color: colors[index % colors.length],
        lineWidth: 1,
        lineStyle: 2,
        lastValueVisible: true,
        title: `${(level.ratio * 100).toFixed(1)}%`,
      });

      series.setData([
        { time: fib.startTime as Time, value: level.price },
        { time: fib.endTime as Time, value: level.price },
      ]);

      seriesRefs.current.set(`${id}_${index}`, series);
    });
  };

  const renderSRLevel = (level: SRLevel, id: string) => {
    if (!chart) return;

    const opacity = Math.min(1, level.strength / 100);
    const color = level.type === 'support' 
      ? `rgba(34, 197, 94, ${opacity})` 
      : `rgba(239, 68, 68, ${opacity})`;

    const series = chart.addLineSeries({
      color,
      lineWidth: Math.max(1, Math.min(4, Math.round(level.strength / 25))) as 1 | 2 | 3 | 4,
      lineStyle: 2,
      lastValueVisible: true,
      title: `${level.type === 'support' ? 'S' : 'R'} ${level.price.toFixed(2)}`,
    });

    // Extend line across visible range
    const data = chart.timeScale().getVisibleRange();
    if (data) {
      series.setData([
        { time: data.from as Time, value: level.price },
        { time: data.to as Time, value: level.price },
      ]);
    }

    seriesRefs.current.set(id, series);
  };

  const removeObjectFromChart = (obj: AnalysisObject) => {
    if (obj.type === AnalysisTool.FIBONACCI) {
      const fib = obj.data as FibonacciLevel;
      fib.levels.forEach((_, index) => {
        const seriesId = `${obj.id}_${index}`;
        const series = seriesRefs.current.get(seriesId);
        if (series && chart) {
          chart.removeSeries(series);
          seriesRefs.current.delete(seriesId);
        }
      });
    } else {
      const series = seriesRefs.current.get(obj.id);
      if (series && chart) {
        chart.removeSeries(series);
        seriesRefs.current.delete(obj.id);
      }
    }
  };

  // Analysis handlers
  const handleSupportResistance = useCallback(() => {
    if (!candlestickSeries || !chart) return;

    // Get current chart data
    const data = candlestickSeries.data();
    if (data.length < 20) return;

    const ohlcData: OHLC[] = data.map(d => ({
      time: d.time as number,
      open: (d as any).open || 0,
      high: (d as any).high || 0,
      low: (d as any).low || 0,
      close: (d as any).close || 0,
      volume: 0,
    }));

    const { support, resistance } = detectSupportResistance(ohlcData);

    // Add to objects
    support.forEach((level, index) => {
      if (index < 3) { // Limit to top 3
        addObject({
          id: `sr_support_${Date.now()}_${index}`,
          type: AnalysisTool.SUPPORT_RESISTANCE,
          data: level,
          visible: true,
          createdAt: Date.now(),
        });
      }
    });

    resistance.forEach((level, index) => {
      if (index < 3) { // Limit to top 3
        addObject({
          id: `sr_resistance_${Date.now()}_${index}`,
          type: AnalysisTool.SUPPORT_RESISTANCE,
          data: level,
          visible: true,
          createdAt: Date.now(),
        });
      }
    });

    onSupportResistanceDetected?.({ support, resistance });
  }, [candlestickSeries, chart]);

  const handlePatternDetection = useCallback(() => {
    if (!candlestickSeries) return;

    const data = candlestickSeries.data();
    const ohlcData: OHLC[] = data.map(d => ({
      time: d.time as number,
      open: (d as any).open || 0,
      high: (d as any).high || 0,
      low: (d as any).low || 0,
      close: (d as any).close || 0,
      volume: 0,
    }));

    const patterns = detectPatterns(ohlcData);
    onPatternDetected?.(patterns);
  }, [candlestickSeries]);

  const handleDivergenceDetection = useCallback(() => {
    // Mock implementation - would use actual indicator data in production
    const mockDivergences: Divergence[] = [
      {
        id: `div_${Date.now()}`,
        type: Math.random() > 0.5 ? 'bullish' : 'bearish',
        indicator: 'RSI',
        startTime: Date.now() / 1000 - 86400,
        endTime: Date.now() / 1000,
        priceStart: 100,
        priceEnd: 105,
        indicatorStart: 30,
        indicatorEnd: 40,
        strength: ['weak', 'medium', 'strong'][Math.floor(Math.random() * 3)] as any,
      },
    ];
    onDivergenceDetected?.(mockDivergences);
  }, []);

  const handleOrderBlocks = useCallback(() => {
    if (!candlestickSeries) return;

    const data = candlestickSeries.data();
    const ohlcData: OHLC[] = data.slice(-20).map(d => ({
      time: d.time as number,
      open: (d as any).open || 0,
      high: (d as any).high || 0,
      low: (d as any).low || 0,
      close: (d as any).close || 0,
      volume: 0,
    }));

    // Simple order block detection
    const blocks: OrderBlock[] = [];
    for (let i = 2; i < ohlcData.length; i++) {
      const current = ohlcData[i];
      const prev = ohlcData[i - 1];
      // Note: prev2 (ohlcData[i - 2]) available for more complex detection patterns

      // Bullish order block: bearish candle followed by strong bullish move
      if (prev.close < prev.open && current.close > current.open && current.close > prev.open) {
        blocks.push({
          id: `ob_bull_${Date.now()}_${i}`,
          type: 'bullish',
          time: prev.time,
          high: prev.high,
          low: prev.low,
          volume: 0,
          mitigationLevel: prev.low,
        });
      }
      // Bearish order block
      else if (prev.close > prev.open && current.close < current.open && current.close < prev.open) {
        blocks.push({
          id: `ob_bear_${Date.now()}_${i}`,
          type: 'bearish',
          time: prev.time,
          high: prev.high,
          low: prev.low,
          volume: 0,
          mitigationLevel: prev.high,
        });
      }
    }

    onOrderBlocksDetected?.(blocks);
  }, [candlestickSeries]);

  const handleVolumeToggle = useCallback(() => {
    setShowVolume(prev => !prev);
  }, []);

  const handleCorrelationToggle = useCallback(() => {
    setShowCorrelation(prev => !prev);
  }, []);

  const handleMTFToggle = useCallback(() => {
    setShowMTF(prev => !prev);
  }, []);

  // Tool click handlers
  const handleToolClick = (toolId: AnalysisTool) => {
    switch (toolId) {
      case AnalysisTool.SUPPORT_RESISTANCE:
        handleSupportResistance();
        break;
      case AnalysisTool.PATTERN_DETECTION:
        handlePatternDetection();
        break;
      case AnalysisTool.DIVERGENCE:
        handleDivergenceDetection();
        break;
      case AnalysisTool.ORDER_BLOCKS:
        handleOrderBlocks();
        break;
      case AnalysisTool.VOLUME_ANALYSIS:
        handleVolumeToggle();
        break;
      case AnalysisTool.CORRELATION:
        handleCorrelationToggle();
        break;
      case AnalysisTool.MTF_ANALYSIS:
        handleMTFToggle();
        break;
      default:
        onToolChange(activeTool === toolId ? null : toolId);
    }
  };

  // Group tools
  const drawingTools = TOOLS.filter(t => t.group === 'drawing');
  const analysisTools = TOOLS.filter(t => t.group === 'analysis');
  const viewTools = TOOLS.filter(t => t.group === 'view');

  const renderToolButton = (tool: ToolConfig) => {
    const isActive = activeTool === tool.id;
    const isToggleActive = 
      (tool.id === AnalysisTool.VOLUME_ANALYSIS && showVolume) ||
      (tool.id === AnalysisTool.CORRELATION && showCorrelation) ||
      (tool.id === AnalysisTool.MTF_ANALYSIS && showMTF);

    return (
      <Tooltip key={tool.id}>
        <TooltipTrigger asChild>
          <ToggleGroupItem
            value={tool.id}
            aria-label={tool.name}
            className={cn(
              "h-8 w-8 p-0 data-[state=on]:bg-accent data-[state=on]:text-accent-foreground",
              (isActive || isToggleActive) && "bg-primary/10 text-primary border-primary/20"
            )}
            onClick={() => handleToolClick(tool.id)}
          >
            {tool.icon}
          </ToggleGroupItem>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="flex flex-col gap-1">
          <span className="font-medium">{tool.name}</span>
          <span className="text-xs text-muted-foreground">{tool.description}</span>
          <kbd className="ml-auto text-xs bg-muted px-1.5 py-0.5 rounded">{tool.shortcut}</kbd>
        </TooltipContent>
      </Tooltip>
    );
  };

  return (
    <TooltipProvider>
      <div className={cn(
        "flex items-center gap-1 p-1.5 bg-card border border-border rounded-md",
        className
      )}>
        {/* Cursor / Select */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                "h-8 w-8",
                activeTool === null && "bg-accent text-accent-foreground"
              )}
              onClick={() => onToolChange(null)}
            >
              <MousePointer2 className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <span className="font-medium">Select</span>
            <kbd className="ml-2 text-xs bg-muted px-1.5 py-0.5 rounded">Esc</kbd>
          </TooltipContent>
        </Tooltip>

        <Separator orientation="vertical" className="h-6 mx-1" />

        {/* Drawing Tools */}
        <ToggleGroup type="single" value={activeTool || ''}>
          {drawingTools.map(renderToolButton)}
        </ToggleGroup>

        <Separator orientation="vertical" className="h-6 mx-1" />

        {/* Analysis Tools */}
        <ToggleGroup type="multiple">
          {analysisTools.map(renderToolButton)}
        </ToggleGroup>

        <Separator orientation="vertical" className="h-6 mx-1" />

        {/* View Tools */}
        <ToggleGroup type="multiple">
          {viewTools.map(renderToolButton)}
        </ToggleGroup>

        <Separator orientation="vertical" className="h-6 mx-1" />

        {/* Undo/Redo */}
        <div className="flex items-center gap-0.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={handleUndo}
                disabled={undoStack.length === 0}
              >
                <Undo2 className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <span className="font-medium">Undo</span>
              <kbd className="ml-2 text-xs bg-muted px-1.5 py-0.5 rounded">Ctrl+Z</kbd>
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={handleRedo}
                disabled={redoStack.length === 0}
              >
                <Redo2 className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <span className="font-medium">Redo</span>
              <kbd className="ml-2 text-xs bg-muted px-1.5 py-0.5 rounded">Ctrl+Y</kbd>
            </TooltipContent>
          </Tooltip>
        </div>

        <Separator orientation="vertical" className="h-6 mx-1" />

        {/* Clear / Manage */}
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <Trash2 className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <span className="font-medium">Clear Objects</span>
            </TooltipContent>
          </Tooltip>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => removeObject(objects[objects.length - 1]?.id)} disabled={objects.length === 0}>
              Delete Last Object
            </DropdownMenuItem>
            <DropdownMenuItem onClick={clearAllObjects} disabled={objects.length === 0}>
              Clear All Objects
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled>
              Objects: {objects.length}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Object Count Badge */}
        {objects.length > 0 && (
          <Badge variant="secondary" className="ml-auto text-xs">
            {objects.length} object{objects.length !== 1 ? 's' : ''}
          </Badge>
        )}

        {/* Active Tool Indicator */}
        {(isDrawing || activeTool) && (
          <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            {isDrawing && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                Click to complete
              </span>
            )}
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}

// ============================================================================
// Export utilities
// ============================================================================

// All exports are inline above

export default AnalysisToolbar;
