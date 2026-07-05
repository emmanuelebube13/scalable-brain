/**
 * Worker Pool for parallel indicator calculations
 * Manages multiple Web Workers for improved performance
 */

import type { OHLCData, IndicatorResult } from '@/types';
import type { CalculationRequest } from '@/utils/indicatorCalculations';
import type { WorkerMessage, WorkerResponse } from './indicatorWorker';

// ============================================================================
// Types
// ============================================================================

export interface WorkerTask {
  id: string;
  type: 'calculate' | 'calculateBatch';
  indicator?: string;
  data?: OHLCData[];
  params?: Record<string, number | string>;
  calculations?: CalculationRequest[];
  resolve: (value: IndicatorResult | IndicatorResult[]) => void;
  reject: (reason: Error) => void;
  priority?: number;
  timestamp: number;
}

export interface PooledWorker {
  id: string;
  worker: Worker;
  busy: boolean;
  currentTaskId: string | null;
  taskCount: number;
  createdAt: number;
}

export interface WorkerPoolOptions {
  poolSize?: number;
  taskTimeout?: number;
  enableRoundRobin?: boolean;
  maxQueueSize?: number;
  workerScriptUrl?: string;
}

export interface WorkerPoolStats {
  poolSize: number;
  activeWorkers: number;
  queuedTasks: number;
  completedTasks: number;
  failedTasks: number;
  averageTaskTime: number;
}

// ============================================================================
// Worker Pool Class
// ============================================================================

export class WorkerPool {
  private workers: PooledWorker[] = [];
  private taskQueue: WorkerTask[] = [];
  private completedTasks = 0;
  private failedTasks = 0;
  private totalTaskTime = 0;
  private taskCounter = 0;
  private roundRobinIndex = 0;
  private options: Required<WorkerPoolOptions>;

  constructor(options: WorkerPoolOptions = {}) {
    this.options = {
      poolSize: options.poolSize || navigator.hardwareConcurrency || 4,
      taskTimeout: options.taskTimeout || 30000,
      enableRoundRobin: options.enableRoundRobin ?? true,
      maxQueueSize: options.maxQueueSize || 100,
      workerScriptUrl: options.workerScriptUrl || this.getDefaultWorkerUrl(),
    };

    this.initializeWorkers();
  }

  // ============================================================================
  // Initialization
  // ============================================================================

  private getDefaultWorkerUrl(): string {
    // In Vite/Webpack, we need to use the ?worker syntax or import the worker
    // This will be resolved by the bundler
    return new URL('./indicatorWorker.ts', import.meta.url).href;
  }

  private initializeWorkers(): void {
    for (let i = 0; i < this.options.poolSize; i++) {
      this.createWorker(i);
    }
  }

