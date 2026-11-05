'use client';
import { useCallback, useEffect, useRef, useState, type SetStateAction } from 'react';
import type { ApiResult, DirectoryPage } from './directory-api';

/** Cursor history belongs to one filter set. Late responses cannot overwrite newer searches. */
export function useApiDirectory<T, Q extends { limit: number }>(
  initialQuery: Q, fetchPage: (query: Q, cursor?: string) => Promise<ApiResult<DirectoryPage<T>>>,
) {
  const [query, setQueryValue] = useState(initialQuery);
  const [pageIndex, setIndex] = useState(0);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<DirectoryPage<T>>({ items: [], total: 0, next_cursor: null, has_more: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const cursors = useRef<(string | undefined)[]>([undefined]);
  const setQuery = useCallback((next: SetStateAction<Q>) => {
    setQueryValue(next); setIndex(0); cursors.current = [undefined];
  }, []);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  const setPageIndex = useCallback((index: number) => {
    if (index === 0 || cursors.current[index] !== undefined) setIndex(Math.max(0, index));
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(undefined);
    const timeout = setTimeout(() => {
      if (!active) return;
      active = false;
      setError('Loading took too long. Please retry.');
      setLoading(false);
    }, 20000);
    void fetchPage(query, cursors.current[pageIndex]).then(response => {
      if (!active) return;
      if (response.error !== undefined) { setError(response.error); return; }
      if (!response.value.items.length && pageIndex > 0) { setIndex(pageIndex - 1); return; }
      setResult(response.value);
      cursors.current[pageIndex + 1] = response.value.next_cursor ?? undefined;
    }).catch(() => { if (active) setError('Unable to load records. Please try again.'); })
      .finally(() => { clearTimeout(timeout); if (active) setLoading(false); });
    return () => { active = false; clearTimeout(timeout); };
  }, [query, pageIndex, revision, fetchPage]);
  return { query, setQuery, pageIndex, setPageIndex, loading, error, reload,
    page: { ...result, page: pageIndex, from: result.items.length ? pageIndex * query.limit + 1 : 0 } };
}
