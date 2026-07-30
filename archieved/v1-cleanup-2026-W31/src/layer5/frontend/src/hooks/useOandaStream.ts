/**
 * useOandaStream - WebSocket hook for real-time OANDA market data streaming.
 *
 * Features:
 * - Real-time tick data streaming
 * - Automatic candle building from ticks
 * - Automatic reconnection with exponential backoff
 * - Connection state management
 * - Error handling and recovery
 * - Configurable symbols and timeframes
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import type { OandaTick, OandaCandle, OHLCData } from '@/types';

// =============================================================================
// Types
// =============================================================================

export interface UseOandaStreamOptions {
  symbol: string;
  timeframe?: string;
  enabled?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  candleBuildInterval?: number; // ms between candle updates
}

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface StreamState {
  connectionState: ConnectionState;
  lastTick: OandaTick | null;
  currentCandle: OandaCandle | null;
  candles: OHLCData[];
  error: Error | null;
  reconnectAttempts: number;
}

export interface UseOandaStreamReturn extends StreamState {
  connect: () => void;
  disconnect: () => void;
  reset: () => void;
  isConnected: boolean;
  isConnecting: boolean;
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Format timestamp to ISO string
 */
function formatTimestamp(date: Date): string {
  return date.toISOString();
}

/**
 * Get candle start time based on timeframe
 */
function getCandleStartTime(timestamp: Date, timeframe: string): Date {
  const date = new Date(timestamp);
  
  switch (timeframe) {
    case '1m':
      date.setSeconds(0, 0);
      break;
    case '5m':
      date.setMinutes(Math.floor(date.getMinutes() / 5) * 5, 0, 0);
      break;
    case '15m':
      date.setMinutes(Math.floor(date.getMinutes() / 15) * 15, 0, 0);
      break;
    case '30m':
      date.setMinutes(Math.floor(date.getMinutes() / 30) * 30, 0, 0);
      break;
    case '1h':
      date.setMinutes(0, 0, 0);
      break;
    case '4h':
      date.setHours(Math.floor(date.getHours() / 4) * 4, 0, 0, 0);
      break;
    case '1d':
      date.setHours(0, 0, 0, 0);
      break;
    default:
      date.setSeconds(0, 0);
  }
  
  return date;
}

/**
 * Convert OandaCandle to OHLCData
 */
function candleToOHLC(candle: OandaCandle): OHLCData {
  return {
    timestamp: candle.time,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume,
  };
}

// =============================================================================
// Hook
// =============================================================================

