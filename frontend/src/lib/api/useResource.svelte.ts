import { apiCache } from "$lib/api/cache";

export interface ResourceState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

/**
 * A Svelte 5 Universal Rune for read-through caching and background revalidation.
 */
export function useResource<T>(
  resourceType: string,
  resourceId: string,
  fetcher: () => Promise<{ data?: T; error?: any }>
) {
  // Initialize state using $state rune
  const state = $state<ResourceState<T>>({
    data: null,
    loading: true,
    error: null
  });

  // Trigger cache logic reactively whenever the ID or type changes
  $effect(() => {
    // Reset loading if we don't have cached data for the new ID
    const { data: cachedData, promise } = apiCache.getOrFetch(resourceType, resourceId, fetcher);

    if (cachedData) {
      state.data = cachedData;
      state.loading = false;
      state.error = null;
    } else {
      state.data = null;
      state.loading = true;
      state.error = null;
    }

    // Handle the network resolution/revalidation silently
    promise
      .then((response) => {
        // openapi-ts functions return an object with a .data wrapper
        if (response && "data" in response) {
          state.data = response.data as T;
        } else {
          state.data = response as T;
        }
        state.loading = false;
      })
      .catch((err) => {
        // Only show error visually if we don't have stale cached data to show
        if (!state.data) {
          state.error = err;
          state.loading = false;
        }
        console.error(`Background revalidation failed for ${resourceType}:${resourceId}`, err);
      });
  });

  // Return a read-only getter to preserve Svelte 5 reactivity
  return {
    get data() {
      return state.data;
    },
    get loading() {
      return state.loading;
    },
    get error() {
      return state.error;
    }
  };
}

export function useResources<T>(
  resourceType: string,
  idKey: keyof T,
  fetcher: () => Promise<{ data?: Array<T>; error?: any }>
) {
  // Initialize state using $state rune
  const state = $state<ResourceState<T>>({
    data: null,
    loading: true,
    error: null
  });

  // Trigger cache logic reactively whenever the ID or type changes
  $effect(() => {
    // Reset loading if we don't have cached data for the new ID
    promise = fetcher().then((freshData) => {
      apiCache.warmList(resourceType, idKey, freshData.data);
      return freshData;
    });

    // Handle the network resolution/revalidation silently
    promise
      .then((response) => {
        // openapi-ts functions return an object with a .data wrapper
        if (response && "data" in response) {
          state.data = response.data as T;
        } else {
          state.data = response as T;
        }
        state.loading = false;
      })
      .catch((err) => {
        // Only show error visually if we don't have stale cached data to show
        if (!state.data) {
          state.error = err;
          state.loading = false;
        }
        console.error(`Background revalidation failed for ${resourceType}:${resourceId}`, err);
      });
  });

  // Return a read-only getter to preserve Svelte 5 reactivity
  return {
    get data() {
      return state.data;
    },
    get loading() {
      return state.loading;
    },
    get error() {
      return state.error;
    }
  };
}
