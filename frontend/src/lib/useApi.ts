import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export interface ApiState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
}

/**
 * Loads `fn` whenever `deps` change. With `pollMs`, re-fetches on that interval
 * while `shouldPoll(data)` is true (used for queued/running experiments).
 */
export function useApi<T>(
  fn: () => Promise<T>,
  deps: unknown[],
  opts: { pollMs?: number; shouldPoll?: (data: T | undefined) => boolean; enabled?: boolean } = {},
): ApiState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError>();
  const [loading, setLoading] = useState(opts.enabled !== false);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (opts.enabled === false) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fnRef
      .current()
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(undefined);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, opts.enabled]);

  const { pollMs, shouldPoll } = opts;
  useEffect(() => {
    if (!pollMs || !shouldPoll?.(data)) return;
    const t = setTimeout(() => setTick((x) => x + 1), pollMs);
    return () => clearTimeout(t);
  }, [data, pollMs, shouldPoll]);

  const reload = useCallback(() => setTick((x) => x + 1), []);
  return { data, error, loading, reload };
}