export function useOandaStream(options: UseOandaStreamOptions): UseOandaStreamReturn {
  const {
    symbol,
    timeframe = '1m',
    enabled = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
    candleBuildInterval = 1000,
  } = options;

  // State
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [lastTick, setLastTick] = useState<OandaTick | null>(null);
  const [currentCandle, setCurrentCandle] = useState<OandaCandle | null>(null);
  const [candles, setCandles] = useState<OHLCData[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  // Refs for managing WebSocket and intervals
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const candleIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pendingTicksRef = useRef<OandaTick[]>([]);
  const isManualDisconnectRef = useRef(false);

  // Derived state
  const isConnected = connectionState === 'connected';
  const isConnecting = connectionState === 'connecting';

  // =============================================================================
  // Candle Building Logic
  // =============================================================================

  /**
   * Process pending ticks and build/update candles
   */
  const processTicks = useCallback(() => {
    if (pendingTicksRef.current.length === 0) return;

    const ticks = [...pendingTicksRef.current];
    pendingTicksRef.current = [];

    // Get or create current candle
    setCurrentCandle(prevCandle => {
      const now = new Date();
      const candleStart = getCandleStartTime(now, timeframe);
      const candleStartStr = formatTimestamp(candleStart);

      // If we have an existing candle and it's still the same time period, update it
      if (prevCandle && prevCandle.time === candleStartStr && !prevCandle.complete) {
        let high = prevCandle.high;
        let low = prevCandle.low;
        let close = prevCandle.close;
        let volume = prevCandle.volume;

        // Process all pending ticks
        for (const tick of ticks) {
          const mid = tick.mid || (tick.bid + tick.ask) / 2;
          high = Math.max(high, mid);
          low = Math.min(low, mid);
          close = mid;
          volume += 1; // Simplified volume counting
        }

        const updatedCandle: OandaCandle = {
          ...prevCandle,
          high,
          low,
          close,
          volume,
        };

        // Update candles array
        setCandles(prevCandles => {
          const newCandles = [...prevCandles];
          const lastIndex = newCandles.length - 1;
          if (lastIndex >= 0 && newCandles[lastIndex].timestamp === candleStartStr) {
            newCandles[lastIndex] = candleToOHLC(updatedCandle);
          }
          return newCandles;
        });

        return updatedCandle;
      }

      // Start a new candle
      if (ticks.length > 0) {
        const firstTick = ticks[0];
        const mid = firstTick.mid || (firstTick.bid + firstTick.ask) / 2;

        // Finalize previous candle if exists
        if (prevCandle && !prevCandle.complete) {
          setCandles(prevCandles => {
            const newCandles = [...prevCandles];
            return newCandles;
          });
        }

        const newCandle: OandaCandle = {
          time: candleStartStr,
          open: mid,
          high: mid,
          low: mid,
          close: mid,
          volume: ticks.length,
          complete: false,
        };

        // Add new candle to array
        setCandles(prevCandles => {
          const newCandles = [...prevCandles, candleToOHLC(newCandle)];
          // Keep last 500 candles
          if (newCandles.length > 500) {
            return newCandles.slice(-500);
          }
          return newCandles;
        });

        return newCandle;
      }

      return prevCandle;
    });

    // Update last tick
    if (ticks.length > 0) {
      setLastTick(ticks[ticks.length - 1]);
    }
  }, [timeframe]);

  // =============================================================================
  // WebSocket Management
  // =============================================================================

  /**
   * Connect to WebSocket
   */
  const connect = useCallback(() => {
    if (!symbol || !enabled) return;

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setConnectionState('connecting');
    setError(null);
    isManualDisconnectRef.current = false;

    // Build WebSocket URL
    const baseUrl = import.meta.env.VITE_WS_URL || 
      (import.meta.env.VITE_API_BASE_URL || '').replace(/^http/, 'ws') ||
      'ws://localhost:8000';
    
    const wsUrl = `${baseUrl}/ws/oanda/stream?instrument=${encodeURIComponent(symbol)}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log(`[useOandaStream] Connected to ${symbol}`);
        setConnectionState('connected');
        setReconnectAttempts(0);
        
        // Start candle building interval
        if (candleIntervalRef.current) {
          clearInterval(candleIntervalRef.current);
        }
        candleIntervalRef.current = setInterval(processTicks, candleBuildInterval);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Handle different message types
          switch (data.type) {
            case 'tick':
              pendingTicksRef.current.push(data.data as OandaTick);
              break;
            case 'candle':
              // Direct candle update from server
              const candle = data.data as OandaCandle;
              setCurrentCandle(candle);
              setCandles(prev => {
                const existingIndex = prev.findIndex(c => c.timestamp === candle.time);
                const ohlc = candleToOHLC(candle);
                if (existingIndex >= 0) {
                  const newCandles = [...prev];
                  newCandles[existingIndex] = ohlc;
                  return newCandles;
                }
                const newCandles = [...prev, ohlc];
                return newCandles.length > 500 ? newCandles.slice(-500) : newCandles;
              });
              break;
            case 'heartbeat':
              // Keep connection alive
              break;
            case 'error':
              console.error('[useOandaStream] Server error:', data.message);
              setError(new Error(data.message || 'Server error'));
              break;
          }
        } catch (e) {
          console.error('[useOandaStream] Failed to parse message:', e);
        }
      };

      ws.onerror = (event) => {
        console.error('[useOandaStream] WebSocket error:', event);
        setError(new Error('WebSocket connection error'));
        setConnectionState('error');
      };

      ws.onclose = (event) => {
        console.log(`[useOandaStream] Disconnected: ${event.code} ${event.reason}`);
        
        // Stop candle building
        if (candleIntervalRef.current) {
          clearInterval(candleIntervalRef.current);
          candleIntervalRef.current = null;
        }

        // Attempt reconnection if not manually disconnected
        if (!isManualDisconnectRef.current && reconnectAttempts < maxReconnectAttempts) {
          const backoffDelay = Math.min(
            reconnectInterval * Math.pow(2, reconnectAttempts),
            30000 // Max 30 seconds
          );
          
          console.log(`[useOandaStream] Reconnecting in ${backoffDelay}ms (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})`);
          
          setReconnectAttempts(prev => prev + 1);
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, backoffDelay);
        } else if (reconnectAttempts >= maxReconnectAttempts) {
          setConnectionState('error');
          setError(new Error(`Max reconnection attempts (${maxReconnectAttempts}) reached`));
        } else {
          setConnectionState('disconnected');
        }
      };
    } catch (e) {
      console.error('[useOandaStream] Failed to create WebSocket:', e);
      setError(e instanceof Error ? e : new Error('Failed to create WebSocket'));
      setConnectionState('error');
    }
  }, [symbol, enabled, reconnectInterval, maxReconnectAttempts, reconnectAttempts, candleBuildInterval, processTicks]);

  /**
   * Disconnect from WebSocket
   */
  const disconnect = useCallback(() => {
    isManualDisconnectRef.current = true;

    // Clear pending reconnection
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Stop candle building
    if (candleIntervalRef.current) {
      clearInterval(candleIntervalRef.current);
      candleIntervalRef.current = null;
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setConnectionState('disconnected');
  }, []);

  /**
   * Reset state and reconnect
   */
  const reset = useCallback(() => {
    disconnect();
    setCandles([]);
    setCurrentCandle(null);
    setLastTick(null);
    setError(null);
    setReconnectAttempts(0);
    pendingTicksRef.current = [];
    
    // Reconnect after a short delay
    setTimeout(() => {
      connect();
    }, 100);
  }, [disconnect, connect]);

  // =============================================================================
  // Effects
  // =============================================================================

  // Auto-connect when enabled
  useEffect(() => {
    if (enabled && symbol) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [enabled, symbol, connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    connectionState,
    lastTick,
    currentCandle,
    candles,
    error,
    reconnectAttempts,
    connect,
    disconnect,
    reset,
    isConnected,
    isConnecting,
  };
}

export default useOandaStream;