  private createWorker(index: number): PooledWorker {
    try {
      const worker = new Worker(
        new URL('./indicatorWorker.ts', import.meta.url),
        { type: 'module' }
      );

      const pooledWorker: PooledWorker = {
        id: `worker-${index}`,
        worker,
        busy: false,
        currentTaskId: null,
        taskCount: 0,
        createdAt: Date.now(),
      };

      worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
        this.handleWorkerMessage(pooledWorker, event.data);
      };

      worker.onerror = (error) => {
        console.error(`[WorkerPool] Worker ${pooledWorker.id} error:`, error);
        this.handleWorkerError(pooledWorker, error);
      };

      this.workers.push(pooledWorker);
      return pooledWorker;
    } catch (error) {
      console.error(`[WorkerPool] Failed to create worker ${index}:`, error);
      throw error;
    }
  }

  // ============================================================================
  // Task Management
  // ============================================================================

  /**
   * Calculate a single indicator using the worker pool
   */
  public calculate(
    indicator: string,
    data: OHLCData[],
    params: Record<string, number | string> = {},
    priority = 0
  ): Promise<IndicatorResult> {
    return new Promise((resolve, reject) => {
      if (this.taskQueue.length >= this.options.maxQueueSize) {
        reject(new Error('Task queue is full'));
        return;
      }

      const task: WorkerTask = {
        id: `task-${++this.taskCounter}`,
        type: 'calculate',
        indicator,
        data,
        params,
        resolve: resolve as (value: IndicatorResult | IndicatorResult[]) => void,
        reject,
        priority,
        timestamp: Date.now(),
      };

      this.enqueueTask(task);
    });
  }

  /**
   * Calculate multiple indicators in batch using the worker pool
   */
  public calculateBatch(
    calculations: CalculationRequest[],
    priority = 0
  ): Promise<IndicatorResult[]> {
    return new Promise((resolve, reject) => {
      if (this.taskQueue.length >= this.options.maxQueueSize) {
        reject(new Error('Task queue is full'));
        return;
      }

      const task: WorkerTask = {
        id: `task-${++this.taskCounter}`,
        type: 'calculateBatch',
        calculations,
        resolve: resolve as (value: IndicatorResult | IndicatorResult[]) => void,
        reject,
        priority,
        timestamp: Date.now(),
      };

      this.enqueueTask(task);
    });
  }

  /**
   * Cancel a pending task
   */
  public cancel(taskId: string): boolean {
    // Remove from queue if not started
    const queueIndex = this.taskQueue.findIndex(t => t.id === taskId);
    if (queueIndex !== -1) {
      const task = this.taskQueue.splice(queueIndex, 1)[0];
      task.reject(new Error('Task cancelled'));
      return true;
    }

    // If running, send cancel message to worker
    const worker = this.workers.find(w => w.currentTaskId === taskId);
    if (worker) {
      this.sendMessage(worker, {
        id: `cancel-${Date.now()}`,
        type: 'cancel',
        cancelId: taskId,
      });
      return true;
    }

    return false;
  }

  /**
   * Cancel all pending and running tasks
   */
  public cancelAll(): void {
    // Cancel all queued tasks
    while (this.taskQueue.length > 0) {
      const task = this.taskQueue.shift()!;
      task.reject(new Error('All tasks cancelled'));
    }

    // Cancel running tasks
    this.workers.forEach(worker => {
      if (worker.currentTaskId) {
        this.sendMessage(worker, {
          id: `cancel-all-${Date.now()}`,
          type: 'cancel',
        });
      }
    });
  }

  // ============================================================================
  // Queue Management
  // ============================================================================

  private enqueueTask(task: WorkerTask): void {
    // Insert task based on priority (higher priority = earlier in queue)
    const insertIndex = this.taskQueue.findIndex(t => (t.priority || 0) < task.priority!);
    
    if (insertIndex === -1) {
      this.taskQueue.push(task);
    } else {
      this.taskQueue.splice(insertIndex, 0, task);
    }

    // Try to process the queue
    this.processQueue();
  }

  private processQueue(): void {
    if (this.taskQueue.length === 0) return;

    const availableWorker = this.getAvailableWorker();
    if (!availableWorker) return;

    const task = this.taskQueue.shift()!;
    this.executeTask(availableWorker, task);
  }

  private executeTask(worker: PooledWorker, task: WorkerTask): void {
    worker.busy = true;
    worker.currentTaskId = task.id;
    worker.taskCount++;

    const message: WorkerMessage = {
      id: task.id,
      type: task.type as 'calculate' | 'calculateBatch',
    };

    if (task.type === 'calculate') {
      message.indicator = task.indicator;
      message.data = task.data;
      message.params = task.params;
    } else {
      message.calculations = task.calculations;
    }

    // Set timeout
    const timeoutId = setTimeout(() => {
      this.handleTaskTimeout(worker, task);
    }, this.options.taskTimeout);

    // Store timeout on worker for cleanup
    (worker as unknown as { timeoutId: number }).timeoutId = timeoutId;

    this.sendMessage(worker, message);
  }

  private handleTaskTimeout(worker: PooledWorker, task: WorkerTask): void {
    console.warn(`[WorkerPool] Task ${task.id} timed out`);
    
    // Terminate and recreate worker
    this.terminateWorker(worker);
    this.createWorker(parseInt(worker.id.split('-')[1]));

    this.failedTasks++;
    task.reject(new Error(`Task timed out after ${this.options.taskTimeout}ms`));

    // Process next task
    this.processQueue();
  }

  // ============================================================================
  // Worker Selection Strategies
  // ============================================================================

  private getAvailableWorker(): PooledWorker | null {
    if (this.options.enableRoundRobin) {
      return this.getWorkerRoundRobin();
    }
    return this.getWorkerLeastBusy();
  }

  private getWorkerRoundRobin(): PooledWorker | null {
    const availableWorkers = this.workers.filter(w => !w.busy);
    if (availableWorkers.length === 0) return null;

    const worker = availableWorkers[this.roundRobinIndex % availableWorkers.length];
    this.roundRobinIndex++;
    return worker;
  }

  private getWorkerLeastBusy(): PooledWorker | null {
    return this.workers
      .filter(w => !w.busy)
      .sort((a, b) => a.taskCount - b.taskCount)[0] || null;
  }

  // ============================================================================
  // Message Handling
  // ============================================================================

  private sendMessage(worker: PooledWorker, message: WorkerMessage): void {
    try {
      worker.worker.postMessage(message);
    } catch (error) {
      console.error(`[WorkerPool] Failed to send message to worker ${worker.id}:`, error);
      this.handleWorkerError(worker, error as ErrorEvent);
    }
  }

  private handleWorkerMessage(worker: PooledWorker, response: WorkerResponse): void {
    // Clear timeout
    const timeoutId = (worker as unknown as { timeoutId?: number }).timeoutId;
    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    // Handle pong (health check)
    if (response.type === 'pong') {
      return;
    }

    // Find the task
    const taskId = worker.currentTaskId;
    if (!taskId) {
      console.warn(`[WorkerPool] Received message from idle worker ${worker.id}`);
      return;
    }

    // Reset worker state
    worker.busy = false;
    worker.currentTaskId = null;

    // Calculate task time
    const taskTime = Date.now() - parseInt(taskId.split('-')[1]);
    this.totalTaskTime += taskTime;

    // Handle different response types
    switch (response.type) {
      case 'result':
        this.completedTasks++;
        // Find the task in queue (it might have been cancelled)
        this.resolveTask(taskId, response.result!);
        break;

      case 'batchResult':
        this.completedTasks++;
        this.resolveTask(taskId, response.results!);
        break;

      case 'error':
        this.failedTasks++;
        this.rejectTask(taskId, new Error(response.error || 'Unknown error'));
        break;

      case 'cancelled':
        this.rejectTask(taskId, new Error('Task was cancelled'));
        break;
    }

    // Process next task
    this.processQueue();
  }

  private handleWorkerError(worker: PooledWorker, error: ErrorEvent | Error): void {
    const taskId = worker.currentTaskId;
    
    // Reset worker
    worker.busy = false;
    
    if (taskId) {
      worker.currentTaskId = null;
      this.failedTasks++;
      this.rejectTask(taskId, new Error(error instanceof Error ? error.message : 'Worker error'));
    }

    // Process next task
    this.processQueue();
  }

  private resolveTask(taskId: string, result: IndicatorResult | IndicatorResult[]): void {
    // In a real implementation, we'd store the task reference
    // For now, we'll use a simple event-based approach
    const event = new CustomEvent('taskComplete', { detail: { taskId, result } });
    window.dispatchEvent(event);
  }

  private rejectTask(taskId: string, error: Error): void {
    const event = new CustomEvent('taskError', { detail: { taskId, error } });
    window.dispatchEvent(event);
  }

  // ============================================================================
  // Lifecycle Management
  // ============================================================================

  private terminateWorker(worker: PooledWorker): void {
    try {
      worker.worker.terminate();
    } catch (error) {
      console.error(`[WorkerPool] Error terminating worker ${worker.id}:`, error);
    }

    // Remove from workers array
    const index = this.workers.indexOf(worker);
    if (index !== -1) {
      this.workers.splice(index, 1);
    }
  }

  /**
   * Terminate all workers and clean up
   */
  public terminate(): void {
    this.cancelAll();
    
    this.workers.forEach(worker => {
      this.terminateWorker(worker);
    });

    this.workers = [];
    this.taskQueue = [];
  }

  /**
   * Resize the worker pool
   */
  public resize(newSize: number): void {
    if (newSize < 1) {
      throw new Error('Pool size must be at least 1');
    }

    const currentSize = this.workers.length;

    if (newSize > currentSize) {
      // Add workers
      for (let i = currentSize; i < newSize; i++) {
        this.createWorker(i);
      }
    } else if (newSize < currentSize) {
      // Remove workers (prefer idle ones)
      const toRemove = currentSize - newSize;
      const idleWorkers = this.workers.filter(w => !w.busy);
      
      for (let i = 0; i < Math.min(toRemove, idleWorkers.length); i++) {
        this.terminateWorker(idleWorkers[i]);
      }
    }

    this.options.poolSize = newSize;
  }

  // ============================================================================
  // Statistics
  // ============================================================================

  public getStats(): WorkerPoolStats {
    const completed = this.completedTasks;
    const averageTime = completed > 0 ? this.totalTaskTime / completed : 0;

    return {
      poolSize: this.workers.length,
      activeWorkers: this.workers.filter(w => w.busy).length,
      queuedTasks: this.taskQueue.length,
      completedTasks: this.completedTasks,
      failedTasks: this.failedTasks,
      averageTaskTime: averageTime,
    };
  }

  /**
   * Check if pool is healthy
   */
  public isHealthy(): boolean {
    return this.workers.length > 0 && this.workers.every(w => {
      const age = Date.now() - w.createdAt;
      return age < 3600000; // Workers older than 1 hour might need restart
    });
  }

  /**
   * Get the number of pending tasks
   */
  public getPendingCount(): number {
    return this.taskQueue.length + this.workers.filter(w => w.busy).length;
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

let globalWorkerPool: WorkerPool | null = null;

/**
 * Get or create the global worker pool instance
 */
export function getGlobalWorkerPool(options?: WorkerPoolOptions): WorkerPool {
  if (!globalWorkerPool) {
    globalWorkerPool = new WorkerPool(options);
  }
  return globalWorkerPool;
}

/**
 * Terminate the global worker pool
 */
export function terminateGlobalWorkerPool(): void {
  if (globalWorkerPool) {
    globalWorkerPool.terminate();
    globalWorkerPool = null;
  }
}

export default WorkerPool;
