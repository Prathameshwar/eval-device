'use client';

/**
 * Framework-independent state for search, filters, sorting and cursor pagination.
 * Consumers own fetching and translate these conventional query parameters to their API.
 * Changing the query discards old cursors; previous-page navigation uses a cursor stack.
 * Shareable query strings omit cursors, which may be bound to a particular session.
 */
import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import type { Sort, SortDirection } from './table';

/** Default UI query bounds. Consumers must also respect their endpoint's limits. */
export const LIMIT_DEFAULT = 50;
export const LIMIT_MAX = 200;
export const SEARCH_MAX = 200;
/**
 * The shortest `q` worth sending. Endpoints set their own minimum to keep a one-character search
 * from scanning a whole index (§2.3); two is the platform default, and a screen whose endpoint asks
 * for more passes its own.
 */
export const SEARCH_MIN = 2;
/** `in` lists are capped server-side; a picker must not offer past this. */
export const FILTER_VALUES_MAX = 100;
/** At most three client-selected sort fields; the server appends `id` (§2.4). */
export const SORT_FIELDS_MAX = 3;

/**
 * The four reserved common parameter names (§2). A resource cannot have a filter called any of
 * these, so they are never read as one — including when a screen names one in `filterKeys` by
 * mistake, which would otherwise smuggle a cursor into the query as a filter and put it back in
 * the shareable URL.
 */
const RESERVED = new Set(['limit', 'cursor', 'q', 'sort']);

/**
 * One filter's value. A list of values is the `in` case, sent as a repeated parameter.
 *
 * There is no operator here, deliberately: filters are resource-specific typed parameters —
 * `status`, `created_from`, `created_to` — and there is no arbitrary field/operator query language
 * to build (§2.2). A range is two named parameters, not an operator on one.
 */
export type FilterValue = string | readonly string[];

export type ListFilters = Readonly<Record<string, FilterValue>>;

/** The `page` object of a list response (§3). No total, by design. */
export type PageMeta = {
  limit: number;
  has_more: boolean;
  next_cursor: string | null;
};

export type ListQuery = {
  /** The search text in force, trimmed. Empty means no search. */
  q: string;
  sort: readonly Sort[];
  filters: ListFilters;
  limit: number;
};

export function clampLimit(limit: number): number {
  if (!Number.isFinite(limit)) return LIMIT_DEFAULT;
  return Math.min(Math.max(1, Math.trunc(limit)), LIMIT_MAX);
}

/** `[{key: 'created_at', direction: 'desc'}, …]` → `-created_at,name` (§2.4). */
export function serializeSort(sort: readonly Sort[]): string {
  return sort
    .slice(0, SORT_FIELDS_MAX)
    .map((entry) => (entry.direction === 'desc' ? `-${entry.key}` : entry.key))
    .join(',');
}

export function parseSort(value: string | null | undefined): Sort[] {
  if (!value) return [];
  return value
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part !== '')
    .slice(0, SORT_FIELDS_MAX)
    .map((part) => {
      const direction: SortDirection = part.startsWith('-') ? 'desc' : 'asc';
      return { key: part.startsWith('-') ? part.slice(1) : part, direction };
    });
}

/** Whether a filter value is worth sending. An empty string or an empty list is not a filter. */
function isSet(value: FilterValue): boolean {
  return Array.isArray(value) ? value.length > 0 : value !== '';
}

type ToParams = {
  query: ListQuery;
  cursor?: string | null;
  /** Include `limit` even at its default — the request does, a shareable URL need not. */
  includeDefaultLimit?: boolean;
};

function toParams({ query, cursor = null, includeDefaultLimit = false }: ToParams): URLSearchParams {
  const params = new URLSearchParams();

  if (query.limit !== LIMIT_DEFAULT || includeDefaultLimit) {
    params.set('limit', String(clampLimit(query.limit)));
  }
  if (query.q !== '') params.set('q', query.q.slice(0, SEARCH_MAX));
  if (query.sort.length > 0) params.set('sort', serializeSort(query.sort));

  // Sorted by name so the same query always produces the same string — which is what makes it
  // usable as a cache key and stops a URL rewrite fighting itself.
  for (const key of Object.keys(query.filters).sort()) {
    const value = query.filters[key];
    if (value === undefined || !isSet(value) || RESERVED.has(key)) continue;
    // An `in` list goes out as a repeated parameter rather than a comma-joined one: a value that
    // legitimately contains a comma — a name, a reference — must survive the round trip.
    if (Array.isArray(value)) for (const entry of value) params.append(key, entry);
    else params.set(key, value as string);
  }

  if (cursor !== null) params.set('cursor', cursor);
  return params;
}

