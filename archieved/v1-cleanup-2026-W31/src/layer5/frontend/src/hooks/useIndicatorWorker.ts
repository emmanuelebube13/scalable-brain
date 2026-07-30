/**
 * React hook for using the indicator Web Worker
 * Provides a simple interface for calculating indicators off the main thread
 */

import { useCallback, useEffect, useRef, useState, useMemo } from 'react';
import type { OHLCData, IndicatorResult } from '@/types';
import type { CalculationRequest } from '@/utils/indicatorCalculations';
import { WorkerPool, getGlobalWorkerPool, type WorkerPoolOptions } from '@/workers/WorkerPool';

// ============================================================================
// Types
// ============================================================================

export type CalculationStatus = 'idle' | 'loading' | 'success' | 'error';

export interface UseIndicatorWorkerOptions {
  /** Use worker pool for parallel calculations */
  usePool?: boolean;
  /** Worker pool configuration (only used if usePool is true) */
  poolOptions?: WorkerPoolOptions;
  /** Timeout for calculations in milliseconds */
  timeout?: number;
  /** Enable debug logging */
  debug?: boolean;
}

export interface UseIndicatorWorkerReturn {
  /** Current calculation status */
  status: CalculationStatus;
  /** Error message if calculation failed */
  error: string | null;
  /** Calculate a single indicator */
  calculate: (
    indicator: string,
    data: OHLCData[],
    params?: Record<string, number | string>
  ) => Promise<IndicatorResult>;
  /** Calculate multiple indicators in batch */
  calculateBatch: (
    calculations: CalculationRequest[]
  ) => Promise<IndicatorResult[]>;
  /** Cancel all pending calculations */
  cancelAll: () => void;
  /** Check if worker is ready */
  isReady: boolean;
}

interface PendingCalculation {
  id: string;
  resolve: (value: IndicatorResult | IndicatorResult[]) => void;
  reject: (reason: Error) => void;
  timestamp: number;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useIndicatorWorker(
  options: UseIndicatorWorkerOptions = {}
): UseIndicatorWorkerReturn {
  const {
    usePool = true,
    poolOptions,
    timeout = 30000,
    debug = false,
  } = options;

  const [status, setStatus] = useState<CalculationStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);

  const workerRef = useRef<Worker | null>(null);
  const workerPoolRef = useRef<WorkerPool | null>(null);
  const pendingRef = useRef<Map<string, PendingCalculation>>(new Map());
  const taskCounterRef = useRef(0);

  // Initialize worker or pool
  useEffect(() => {
    if (usePool) {
      // Use worker pool
      workerPoolRef.current = getGlobalWorkerPool(poolOptions);
      setIsReady(true);

      if (debug) {
        console.log('[useIndicatorWorker] Using worker pool');
      }
    } else {
      // Use single worker
      const initWorker = async () => {
        try {
          workerRef.current = new Worker(
            new URL('@/workers/indicatorWorker.ts', import.meta.url),
            { type: 'module' }
          );

          workerRef.current.onmessage = handleWorkerMessage;
          workerRef.current.onerror = handleWorkerError;

          // Wait for worker to be ready (ping)
          const pingId = `ping-${Date.now()}`;
          const pingTimeout = setTimeout(() => {
            setError('Worker initialization timeout');
            setStatus('error');
          }, 5000);

          const checkReady = (e: MessageEvent) => {
            if (e.data.id === pingId && e.data.type === 'pong') {
              clearTimeout(pingTimeout);
              workerRef.current?.removeEventListener('message', checkReady);
              setIsReady(true);
              
              if (debug) {
                console.log('[useIndicatorWorker] Worker ready');
              }
            }
          };

          workerRef.current.addEventListener('message', checkReady);
          workerRef.current.postMessage({ id: pingId, type: 'ping' });
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Failed to initialize worker');
          setStatus('error');
        }
      };

      initWorker();
    }

    // Cleanup
    return () => {
      if (!usePool && workerRef.current) {
        workerRef.current.terminate();
        workerRef.current = null;
      }
      // Cancel all pending calculations
      pendingRef.current.forEach((pending) => {
        pending.reject(new Error('Component unmounted'));
      });
      pendingRef.current.clear();
    };
  }, [usePool, poolOptions, debug]);

