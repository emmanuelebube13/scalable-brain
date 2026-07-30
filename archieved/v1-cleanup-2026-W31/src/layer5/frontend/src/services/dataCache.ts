/**
 * Data Cache Service — Caches API responses to avoid refetching data
 * and preloads critical data at app startup
 */

import type {
  KPIData,
  Trade,
  Signal,
  RegimeData,
  RiskMetrics,
  ModelMetadata,
  Strategy,
  Asset,
} from '@/types';
import * as api from './api';

interface CachedData {
  timestamp: number;
  data: any;
}

class DataCache {
  private cache = new Map<string, CachedData>();
  private readonly TTL_MS = 5 * 60 * 1000; // 5 minute cache TTL
  private preloadPromises = new Map<string, Promise<any>>();

  /**
   * Get cached data if available and not expired
   */
  get<T>(key: string): T | null {
    const cached = this.cache.get(key);
    if (!cached) return null;

    const isExpired = Date.now() - cached.timestamp > this.TTL_MS;
    if (isExpired) {
      this.cache.delete(key);
      return null;
    }

    return cached.data as T;
  }

  /**
   * Set cache data
   */
  set<T>(key: string, data: T): void {
    this.cache.set(key, {
      timestamp: Date.now(),
      data,
    });
  }

  /**
   * Clear specific cache entry
   */
  clear(key: string): void {
    this.cache.delete(key);
  }

  /**
   * Clear all cache
   */
  clearAll(): void {
    this.cache.clear();
  }

  /**
   * Preload critical data at app startup
   * Runs in background without blocking
   */
  preloadCriticalData(): void {
    const criticalEndpoints = [
      { key: 'kpi', fetcher: () => api.fetchKPI() },
      { key: 'trades', fetcher: () => api.fetchTrades(10) },
      { key: 'regimes', fetcher: () => api.fetchCurrentRegimes() },
      { key: 'risk', fetcher: () => api.fetchRiskMetrics() },
      { key: 'strategies', fetcher: () => api.fetchStrategies() },
      { key: 'assets', fetcher: () => api.fetchAssets() },
    ];

    for (const { key, fetcher } of criticalEndpoints) {
      // Don't refetch if already in progress
      if (this.preloadPromises.has(key)) continue;

      const promise = fetcher()
        .then((data) => {
          this.set(key, data);
          return data;
        })
        .catch((error) => {
          console.warn(`Failed to preload ${key}:`, error);
          return null;
        })
        .finally(() => {
          this.preloadPromises.delete(key);
        });

      this.preloadPromises.set(key, promise);
    }
  }

  /**
   * Fetch with caching — returns cached data if available, otherwise fetches
   */
  async fetchWithCache<T>(
    key: string,
    fetcher: () => Promise<T>,
    options?: { bypassCache?: boolean; ttl?: number }
  ): Promise<T> {
    if (!options?.bypassCache) {
      const cached = this.get<T>(key);
      if (cached) return cached;
    }

    const data = await fetcher();
    this.set(key, data);
    return data;
  }
}

// Singleton instance
export const dataCache = new DataCache();

/**
 * Hook for React components to use cached data
 * Fetches data and caches it for future use
 */
export async function useCachedData<T>(
  key: string,
  fetcher: () => Promise<T>,
  options?: { bypassCache?: boolean; ttl?: number }
): Promise<T> {
  return dataCache.fetchWithCache(key, fetcher, options);
}
