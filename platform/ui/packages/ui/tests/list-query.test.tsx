/**
 * `useListQuery` and its serialisers.
 *
 * Three invariants carry this module, and each is a run of tests below:
 *
 *  - **A cursor is only valid for the query that produced it**, so every query change restarts the
 *    walk at page one. A test per mutator, because forgetting one is a 422 the reader cannot explain.
 *  - **Keyset cursors only point forward**, so "previous" walks a stack of cursors already used.
 *  - **A cursor is not shareable** — it is opaque, expiring and bound to the actor — so it is in the
 *    request's parameters and never in the URL string.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  clampLimit,
  listQueryString,
  parseListQuery,
  parseSort,
  serializeSort,
  useListQuery,
  type PageMeta,
} from '../src/lib/list-query';

const page = (hasMore: boolean, cursor: string | null): PageMeta => ({
  limit: 50,
  has_more: hasMore,
  next_cursor: cursor,
});

describe('sort serialisation', () => {
  it('writes descending with a leading minus, ascending bare', () => {
    expect(
      serializeSort([
        { key: 'created_at', direction: 'desc' },
        { key: 'name', direction: 'asc' },
      ]),
    ).toBe('-created_at,name');
  });

  it('reads a sort string back', () => {
    expect(parseSort('-created_at,name')).toEqual([
      { key: 'created_at', direction: 'desc' },
      { key: 'name', direction: 'asc' },
    ]);
  });

  it('keeps at most three fields, because the server accepts three plus its own tie-breaker', () => {
    expect(parseSort('a,b,c,d')).toHaveLength(3);
    expect(
      serializeSort([
        { key: 'a', direction: 'asc' },
        { key: 'b', direction: 'asc' },
        { key: 'c', direction: 'asc' },
        { key: 'd', direction: 'asc' },
      ]),
    ).toBe('a,b,c');
  });

  it('reads an absent or empty sort as no sort', () => {
    expect(parseSort(null)).toEqual([]);
    expect(parseSort('')).toEqual([]);
    expect(parseSort(' , ')).toEqual([]);
  });
});

describe('limits', () => {
  it('clamps to the server bounds rather than sending a value it will reject', () => {
    expect(clampLimit(500)).toBe(200);
    expect(clampLimit(0)).toBe(1);
    expect(clampLimit(Number.NaN)).toBe(50);
    expect(clampLimit(75)).toBe(75);
  });
});

describe('listQueryString', () => {
  const query = {
    q: 'north',
    sort: [{ key: 'created_at', direction: 'desc' as const }],
    filters: { status: 'POSTED', channel: ['EMAIL', 'SMS'] },
    limit: 50,
  };

  it('serialises search, sort and filters, and omits the default page size', () => {
    expect(listQueryString(query)).toBe(
      'q=north&sort=-created_at&channel=EMAIL&channel=SMS&status=POSTED',
    );
  });

  it('sends an `in` list as a repeated parameter, so a value containing a comma survives', () => {
    const string = listQueryString({ ...query, filters: { name: ['Smith, John', 'Ada'] } });

    expect(new URLSearchParams(string).getAll('name')).toEqual(['Smith, John', 'Ada']);
  });

  it('is stable for the same query, whatever order the filters were set in', () => {
    expect(listQueryString({ ...query, filters: { b: '2', a: '1' } })).toBe(
      listQueryString({ ...query, filters: { a: '1', b: '2' } }),
    );
  });

  it('drops an empty filter — an empty string or an empty list is not a predicate', () => {
    expect(listQueryString({ ...query, q: '', sort: [], filters: { status: '', tag: [] } })).toBe('');
  });

  it('states a non-default page size', () => {
    expect(listQueryString({ ...query, q: '', sort: [], filters: {}, limit: 100 })).toBe('limit=100');
  });
});

describe('parseListQuery', () => {
  it('reads a query out of a URL, keeping only the filters the screen declares', () => {
    const query = parseListQuery('q=north&sort=-created_at&status=POSTED&limit=100&bogus=1', {
      filterKeys: ['status'],
    });

    expect(query).toEqual({
      q: 'north',
      sort: [{ key: 'created_at', direction: 'desc' }],
      filters: { status: 'POSTED' },
      limit: 100,
    });
  });

  it('reads a repeated parameter as a list', () => {
    const query = parseListQuery('channel=EMAIL&channel=SMS', { filterKeys: ['channel'] });

    expect(query.filters).toEqual({ channel: ['EMAIL', 'SMS'] });
  });

  it('ignores a cursor in the URL — it is not something a link may carry', () => {
    // Named as a filter on purpose: a reserved parameter is never read as one, so a screen with a
    // mistake in its filter list cannot smuggle a cursor back into the shareable query.
    const query = parseListQuery('cursor=v2.abc&q=north', { filterKeys: ['cursor', 'limit'] });

    expect(query.filters).toEqual({});
    expect(listQueryString(query)).toBe('q=north');
  });

  it('refuses to serialise a filter named after a reserved parameter', () => {
    const string = listQueryString({
      q: '',
      sort: [],
      filters: { cursor: 'forged', status: 'POSTED' },
      limit: 50,
    });

    expect(string).toBe('status=POSTED');
  });

  it('clamps a hand-edited limit instead of forwarding a 422', () => {
    expect(parseListQuery('limit=5000').limit).toBe(200);
  });

  it('accepts a URLSearchParams as well as a string', () => {
    expect(parseListQuery(new URLSearchParams('q=north')).q).toBe('north');
  });
});

describe('useListQuery — the walk', () => {
  it('starts on the first page with no cursor', () => {
    const { result } = renderHook(() => useListQuery({ meta: page(true, 'c1') }));

    expect(result.current.cursor).toBeNull();
    expect(result.current.page).toMatchObject({ index: 0, from: 1, hasPrevious: false, hasNext: true });
  });

  it('has no next page when the response says there is no more', () => {
    const { result } = renderHook(() => useListQuery({ meta: page(false, null) }));

    expect(result.current.page.hasNext).toBe(false);
  });

  it('steps forward with the cursor the response handed it', () => {
    const { result } = renderHook(() => useListQuery({ meta: page(true, 'c1') }));

    act(() => result.current.nextPage());

    expect(result.current.cursor).toBe('c1');
    expect(result.current.page).toMatchObject({ index: 1, from: 51, hasPrevious: true });
    expect(result.current.params.get('cursor')).toBe('c1');
  });

  it('steps back through the cursors already used, because a keyset cursor only points forward', () => {
    const { result, rerender } = renderHook((meta: PageMeta) => useListQuery({ meta }), {
      initialProps: page(true, 'c1'),
    });

    act(() => result.current.nextPage());
    rerender(page(true, 'c2'));
    act(() => result.current.nextPage());
    expect(result.current.cursor).toBe('c2');

    act(() => result.current.previousPage());

    expect(result.current.cursor).toBe('c1');
    expect(result.current.page.index).toBe(1);
  });

  it('cannot step back from the first page', () => {
    const { result } = renderHook(() => useListQuery({ meta: page(true, 'c1') }));

    act(() => result.current.previousPage());

    expect(result.current.page.index).toBe(0);
  });

  it('ignores a step forward with nowhere to go', () => {
    const { result } = renderHook(() => useListQuery({ meta: page(false, 'c1') }));

    act(() => result.current.nextPage());

    expect(result.current.cursor).toBeNull();
  });

  it('drops the cursors ahead of it when the walk forks', () => {
    const { result, rerender } = renderHook((meta: PageMeta) => useListQuery({ meta }), {
      initialProps: page(true, 'c1'),
    });

    act(() => result.current.nextPage());
    rerender(page(true, 'c2'));
    act(() => result.current.nextPage());
    act(() => result.current.previousPage());
    // The rows may have shifted since; the cursor for page 3 is whatever this page now reports.
    rerender(page(true, 'c2-fresh'));
    act(() => result.current.nextPage());

    expect(result.current.cursor).toBe('c2-fresh');
    expect(result.current.page.index).toBe(2);
  });

  it('restarts the walk without touching the query — the recovery for a rejected cursor', () => {
    const { result } = renderHook(() => useListQuery({ initial: { q: 'north' }, meta: page(true, 'c1') }));

    act(() => result.current.nextPage());
    act(() => result.current.restart());

    expect(result.current.cursor).toBeNull();
    expect(result.current.page).toMatchObject({ index: 0, hasPrevious: false });
    expect(result.current.q).toBe('north');
  });
});

describe('useListQuery — a query change restarts the walk', () => {
  /** Every mutator, because the one that is forgotten is the one that 422s in production. */
  const cases: readonly [string, (handle: ReturnType<typeof useListQuery>) => void][] = [
    ['search', (handle) => handle.setSearch('north')],
    ['sort', (handle) => handle.setSort([{ key: 'name', direction: 'asc' }])],
    ['a filter', (handle) => handle.setFilter('status', 'POSTED')],
    ['the whole filter set', (handle) => handle.setFilters({ status: 'DRAFT' })],
    ['the page size', (handle) => handle.setLimit(100)],
  ];

  it.each(cases)('changing %s goes back to page one', (_label, change) => {
    const { result } = renderHook(() => useListQuery({ meta: page(true, 'c1') }));

    act(() => result.current.nextPage());
    expect(result.current.cursor).toBe('c1');

    act(() => change(result.current));

    // The cursor was signed over the previous query's filters, search and sort (§2.1).
    expect(result.current.cursor).toBeNull();
    expect(result.current.page).toMatchObject({ index: 0, from: 1, hasPrevious: false });
  });

  it('does not restart when a mutator changes nothing', () => {
    const { result } = renderHook(() => useListQuery({ initial: { q: 'north' }, meta: page(true, 'c1') }));

    act(() => result.current.nextPage());
    act(() => result.current.setSearch('north'));
    act(() => result.current.setSort([]));

    expect(result.current.cursor).toBe('c1');
  });

  it('holds every no-op mutator, including on the filters', () => {
    /*
     * A screen's fetch effect is keyed on the query, so a new-but-equal query object is a second
     * request for the page already on screen — re-selecting the value a `<select>` already shows, or
     * clearing filters that are already clear. Every mutator is covered because the guard used to be
     * written per case and two of them did not have one.
     */
    const { result } = renderHook(() =>
      useListQuery({
        initial: { q: 'north', filters: { status: 'POSTED' }, limit: 25 },
        meta: page(true, 'c1'),
      }),
    );

    act(() => result.current.nextPage());
    const before = result.current.filters;

    act(() => result.current.setFilter('status', 'POSTED'));
    act(() => result.current.setFilters({ status: 'POSTED' }));
    act(() => result.current.setLimit(25));
    act(() => result.current.setFilter('tag', null));

    expect(result.current.cursor).toBe('c1');
    // The same object, not merely an equal one: identity is what a dependency array compares.
    expect(result.current.filters).toBe(before);

    // And a real change still restarts, so the guard has not swallowed the rule it guards.
    act(() => result.current.setFilter('status', 'DRAFT'));
    expect(result.current.cursor).toBeNull();
  });

  it('holds a clear when there is nothing to clear', () => {
    const { result } = renderHook(() => useListQuery({ meta: page(true, 'c1') }));

    act(() => result.current.nextPage());
    act(() => result.current.clearFilters());

    expect(result.current.cursor).toBe('c1');
  });

  it('trims a search before comparing it, as the server would', () => {
    const { result } = renderHook(() => useListQuery({ meta: page(true, 'c1') }));

    act(() => result.current.setSearch('  north  '));

    expect(result.current.q).toBe('north');
    expect(result.current.queryString).toBe('q=north');
  });

  it('removes a filter when it is set to nothing', () => {
    const { result } = renderHook(() => useListQuery({ initial: { filters: { status: 'POSTED' } } }));

    act(() => result.current.setFilter('status', ''));
    expect(result.current.filters).toEqual({});

    act(() => result.current.setFilter('tag', ['A']));
    act(() => result.current.setFilter('tag', null));
    expect(result.current.filters).toEqual({});
  });

  it('clamps a page size the server would reject', () => {
    const { result } = renderHook(() => useListQuery());

    act(() => result.current.setLimit(5000));

    expect(result.current.limit).toBe(200);
  });
});