  // Handle worker messages (only for single worker mode)
  const handleWorkerMessage = useCallback((event: MessageEvent) => {
    const { id, type, result, results, error: workerError } = event.data;
    const pending = pendingRef.current.get(id);

    if (!pending) {
      if (debug) {
        console.warn('[useIndicatorWorker] Received message for unknown task:', id);
      }
      return;
    }

    pendingRef.current.delete(id);

    switch (type) {
      case 'result':
        setStatus('success');
        setError(null);
        pending.resolve(result);
        break;

      case 'batchResult':
        setStatus('success');
        setError(null);
        pending.resolve(results);
        break;

      case 'error':
        setStatus('error');
        setError(workerError || 'Calculation failed');
        pending.reject(new Error(workerError || 'Calculation failed'));
        break;

      case 'cancelled':
        pending.reject(new Error('Calculation cancelled'));
        break;
    }

    if (pendingRef.current.size === 0) {
      setStatus('idle');
    }
  }, [debug]);

  const handleWorkerError = useCallback((error: ErrorEvent) => {
    console.error('[useIndicatorWorker] Worker error:', error);
    setError(error.message || 'Worker error');
    setStatus('error');

    // Reject all pending calculations
    pendingRef.current.forEach((pending) => {
      pending.reject(new Error(error.message || 'Worker error'));
    });
    pendingRef.current.clear();
  }, []);

  // Calculate single indicator
  const calculate = useCallback(async (
    indicator: string,
    data: OHLCData[],
    params: Record<string, number | string> = {}
  ): Promise<IndicatorResult> => {
    if (!isReady) {
      throw new Error('Worker not ready');
    }

    setStatus('loading');
    setError(null);

    try {
      if (usePool && workerPoolRef.current) {
        // Use worker pool
        const result = await workerPoolRef.current.calculate(indicator, data, params);
        setStatus('success');
        return result;
      } else if (workerRef.current) {
        // Use single worker
        return new Promise((resolve, reject) => {
          const id = `calc-${++taskCounterRef.current}`;
          
          // Set timeout
          const timeoutId = setTimeout(() => {
            pendingRef.current.delete(id);
            setStatus('error');
            setError('Calculation timeout');
            reject(new Error('Calculation timeout'));
          }, timeout);

          // Store pending calculation
          pendingRef.current.set(id, {
            id,
            resolve: (value) => {
              clearTimeout(timeoutId);
              resolve(value as IndicatorResult);
            },
            reject: (reason) => {
              clearTimeout(timeoutId);
              reject(reason);
            },
            timestamp: Date.now(),
          });

          // Send message to worker
          workerRef.current!.postMessage({
            id,
            type: 'calculate',
            indicator,
            data,
            params,
          });
        });
      } else {
        throw new Error('Worker not available');
      }
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Calculation failed');
      throw err;
    }
  }, [isReady, usePool, timeout]);

  // Calculate batch of indicators
  const calculateBatch = useCallback(async (
    calculations: CalculationRequest[]
  ): Promise<IndicatorResult[]> => {
    if (!isReady) {
      throw new Error('Worker not ready');
    }

    if (!calculations || calculations.length === 0) {
      return [];
    }

    setStatus('loading');
    setError(null);

    try {
      if (usePool && workerPoolRef.current) {
        // Use worker pool
        const results = await workerPoolRef.current.calculateBatch(calculations);
        setStatus('success');
        return results;
      } else if (workerRef.current) {
        // Use single worker
        return new Promise((resolve, reject) => {
          const id = `batch-${++taskCounterRef.current}`;
          
          // Set timeout
          const timeoutId = setTimeout(() => {
            pendingRef.current.delete(id);
            setStatus('error');
            setError('Batch calculation timeout');
            reject(new Error('Batch calculation timeout'));
          }, timeout * calculations.length); // Scale timeout with batch size

          // Store pending calculation
          pendingRef.current.set(id, {
            id,
            resolve: (value) => {
              clearTimeout(timeoutId);
              resolve(value as IndicatorResult[]);
            },
            reject: (reason) => {
              clearTimeout(timeoutId);
              reject(reason);
            },
            timestamp: Date.now(),
          });

          // Send message to worker
          workerRef.current!.postMessage({
            id,
            type: 'calculateBatch',
            calculations,
          });
        });
      } else {
        throw new Error('Worker not available');
      }
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Batch calculation failed');
      throw err;
    }
  }, [isReady, usePool, timeout]);

  // Cancel all pending calculations
  const cancelAll = useCallback(() => {
    if (usePool && workerPoolRef.current) {
      workerPoolRef.current.cancelAll();
    } else if (workerRef.current) {
      workerRef.current.postMessage({
        id: `cancel-${Date.now()}`,
        type: 'cancel',
      });
    }

    // Reject all pending promises
    pendingRef.current.forEach((pending) => {
      pending.reject(new Error('Calculations cancelled'));
    });
    pendingRef.current.clear();

    setStatus('idle');
  }, [usePool]);

