/**
 * Web Worker for client-side indicator calculations
 * Runs in a separate thread to avoid blocking the main UI
 * 
 * @ts-nocheck - Web Worker global scope types
 */

/// <reference lib="webworker" />

import type { OHLCData, IndicatorResult } from '@/types';
import type { CalculationRequest } from '@/utils/indicatorCalculations';
import { calculateIndicator } from '@/utils/indicatorCalculations';

// ============================================================================
// Message Types
// ============================================================================

export type WorkerMessageType = 
  | 'calculate' 
  | 'calculateBatch' 
  | 'cancel' 
  | 'ping';

export type WorkerResponseType = 
  | 'result' 
  | 'batchResult' 
  | 'error' 
  | 'pong' 
  | 'cancelled';

export interface WorkerMessage {
  id: string;
  type: WorkerMessageType;
  indicator?: string;
  data?: OHLCData[];
  params?: Record<string, number | string>;
  calculations?: CalculationRequest[];
  cancelId?: string;
}

export interface WorkerResponse {
  id: string;
  type: WorkerResponseType;
  result?: IndicatorResult;
  results?: IndicatorResult[];
  error?: string;
  cancelledId?: string;
}

// ============================================================================
// Worker State
// ============================================================================

interface PendingTask {
  id: string;
  startTime: number;
  abortController: AbortController;
}

const pendingTasks = new Map<string, PendingTask>();
let taskCounter = 0;

// ============================================================================
// Message Handler
// ============================================================================

self.onmessage = function (event: MessageEvent<WorkerMessage>) {
  const message = event.data;
  
  if (!message || !message.id) {
    console.error('[IndicatorWorker] Invalid message received');
    return;
  }

  switch (message.type) {
    case 'calculate':
      handleCalculate(message);
      break;
    
    case 'calculateBatch':
      handleCalculateBatch(message);
      break;
    
    case 'cancel':
      handleCancel(message);
      break;
    
    case 'ping':
      sendResponse(message.id, { type: 'pong' });
      break;
    
    default:
      sendError(message.id, `Unknown message type: ${(message as WorkerMessage).type}`);
  }
};

// ============================================================================
// Calculation Handlers
// ============================================================================

function handleCalculate(message: WorkerMessage): void {
  const { id, indicator, data, params = {} } = message;

  if (!indicator) {
    sendError(id, 'Indicator type not specified');
    return;
  }

  if (!data || !Array.isArray(data) || data.length === 0) {
    sendError(id, 'No data provided for calculation');
    return;
  }

  // Create abort controller for cancellation support
  const abortController = new AbortController();
  const taskId = `calc_${++taskCounter}`;
  
  pendingTasks.set(taskId, {
    id,
    startTime: Date.now(),
    abortController,
  });

  try {
    // Check if cancelled before starting
    if (abortController.signal.aborted) {
      pendingTasks.delete(taskId);
      return;
    }

    // Perform calculation
    const startTime = performance.now();
    const result = calculateIndicator(indicator, data, params);
    const duration = performance.now() - startTime;

    // Log performance in development
    // Log performance (disabled in worker context)
    // console.log(`[IndicatorWorker] ${indicator} calculated in ${duration.toFixed(2)}ms (${data.length} bars)`);

    // Check if cancelled after calculation
    if (abortController.signal.aborted) {
      pendingTasks.delete(taskId);
      return;
    }

    pendingTasks.delete(taskId);

    // Return result
    sendResponse(id, {
      type: 'result',
      result: {
        ...result,
        // Add metadata
        metadata: {
          calculationTime: duration,
          dataPoints: data.length,
        },
      } as IndicatorResult,
    });
  } catch (error) {
    pendingTasks.delete(taskId);
    
    const errorMessage = error instanceof Error 
      ? error.message 
      : 'Unknown error during calculation';
    
    console.error(`[IndicatorWorker] Error calculating ${indicator}:`, errorMessage);
    
    sendError(id, errorMessage);
  }
}