describe('useListQuery — search, filters and the URL', () => {
  it('lifts the search and every filter, and keeps sort and page size', () => {
    const { result } = renderHook(() =>
      useListQuery({
        initial: {
          q: 'north',
          filters: { status: 'POSTED' },
          sort: [{ key: 'name', direction: 'asc' }],
          limit: 100,
        },
      }),
    );

    act(() => result.current.clearFilters());

    expect(result.current.q).toBe('');
    expect(result.current.filters).toEqual({});
    // Neither of these hides a row, so neither is a filter to lift.
    expect(result.current.sort).toEqual([{ key: 'name', direction: 'asc' }]);
    expect(result.current.limit).toBe(100);
  });

  it('says whether the list is narrowed, which is what the table needs for its empty state', () => {
    const { result } = renderHook(() => useListQuery());

    expect(result.current.filtered).toBe(false);

    act(() => result.current.setFilter('status', 'POSTED'));
    expect(result.current.filtered).toBe(true);

    act(() => result.current.clearFilters());
    act(() => result.current.setSearch('north'));
    expect(result.current.filtered).toBe(true);
  });

  it('puts the cursor in the request and never in the shareable query', () => {
    const { result } = renderHook(() => useListQuery({ initial: { q: 'north' }, meta: page(true, 'c1') }));

    act(() => result.current.nextPage());

    expect(result.current.params.get('cursor')).toBe('c1');
    // Pasting a link with a cursor in it hands the recipient a token that will be rejected.
    expect(result.current.queryString).toBe('q=north');
  });

  it('always states the page size in the request, default or not', () => {
    const { result } = renderHook(() => useListQuery());

    expect(result.current.params.get('limit')).toBe('50');
    expect(result.current.queryString).toBe('');
  });

  it('reports a query change so the address bar can follow, and a page step never', () => {
    const onQueryChange = vi.fn();
    const { result } = renderHook(() => useListQuery({ meta: page(true, 'c1'), onQueryChange }));

    // The first query came from the URL; reporting it back would be a rewrite that changes nothing.
    expect(onQueryChange).not.toHaveBeenCalled();

    act(() => result.current.setSearch('north'));
    expect(onQueryChange).toHaveBeenCalledWith('q=north');

    onQueryChange.mockClear();
    act(() => result.current.nextPage());
    // The cursor is not in the URL, so a step forward leaves it unchanged.
    expect(onQueryChange).not.toHaveBeenCalled();
  });

  it('adopts a query from outside, and ignores one that is the same query', () => {
    const { result } = renderHook(() => useListQuery({ meta: page(true, 'c1') }));

    act(() => result.current.nextPage());
    act(() =>
      result.current.adopt({ q: '', sort: [], filters: {}, limit: 50 }),
    );
    // Identical to what is already in force — an echo of the address bar, not a change.
    expect(result.current.cursor).toBe('c1');

    act(() => result.current.adopt(parseListQuery('q=north')));

    expect(result.current.q).toBe('north');
    expect(result.current.cursor).toBeNull();
  });
});