  return {
    status,
    error,
    calculate,
    calculateBatch,
    cancelAll,
    isReady,
  };
}

// ============================================================================
// Specialized Hooks
// ============================================================================

/**
 * Hook for calculating a single indicator with automatic updates when inputs change
 */
export function useIndicator(
  indicator: string,
  data: OHLCData[],
  params: Record<string, number | string> = {},
  options: UseIndicatorWorkerOptions = {}
): {
  result: IndicatorResult | null;
  status: CalculationStatus;
  error: string | null;
  recalculate: () => void;
} {
  const { calculate, status, error, isReady } = useIndicatorWorker(options);
  const [result, setResult] = useState<IndicatorResult | null>(null);
  const isMountedRef = useRef(true);

  const recalculate = useCallback(async () => {
    if (!isReady || !data || data.length === 0) return;

    try {
      const newResult = await calculate(indicator, data, params);
      if (isMountedRef.current) {
        setResult(newResult);
      }
    } catch (err) {
      // Error is already handled in the hook
    }
  }, [calculate, indicator, data, params, isReady]);

  useEffect(() => {
    isMountedRef.current = true;
    recalculate();
    return () => {
      isMountedRef.current = false;
    };
  }, [recalculate]);

  return {
    result,
    status,
    error,
    recalculate,
  };
}

/**
 * Hook for calculating multiple indicators
 */
export function useIndicators(
  calculations: Array<{
    indicator: string;
    data: OHLCData[];
    params?: Record<string, number | string>;
  }>,
  options: UseIndicatorWorkerOptions = {}
): {
  results: IndicatorResult[];
  status: CalculationStatus;
  error: string | null;
  progress: number;
} {
  const { calculateBatch, status, error, isReady } = useIndicatorWorker(options);
  const [results, setResults] = useState<IndicatorResult[]>([]);
  const [progress, setProgress] = useState(0);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;

    if (!isReady || calculations.length === 0) {
      setResults([]);
      setProgress(0);
      return;
    }

    const runCalculations = async () => {
      try {
        setProgress(0);
        
        // Convert to CalculationRequest format
        const requests: CalculationRequest[] = calculations.map(c => ({
          indicator: c.indicator,
          data: c.data,
          params: c.params || {},
        }));

        const newResults = await calculateBatch(requests);
        
        if (isMountedRef.current) {
          setResults(newResults);
          setProgress(100);
        }
      } catch (err) {
        if (isMountedRef.current) {
          setResults([]);
        }
      }
    };

    runCalculations();

    return () => {
      isMountedRef.current = false;
    };
  }, [calculateBatch, calculations, isReady]);

  // Update progress based on status
  useEffect(() => {
    if (status === 'loading') {
      setProgress((prev) => (prev < 90 ? prev + 10 : prev));
    } else if (status === 'success') {
      setProgress(100);
    }
  }, [status]);

  return {
    results,
    status,
    error,
    progress,
  };
}

/**
 * Hook for managing a pool of workers directly
 */
export function useWorkerPool(options: WorkerPoolOptions = {}): {
  pool: WorkerPool | null;
  stats: {
    poolSize: number;
    activeWorkers: number;
    queuedTasks: number;
    completedTasks: number;
  };
  isHealthy: boolean;
} {
  const poolRef = useRef<WorkerPool | null>(null);
  const [stats, setStats] = useState({
    poolSize: 0,
    activeWorkers: 0,
    queuedTasks: 0,
    completedTasks: 0,
  });
  const [isHealthy, setIsHealthy] = useState(true);

  useEffect(() => {
    poolRef.current = getGlobalWorkerPool(options);

    // Poll stats
    const interval = setInterval(() => {
      if (poolRef.current) {
        const poolStats = poolRef.current.getStats();
        setStats({
          poolSize: poolStats.poolSize,
          activeWorkers: poolStats.activeWorkers,
          queuedTasks: poolStats.queuedTasks,
          completedTasks: poolStats.completedTasks,
        });
        setIsHealthy(poolRef.current.isHealthy());
      }
    }, 1000);

    return () => {
      clearInterval(interval);
    };
  }, [options]);

  return {
    pool: poolRef.current,
    stats,
    isHealthy,
  };
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Preload the worker pool to avoid initialization delays
 */
export function preloadWorkerPool(options?: WorkerPoolOptions): void {
  getGlobalWorkerPool(options);
}

/**
 * Terminate the global worker pool
 */
export function terminateWorkerPool(): void {
  const pool = getGlobalWorkerPool();
  pool.terminate();
}

export default useIndicatorWorker;
