import { useCallback, useEffect, useRef, useState } from "react";

interface AsyncOptions<T> {
  immediate?: boolean;
  transform?: (value: T) => T;
  listenToRefreshEvent?: boolean;
  pollIntervalMs?: number;
  showLoadingOnRefresh?: boolean;
}

export const useAsyncData = <T,>(
  loader: () => Promise<T>,
  deps: ReadonlyArray<unknown> = [],
  options: AsyncOptions<T> = {}
) => {
  const {
    immediate = true,
    transform,
    listenToRefreshEvent = true,
    pollIntervalMs,
    showLoadingOnRefresh = false
  } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(immediate);
  const [error, setError] = useState<Error | null>(null);
  const isMountedRef = useRef(true);
  const firstLoadRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const execute = useCallback(async () => {
    if (!isMountedRef.current) {
      return;
    }

    const nextLoadingState = firstLoadRef.current || showLoadingOnRefresh;
    setLoading(nextLoadingState);
    setError(null);
    try {
      const result = await loader();
      if (!isMountedRef.current) {
        return;
      }
      setData(transform ? transform(result) : result);
    } catch (err) {
      if (!isMountedRef.current) {
        return;
      }
      setError(err instanceof Error ? err : new Error("Unknown error"));
    } finally {
      if (!isMountedRef.current) {
        return;
      }
      setLoading(false);
      firstLoadRef.current = false;
    }
  }, [loader, transform, showLoadingOnRefresh]);

  useEffect(() => {
    if (!listenToRefreshEvent || typeof window === "undefined") {
      return () => undefined;
    }
    const handler = () => {
      void execute();
    };
    window.addEventListener("app:refresh-data", handler);
    return () => {
      window.removeEventListener("app:refresh-data", handler);
    };
  }, [execute, listenToRefreshEvent]);

  useEffect(() => {
    if (immediate) {
      void execute();
    }
  }, [immediate, execute, ...deps]);

  useEffect(() => {
    if (!pollIntervalMs || pollIntervalMs <= 0 || typeof window === "undefined") {
      return () => undefined;
    }
    const interval = window.setInterval(() => {
      void execute();
    }, pollIntervalMs);
    return () => {
      window.clearInterval(interval);
    };
  }, [execute, pollIntervalMs]);

  return {
    data,
    loading,
    error,
    refresh: execute
  };
};