/** The shareable query string for a state: no cursor, and no `limit` when it is the default. */
export function listQueryString(query: ListQuery): string {
  return toParams({ query }).toString();
}

type ParseOptions = {
  /**
   * The filter parameter names this screen accepts. Anything else in the URL is dropped rather
   * than forwarded — an unknown filter is a 422 from the server (§2.2), and a link with a typo in
   * it should still open the list.
   */
  filterKeys?: readonly string[];
};

/**
 * Reads a query out of a URL — `useSearchParams().toString()`, a `?…` string, or a `URLSearchParams`.
 * The cursor is ignored even when present, for the reason in this module's header.
 */
export function parseListQuery(
  search: string | URLSearchParams,
  { filterKeys = [] }: ParseOptions = {},
): ListQuery {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search;

  const filters: Record<string, FilterValue> = {};
  for (const key of filterKeys) {
    if (RESERVED.has(key)) continue;
    const values = params.getAll(key).filter((value) => value !== '');
    if (values.length === 0) continue;
    filters[key] = values.length === 1 ? (values[0] as string) : values;
  }

  const limit = params.get('limit');
  return {
    q: (params.get('q') ?? '').trim().slice(0, SEARCH_MAX),
    sort: parseSort(params.get('sort')),
    filters,
    limit: limit === null ? LIMIT_DEFAULT : clampLimit(Number(limit)),
  };
}

/* ---------- the hook ---------- */

type State = {
  query: ListQuery;
  /**
   * The cursor each visited page was fetched with. `null` at the head, because the first page has
   * no cursor — so the stack's length is the number of pages walked.
   */
  stack: readonly (string | null)[];
  index: number;
};

type Action =
  | { kind: 'search'; q: string }
  | { kind: 'sort'; sort: readonly Sort[] }
  | { kind: 'filter'; key: string; value: FilterValue | null }
  | { kind: 'filters'; filters: ListFilters }
  | { kind: 'clear' }
  | { kind: 'limit'; limit: number }
  | { kind: 'next'; cursor: string }
  | { kind: 'previous' }
  | { kind: 'restart' }
  | { kind: 'adopt'; query: ListQuery };

/** The head of a fresh walk. Every query change goes through here — see rule 1 in the header. */
function restarted(query: ListQuery): State {
  return { query, stack: [null], index: 0 };
}

/**
 * Apply a query: restart the walk, but only when the query actually changed.
 *
 * Both halves matter. Restarting is rule 1 — a cursor does not survive a query change. Returning the
 * *same state object* when nothing changed is what keeps a re-selected filter value, a re-typed
 * search term or a re-chosen page size from costing a request: the screen's fetch effect is keyed on
 * the query, so a new-but-equal object is a second round trip for the page already on screen.
 *
 * Compared through `listQueryString`, which normalizes key order and drops what would not be sent —
 * one comparison for every mutator, rather than a hand-written guard per case that two of them were
 * missing.
 */
function applied(state: State, query: ListQuery): State {
  return listQueryString(query) === listQueryString(state.query) ? state : restarted(query);
}

function reduce(state: State, action: Action): State {
  switch (action.kind) {
    case 'search':
      return applied(state, { ...state.query, q: action.q.trim().slice(0, SEARCH_MAX) });
    case 'sort':
      return applied(state, { ...state.query, sort: action.sort.slice(0, SORT_FIELDS_MAX) });
    case 'filter': {
      const next = { ...state.query.filters };
      if (action.value === null || !isSet(action.value)) delete next[action.key];
      else next[action.key] = action.value;
      return applied(state, { ...state.query, filters: next });
    }
    case 'filters':
      return applied(state, { ...state.query, filters: action.filters });
    case 'clear':
      return applied(state, { ...state.query, q: '', filters: {} });
    // The page size is part of what a cursor is signed over, so this restarts the walk too.
    case 'limit':
      return applied(state, { ...state.query, limit: clampLimit(action.limit) });
    case 'next':
      return {
        ...state,
        // Anything ahead of the current page is dropped: after a step back and a step forward the
        // cursor may differ, and a stale one further up the stack would be used as if it were live.
        stack: [...state.stack.slice(0, state.index + 1), action.cursor],
        index: state.index + 1,
      };
    case 'previous':
      return state.index === 0 ? state : { ...state, index: state.index - 1 };
    case 'restart':
      return state.index === 0 && state.stack.length === 1 ? state : restarted(state.query);
    // A query that arrived from outside — the address bar, a saved view. The comparison in `applied`
    // is what stops an unchanged URL echoing back and restarting the walk on every render.
    case 'adopt':
      return applied(state, action.query);
  }
}

