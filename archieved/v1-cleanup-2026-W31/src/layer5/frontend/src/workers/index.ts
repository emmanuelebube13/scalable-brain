/**
 * Web Workers exports
 * 
 * This module provides Web Worker functionality for client-side indicator calculations,
 * improving chart performance by offloading heavy computations to separate threads.
 * 
 * @example
 * ```tsx
 * import { useIndicatorWorker } from '@/hooks/useIndicatorWorker';
 * 
 * function ChartComponent({ data }) {
 *   const { calculate, status } = useIndicatorWorker();
 *   
 *   useEffect(() => {
 *     calculate('sma', data, { period: 20 })
 *       .then(result => console.log(result))
 *       .catch(err => console.error(err));
 *   }, [data]);
 * }
 * ```
 */

// Worker Pool
export { WorkerPool, getGlobalWorkerPool, terminateGlobalWorkerPool } from './WorkerPool';
export type {
  WorkerTask,
  PooledWorker,
  WorkerPoolOptions,
  WorkerPoolStats,
} from './WorkerPool';

// Indicator Worker Types
export type {
  WorkerMessageType,
  WorkerResponseType,
  WorkerMessage,
  WorkerResponse,
} from './indicatorWorker';
