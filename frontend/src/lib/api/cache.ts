// src/lib/api/cache.ts
import { writable, get } from "svelte/store";

export interface CacheEntry<T = any> {
  data: T;
  fetchedAt: number; // Timestamp in ms
}

// Nested structure: cache[resourceType][id] = CacheEntry
type CacheStoreData = Record<string, Record<string, CacheEntry>>;

class CacheManager {
  // A single, unified store for all resource types
  private store = writable<CacheStoreData>({});
  private defaultTtl = 5 * 60 * 1000; // 5 minutes default

  /**
   * Warm the cache using an array of items (e.g., from a list endpoint).
   */
  warmList<T>(resourceType: string, idKey: keyof T, items: T[]) {
    this.store.update((current) => {
      if (!current[resourceType]) current[resourceType] = {};

      const now = Date.now();
      items.forEach((item) => {
        const id = String(item[idKey]);
        current[resourceType][id] = { data: item, fetchedAt: now };
      });

      return current;
    });
  }

  /**
   * Core read-through logic: Returns cached data instantly if present,
   * but triggers a lazy background refresh if the data is stale.
   */
  getOrFetch<T>(
    resourceType: string,
    id: string,
    fetcher: () => Promise<T>,
    ttl = this.defaultTtl
  ): { data: T | null; promise: Promise<T> } {
    const currentCache = get(this.store);
    const cachedEntry = currentCache[resourceType]?.[id];
    const now = Date.now();

    const isMissing = !cachedEntry;
    const isStale = cachedEntry && now - cachedEntry.fetchedAt > ttl;

    // Trigger background or foreground fetch
    let networkPromise: Promise<T>;
    if (isMissing || isStale) {
      networkPromise = fetcher().then((freshData) => {
        this.store.update((current) => {
          if (!current[resourceType]) current[resourceType] = {};
          current[resourceType][id] = { data: freshData, fetchedAt: Date.now() };
          return current;
        });
        return freshData;
      });
    } else {
      // Just pretend like the cached one is new
      networkPromise = Promise.resolve(cachedEntry.data);
    }

    // Stale-While-Revalidate return signature:
    // Give the caller the stale data *immediately*, paired with the resolving network promise
    return {
      data: cachedEntry ? cachedEntry.data : null,
      promise: networkPromise
    };
  }

  /**
   * Completely invalidate a specific resource type or a single item
   */
  invalidate(resourceType: string, id?: string) {
    this.store.update((current) => {
      if (!current[resourceType]) return current;
      if (id) {
        delete current[resourceType][id];
      } else {
        current[resourceType] = {};
      }
      return current;
    });
  }

  /**
   * Request list of resources, applying query parameters and cache results
   * Return previously cached results while awaiting new results
   */
  fetchList<T>(
    resourceType: string,
    idKey: keyof T,
    fetcher: () => Promise<Array<T>>,
    queryParams: Record<string, Array<string>> = {},
    ttl = this.defaultTtl
  ): { data: Array<T> | null; promise: Promise<Array<T>> } {
    // construct cache key for query params
    // lookup `${resourceType}-cache` for list of ids
  }
}

export const apiCache = new CacheManager();
