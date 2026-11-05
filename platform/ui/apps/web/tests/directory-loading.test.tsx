import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useApiDirectory } from '../src/lib/use-api-directory';
import type { ApiResult, DirectoryPage } from '../src/lib/directory-api';

afterEach(() => vi.useRealTimers());
const page = { items: ['new record'], total: 1, next_cursor: null, has_more: false };

it('ends a stalled read, allows retry, and ignores a late response from the timed-out read', async () => {
  vi.useFakeTimers();
  let finish!: (value: ApiResult<DirectoryPage<string>>) => void;
  const fetchPage = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockResolvedValue({ value: page });
  const { result } = renderHook(() => useApiDirectory({ limit: 25 }, fetchPage));
  await act(() => vi.advanceTimersByTimeAsync(20000));
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toContain('retry');
  await act(async () => { result.current.reload(); });
  expect(result.current.error).toBeUndefined();
  expect(result.current.page.items).toEqual(['new record']);
  await act(async () => { finish({ value: { ...page, items: ['stale record'] } }); });
  expect(result.current.page.items).toEqual(['new record']);
});

it('cleans up the deadline when a request succeeds or the component unmounts', async () => {
  vi.useFakeTimers();
  const fetchPage = vi.fn().mockResolvedValue({ value: page });
  const { result, unmount } = renderHook(() => useApiDirectory({ limit: 25 }, fetchPage));
  await act(async () => {});
  await act(() => vi.advanceTimersByTimeAsync(25000));
  expect(result.current.error).toBeUndefined();
  expect(result.current.loading).toBe(false);
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});
