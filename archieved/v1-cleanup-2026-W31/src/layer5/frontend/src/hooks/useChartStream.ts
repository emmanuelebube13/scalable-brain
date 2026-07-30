/**
 * useChartStream - WebSocket hook for real-time OANDA market data streaming.
 *
 * Features:
 * - Real-time tick data streaming from OANDA v20 API
 * - Automatic candle building from ticks
 * - Automatic reconnection with exponential backoff
 * - Connection state management
 * - Error handling and recovery
 * - Configurable symbols and timeframes
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import type { OHLCData } from '@/types';

// =============================================================================
// Types
// =============================================================================

export type Granularity = '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d';

export interface OandaTick {
  instrument: string;
  time: string;
  bid: number;
  ask: number;
  mid: number;
}

export interface StreamState {
  connectionState: 'connecting' | 'connected' | 'disconnected' | 'error';
  lastTick: OandaTick | null;
  currentPrice: number;
  error: Error | null;
  reconnectAttempts: number;
}

export interface UseChartStreamOptions {
  symbol: string;
  timeframe?: Granularity;
  enabled?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export interface UseChartStreamReturn extends StreamState {
  connect: () => void;
  disconnect: () => void;
  reset: () => void;
  isConnected: boolean;
  isConnecting: boolean;
}

// =============================================================================
// Utility Functions
// =============================================================================

function getCandleStartTime(timestamp: Date, timeframe: Granularity): Date {
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

// =============================================================================
// Hook
// =============================================================================

export function useChartStream(options: UseChartStreamOptions): UseChartStreamReturn {
  const {
    symbol,
    timeframe = '1h',
    enabled = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
  } = options;

  // State
  const [connectionState, setConnectionState] = useState<StreamState['connectionState']>('disconnected');
  const [lastTick, setLastTick] = useState<OandaTick | null>(null);
  const [currentPrice, setCurrentPrice] = useState<number>(0);
  const [error, setError] = useState<Error | null>(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  // Refs for managing WebSocket
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isManualDisconnectRef = useRef(false);

  // Derived state
  const isConnected = connectionState === 'connected';
  const isConnecting = connectionState === 'connecting';

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

    // Build WebSocket URL - connect to backend streaming endpoint
    const baseUrl = import.meta.env.VITE_WS_URL || 
      (import.meta.env.VITE_API_BASE_URL || '').replace(/^http/, 'ws') ||
      'ws://localhost:8000';
    
    const wsUrl = `${baseUrl}/api/v1/streaming/ws/oanda`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log(`[useChartStream] Connected to stream server`);
        setConnectionState('connected');
        setReconnectAttempts(0);
        
        // Subscribe to the symbol
        ws.send(JSON.stringify({
          type: 'subscribe',
          symbol: symbol,
          granularity: mapTimeframeToOanda(timeframe)
        }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          switch (data.type) {
            case 'tick':
              const tick = data.data as OandaTick;
              setLastTick(tick);
              setCurrentPrice(tick.mid || (tick.bid + tick.ask) / 2);
              break;
            case 'candle':
              // Handle candle updates if needed
              if (data.data?.close) {
                setCurrentPrice(data.data.close);
              }
              break;
            case 'connected':
              console.log('[useChartStream] Server confirmed connection:', data.message);
              break;
            case 'subscribed':
              console.log('[useChartStream] Subscribed to:', data.symbol);
              break;
            case 'heartbeat':
              // Keep connection alive
              break;
            case 'error':
              console.error('[useChartStream] Server error:', data.message);
              setError(new Error(data.message || 'Server error'));
              break;
          }
        } catch (e) {
          console.error('[useChartStream] Failed to parse message:', e);
        }
      };

      ws.onerror = (event) => {
        console.error('[useChartStream] WebSocket error:', event);
        setError(new Error('WebSocket connection error'));
        setConnectionState('error');
      };

      ws.onclose = (event) => {
        console.log(`[useChartStream] Disconnected: ${event.code} ${event.reason}`);

        // Attempt reconnection if not manually disconnected
        if (!isManualDisconnectRef.current && reconnectAttempts < maxReconnectAttempts) {
          const backoffDelay = Math.min(
            reconnectInterval * Math.pow(2, reconnectAttempts),
            30000 // Max 30 seconds
          );
          
          console.log(`[useChartStream] Reconnecting in ${backoffDelay}ms (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})`);
          
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
      console.error('[useChartStream] Failed to create WebSocket:', e);
      setError(e instanceof Error ? e : new Error('Failed to create WebSocket'));
      setConnectionState('error');
    }
  }, [symbol, timeframe, enabled, reconnectInterval, maxReconnectAttempts, reconnectAttempts]);

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
    setLastTick(null);
    setCurrentPrice(0);
    setError(null);
    setReconnectAttempts(0);
    
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
    currentPrice,
    error,
    reconnectAttempts,
    connect,
    disconnect,
    reset,
    isConnected,
    isConnecting,
  };
}

/**
 * Map our timeframe format to OANDA granularity
 */
function mapTimeframeToOanda(timeframe: Granularity): string {
  const mapping: Record<Granularity, string> = {
    '1m': 'M1',
    '5m': 'M5',
    '15m': 'M15',
    '30m': 'M30',
    '1h': 'H1',
    '4h': 'H4',
    '1d': 'D',
  };
  return mapping[timeframe] || 'H1';
}

export default useChartStream;