function handleCalculateBatch(message: WorkerMessage): void {
  const { id, calculations } = message;

  if (!calculations || !Array.isArray(calculations) || calculations.length === 0) {
    sendError(id, 'No calculations provided for batch');
    return;
  }

  // Create abort controller for cancellation support
  const abortController = new AbortController();
  const taskId = `batch_${++taskCounter}`;
  
  pendingTasks.set(taskId, {
    id,
    startTime: Date.now(),
    abortController,
  });

  try {
    // Check if cancelled before starting
    if (abortController.signal.aborted) {
      pendingTasks.delete(taskId);
      return;
    }

    // Perform batch calculation
    const startTime = performance.now();
    const results: IndicatorResult[] = [];
    
    for (let i = 0; i < calculations.length; i++) {
      // Check for cancellation between calculations
      if (abortController.signal.aborted) {
        pendingTasks.delete(taskId);
        return;
      }

      const calc = calculations[i];
      const result = calculateIndicator(
        calc.indicator,
        calc.data,
        calc.params
      );
      results.push(result);
    }

    const duration = performance.now() - startTime;

    // Log performance (disabled in worker context)
    // console.log(`[IndicatorWorker] Batch of ${calculations.length} indicators calculated in ${duration.toFixed(2)}ms`);

    // Check if cancelled after calculation
    if (abortController.signal.aborted) {
      pendingTasks.delete(taskId);
      return;
    }

    pendingTasks.delete(taskId);

    // Return results
    sendResponse(id, {
      type: 'batchResult',
      results,
    });
  } catch (error) {
    pendingTasks.delete(taskId);
    
    const errorMessage = error instanceof Error 
      ? error.message 
      : 'Unknown error during batch calculation';
    
    console.error('[IndicatorWorker] Error in batch calculation:', errorMessage);
    
    sendError(id, errorMessage);
  }
}

function handleCancel(message: WorkerMessage): void {
  const { id, cancelId } = message;
  
  if (!cancelId) {
    // Cancel all pending tasks if no specific ID provided
    for (const [taskId, task] of pendingTasks.entries()) {
      task.abortController.abort();
      pendingTasks.delete(taskId);
      
      sendResponse(task.id, {
        type: 'cancelled',
        cancelledId: taskId,
      });
    }
  } else {
    // Cancel specific task
    const task = pendingTasks.get(cancelId);
    if (task) {
      task.abortController.abort();
      pendingTasks.delete(cancelId);
      
      sendResponse(task.id, {
        type: 'cancelled',
        cancelledId: cancelId,
      });
    }
  }

  // Acknowledge cancel request
  sendResponse(id, { type: 'pong' });
}

// ============================================================================
// Helper Functions
// ============================================================================

function sendResponse(id: string, response: Omit<WorkerResponse, 'id'>): void {
  self.postMessage({
    id,
    ...response,
  } as WorkerResponse);
}

function sendError(id: string, error: string): void {
  sendResponse(id, {
    type: 'error',
    error,
  });
}

// ============================================================================
// Error Handling
// ============================================================================

self.onerror = function (event: Event | string) {
  const message = typeof event === 'string' ? event : ((event as ErrorEvent).message || 'Unknown worker error');
  console.error('[IndicatorWorker] Unhandled error:', message);
  // Try to notify main thread about the error
  try {
    self.postMessage({
      id: 'worker-error',
      type: 'error',
      error: `Worker error: ${message}`,
    } as WorkerResponse);
  } catch {
    // Ignore if postMessage fails
  }
};

// Handle unhandled promise rejections
self.onunhandledrejection = function (event: PromiseRejectionEvent) {
  console.error('[IndicatorWorker] Unhandled rejection:', event.reason);
  event.preventDefault();
};

// Signal that worker is ready
console.log('[IndicatorWorker] Indicator calculation worker initialized');

// Export for TypeScript module resolution
export {};