export type UseListQueryOptions = {
  /** The starting query — usually `parseListQuery(useSearchParams())`. */
  initial?: Partial<ListQuery>;
  /**
   * The `page` object of the response currently on screen. It is the only source of "is there a
   * next page": a keyset list has no count to derive it from.
   */
  meta?: PageMeta | null;
  /**
   * Called with the shareable query string whenever the query changes — wire it to
   * `router.replace` to keep the address bar honest. Never called for a page step, because the
   * cursor is not in the URL and the URL would not change.
   */
  onQueryChange?: (queryString: string) => void;
};

export type ListQueryHandle = {
  q: string;
  sort: readonly Sort[];
  filters: ListFilters;
  limit: number;
  /** The cursor for the page in hand, or `null` on the first page. */
  cursor: string | null;
  /** The request's parameters, cursor and limit included. */
  params: URLSearchParams;
  /** The shareable query string — no cursor. */
  queryString: string;
  /** True when a search or any filter is narrowing the list — what `DataTable.filtered` wants. */
  filtered: boolean;
  page: {
    /** 0-based position in the walk. */
    index: number;
    /** 1-based index of this page's first row in the walk so far. */
    from: number;
    hasPrevious: boolean;
    hasNext: boolean;
  };
  setSearch: (q: string) => void;
  setSort: (sort: readonly Sort[]) => void;
  setFilter: (key: string, value: FilterValue | null) => void;
  setFilters: (filters: ListFilters) => void;
  /** Lifts the search and every filter. Sort and page size are not filters and are kept. */
  clearFilters: () => void;
  setLimit: (limit: number) => void;
  nextPage: () => void;
  previousPage: () => void;
  /**
   * Back to the first page, same query. This is the recovery for a rejected cursor — expired,
   * unknown version, or invalidated by an authority change — all of which arrive as a 422 naming
   * `cursor` (§2.1). The rows are still reachable; only the position was lost.
   */
  restart: () => void;
  /** Adopts a query from outside — the address bar changed, a saved view was applied. */
  adopt: (query: ListQuery) => void;
};

export function useListQuery({
  initial,
  meta = null,
  onQueryChange,
}: UseListQueryOptions = {}): ListQueryHandle {
  const [state, dispatch] = useReducer(
    reduce,
    initial,
    (start): State =>
      restarted({
        q: (start?.q ?? '').trim(),
        sort: start?.sort ?? [],
        filters: start?.filters ?? {},
        limit: clampLimit(start?.limit ?? LIMIT_DEFAULT),
      }),
  );

  const queryString = useMemo(() => listQueryString(state.query), [state.query]);

  /* Held in a ref, and reported from an effect keyed on the string alone: a router callback is a
   * fresh closure on every render, and this must fire when the query changes rather than when the
   * caller re-renders. The first query is not reported — it came from the URL. */
  const report = useRef(onQueryChange);
  useEffect(() => {
    report.current = onQueryChange;
  });
  const reported = useRef(queryString);
  useEffect(() => {
    if (queryString === reported.current) return;
    reported.current = queryString;
    report.current?.(queryString);
  }, [queryString]);

  const cursor = state.stack[state.index] ?? null;

  const params = useMemo(
    () => toParams({ query: state.query, cursor, includeDefaultLimit: true }),
    [state.query, cursor],
  );

  const nextCursor = meta?.has_more === true ? meta.next_cursor : null;

  const nextPage = useCallback(() => {
    if (nextCursor === null) return;
    dispatch({ kind: 'next', cursor: nextCursor });
  }, [nextCursor]);

  return {
    q: state.query.q,
    sort: state.query.sort,
    filters: state.query.filters,
    limit: state.query.limit,
    cursor,
    params,
    queryString,
    filtered: state.query.q !== '' || Object.keys(state.query.filters).length > 0,
    page: {
      index: state.index,
      from: state.index * state.query.limit + 1,
      hasPrevious: state.index > 0,
      hasNext: nextCursor !== null,
    },
    setSearch: useCallback((q: string) => dispatch({ kind: 'search', q }), []),
    setSort: useCallback((sort: readonly Sort[]) => dispatch({ kind: 'sort', sort }), []),
    setFilter: useCallback(
      (key: string, value: FilterValue | null) => dispatch({ kind: 'filter', key, value }),
      [],
    ),
    setFilters: useCallback((filters: ListFilters) => dispatch({ kind: 'filters', filters }), []),
    clearFilters: useCallback(() => dispatch({ kind: 'clear' }), []),
    setLimit: useCallback((limit: number) => dispatch({ kind: 'limit', limit }), []),
    nextPage,
    previousPage: useCallback(() => dispatch({ kind: 'previous' }), []),
    restart: useCallback(() => dispatch({ kind: 'restart' }), []),
    adopt: useCallback((query: ListQuery) => dispatch({ kind: 'adopt', query }), []),
  };
}
