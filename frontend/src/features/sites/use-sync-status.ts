'use client';

import { ApiError } from '@/lib/api/client';
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Shared polling hook for integration sync cards (WordPress · GSC · future GA4).
 * Loads once (and again whenever `refreshKey` changes, e.g. after a connection test queued a job)
 * and keeps polling every `intervalMs` while `shouldPoll(status)` says a run is active.
 */
export function useIntegrationSyncStatus<T>({ load, shouldPoll, refreshKey = 0, intervalMs = 2000 }: {
  load: () => Promise<T>;
  shouldPoll: (s: T | null) => boolean;
  refreshKey?: number;
  intervalMs?: number;
}) {
  const [status, setStatus] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reload = useCallback(async () => {
    try {
      const s = await load();
      setStatus(s);
      setError(null);
      return s;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      return null;
    }
  }, [load]);

  useEffect(() => { void reload(); }, [reload, refreshKey]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (shouldPoll(status)) timer.current = setTimeout(() => { void reload(); }, intervalMs);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [status, shouldPoll, reload, intervalMs]);

  return { status, error, setError, reload };
}
