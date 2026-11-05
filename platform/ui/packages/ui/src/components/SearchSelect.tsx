'use client';

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { usePlacement } from '../lib/placement';
import type { Tone } from './Badge';
import { CheckIcon } from './icons';
import { ChevronDownIcon, CloseIcon, SearchIcon, WarnTriangleIcon } from './icons-console';

/**
 * `SearchSelect` — entity lookup. Type to search, pick one or several, page through remote
 * results, optionally create what you were looking for.
 *
 * Named for its job, but it implements the **WAI-ARIA 1.2 combobox pattern**: that is the spec
 * its roles, keyboard model and `aria-activedescendant` behaviour are written against.
 *
 * Two things it deliberately does not do:
 *
 *  - **It never fetches.** The caller supplies `loadOptions`, so this file knows nothing about
 *    `catalog` or `identity` and one control serves customers, items and ledger accounts.
 *  - **It never formats.** `figure` and `meta` arrive as strings the caller already ran through
 *    `useFormatters`, so no amount can reach a component that has no display config.
 */

export type SearchSelectOption = {
  /** The entity id. */
  id: string;
  /** Primary text — what the search matched. */
  label: string;
  /** Second line: a code, a place, a status. */
  meta?: string;
  /** Right-aligned and already formatted. A string, never a number. */
  figure?: string;
  icon?: ReactNode;
  tone?: Tone;
  /** Present in the list but not selectable — an inactive item, say. */
  disabled?: boolean;
};

export type SearchSelectLoader = (args: {
  q: string;
  cursor: string | null;
  signal: AbortSignal;
}) => Promise<{ items: SearchSelectOption[]; nextCursor: string | null }>;

type BaseProps = {
  label: string;
  /** Static mode. Provide this or `loadOptions`, not both. */
  options?: readonly SearchSelectOption[];
  /** Async mode. Called with a reset cursor whenever the query changes. */
  loadOptions?: SearchSelectLoader;
  /**
   * The resolved option(s) behind `value`. The control caches everything it renders, but on a
   * first paint — a value loaded from the server whose option was never in a list — it has an
   * id and nothing to label it with. You already hold the entity; passing it is cheaper and
   * more honest than having this component fetch.
   */
  selected?: SearchSelectOption | readonly SearchSelectOption[] | null;
  /** Defaults to 2 in async mode and 0 in static mode — see §5.5 for why they differ. */
  minQueryLength?: number;
  /**
   * Keeps the label as the accessible name but takes it out of the layout — for a toolbar
   * filter, where a stacked label above a control in a row of controls is just noise.
   */
  hideLabel?: boolean;
  /** Lets a caller mirror what was typed into a heading, or lift it into the URL. */
  onQueryChange?: (q: string) => void;
  /** Collapses the chip list past this many, so a filter cannot grow without bound. */
  maxChips?: number;
  placeholder?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  disabled?: boolean;
  clearable?: boolean;
  emptyLabel?: string;
  /** Emits hidden inputs so a plain `<form>` submit carries the id(s). */
  name?: string;
  /** The caller's permission check. Presentation only — the server still decides. */
  canCreate?: boolean;
  onCreate?: (q: string) => Promise<SearchSelectOption | null> | void;
  createLabel?: (q: string) => string;
  /** Accumulation cap across pages. Beyond it the list says so rather than paging forever. */
  maxOptions?: number;
  debounceMs?: number;
};

type SingleProps = BaseProps & {
  multiple?: false;
  value: string | null;
  onChange: (id: string | null, option: SearchSelectOption | null) => void;
};

type MultipleProps = BaseProps & {
  multiple: true;
  value: readonly string[];
  /**
   * `ids` is authoritative; `options` is the same set resolved to everything the control can
   * label, in the order of `ids`. An id whose option this field has never seen is **absent from
   * `options` while still present in `ids`** — the alternative is inventing a label for an
   * entity, which on a filter chip would print a fabricated customer name. Pass `selected` and
   * the two always agree.
   */
  onChange: (ids: string[], options: SearchSelectOption[]) => void;
};

/** Single and multiple are a union, so `value` is never ambiguously typed. */
export type SearchSelectProps = SingleProps | MultipleProps;

/** The API clamps `q` at 200 characters; sending more is a guaranteed 422. */
const MAX_QUERY = 200;

/** The create row's key. Not an entity id, so it can never collide with one. */
const CREATE_ROW = '\u0000create';

const DEFAULT_DEBOUNCE = 250;
const DEFAULT_MAX_OPTIONS = 200;

function matches(option: SearchSelectOption, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return (
    option.label.toLowerCase().includes(needle) ||
    (option.meta?.toLowerCase().includes(needle) ?? false)
  );
}

export function SearchSelect(props: SearchSelectProps) {
  const {
    label,
    options,
    loadOptions,
    selected,
    minQueryLength,
    hideLabel = false,
    onQueryChange,
    maxChips,
    placeholder,
    hint,
    error,
    required = false,
    disabled = false,
    clearable = true,
    emptyLabel = 'No matches',
    name,
    canCreate = false,
    onCreate,
    createLabel = (q) => `Add “${q}”`,
    maxOptions = DEFAULT_MAX_OPTIONS,
    debounceMs = DEFAULT_DEBOUNCE,
  } = props;

  const multiple = props.multiple === true;
  const isAsync = typeof loadOptions === 'function';
  const minQ = minQueryLength ?? (isAsync ? 2 : 0);

  const uid = useId();
  const inputId = `${uid}-input`;
  const listId = `${uid}-list`;
  const hintId = `${uid}-hint`;
  const errorId = `${uid}-error`;

  const anchorRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const [open, setOpen] = useState(false);
  /**
   * What is in the input.
   *
   * Separate from `filterQuery` — the query the list currently reflects — because in multiple
   * mode a commit clears the input so the next name can be typed, while the results have to
   * stay on screen. Sharing one value forced a choice between an input you must clear by hand
   * and a list that empties itself the moment you pick something.
   */
  const [query, setQuery] = useState('');
  const [filterQuery, setFilterQuery] = useState('');
  /*
   * The highlighted row, held by identity rather than by ordinal.
   *
   * It used to be an index, and the auto-page trigger fires precisely when the highlight is on
   * the last row — so appending a page slid a different option under the highlight and Enter
   * committed an entity the user had never looked at. On an invoice that is the wrong customer
   * on a posted document. The ordinal is derived per render instead, where it cannot go stale.
   */
  const [activeRow, setActiveRow] = useState<string | null>(null);
  const [remote, setRemote] = useState<SearchSelectOption[]>([]);
  /*
   * The query `remote` actually answers, as the server answered it.
   *
   * Not derivable from `filterQuery`: that is set on the keystroke, so between the keystroke and
   * the response settling it already names a query nothing has searched yet. The create row has
   * to know whether the *results* have seen this name, which is a different question.
   */
  const [remoteFor, setRemoteFor] = useState<string | null>(null);
  /*
   * The cursor is stored with the query it was minted for. A cursor is bound to its query,
   * filters and sort, and reusing one across a change is a 422 — so paging compares the two
   * rather than trusting that the debounce cleared it in time. Between a keystroke and the
   * debounce firing, a bare cursor still belonged to the previous query (design-system row 22).
   */
  const [cursor, setCursor] = useState<{ q: string; value: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [failed, setFailed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createFailed, setCreateFailed] = useState(false);

  /**
   * The row count at which the last automatic page was requested. An empty page is legal and
   * still carries a cursor, so without this the "walked onto the last row" trigger fires again
   * on the fresh cursor and pages until the server runs out. Auto-paging resumes only once the
   * list has actually grown.
   */
  const autoPagedAt = useRef(-1);

  const selectedProp = useMemo<SearchSelectOption[]>(
    () => (selected == null ? [] : Array.isArray(selected) ? [...selected] : [selected]),
    [selected],
  );

  /*
   * Every option this field has seen, so a selected id can still be labelled after the search
   * that produced it has been replaced.
   *
   * Derived **during render**, not in an effect. Filling a ref from `useEffect` schedules no
   * render, so the paint that should have shown the label had already happened and the field
   * came up blank — the exact first-paint case `selected` exists for. The ref only carries
   * options forward from earlier searches; everything current is merged in here.
   */
  const cache = useRef(new Map<string, SearchSelectOption>());
  const pool = useMemo(() => {
    const merged = new Map(cache.current);
    for (const option of options ?? []) merged.set(option.id, option);
    for (const option of remote) merged.set(option.id, option);
    for (const option of selectedProp) merged.set(option.id, option);
    cache.current = merged;
    return merged;
  }, [options, remote, selectedProp]);

  const selectedIds = useMemo<string[]>(
    () =>
      multiple
        ? [...((props as MultipleProps).value ?? [])]
        : (props as SingleProps).value
          ? [(props as SingleProps).value as string]
          : [],
    [multiple, props],
  );

  // The list belongs to the field above it, so it spans the field's width.
  const placement = usePlacement(anchorRef, open, { matchWidth: true });

  /** Both the clear button and a chip's remove button unmount when used. */
  const focusInput = useCallback(() => inputRef.current?.focus(), []);

  /* ---------------- async search ---------------- */

  const requestId = useRef(0);
  const inFlight = useRef<AbortController | null>(null);

  /*
   * Held in a ref so `search` — and therefore the debounce effect — does not re-identify when
   * the caller passes a fresh arrow function each render. A call site that forgets `useMemo`
   * would otherwise refetch on every parent render, and nothing in the type signature warns
   * them.
   */
  const loaderRef = useRef(loadOptions);
  useEffect(() => {
    loaderRef.current = loadOptions;
  }, [loadOptions]);

  const search = useCallback(
    async (q: string, from: string | null) => {
      const load = loaderRef.current;
      if (!load) return;

      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      const id = ++requestId.current;

      if (from) setLoadingMore(true);
      else setLoading(true);
      setFailed(false);

      try {
        const page = await load({ q: q.slice(0, MAX_QUERY), cursor: from, signal: controller.signal });
        /*
         * Aborting is not sufficient on its own: an aborted request can still settle first, and
         * then the list shows results for a query the user has already moved on from — a wrong
         * answer that looks like a right one. Only the newest request may write state.
         */
        if (id !== requestId.current) return;

        for (const option of page.items) cache.current.set(option.id, option);
        setRemote((prev) => {
          const next = from ? [...prev, ...page.items] : page.items;
          const seen = new Set<string>();
          return next.filter((o) => !seen.has(o.id) && seen.add(o.id)).slice(0, maxOptions);
        });
        // Stamped with the query that produced it, so it can never be replayed under another.
        setCursor(page.nextCursor ? { q: q.trim(), value: page.nextCursor } : null);
        /* Deliberately not set in the `catch`: a failed search has established nothing about
         * whether the name exists, so the create row must stay unoffered. */
        setRemoteFor(q.trim());
      } catch {
        if (id !== requestId.current || controller.signal.aborted) return;
        // "Nothing matched" and "the request failed" are different facts about someone's data.
        setFailed(true);
      } finally {
        if (id === requestId.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [maxOptions],
  );

  const belowMin = filterQuery.trim().length < minQ;

  /* Debounce applies to *typing*. Opening with a query already in hand should not sit on a
   * dead list for a quarter of a second, so the open transition searches immediately. */
  const justOpened = useRef(false);

  useEffect(() => {
    if (!open || !isAsync) return;
    /*
     * Consumed here, before the below-minimum return: "no debounce on open" means opening with
     * a query already in hand. Leaving the flag set through an empty open would make the first
     * character someone types skip the debounce instead.
     */
    const immediate = justOpened.current;
    justOpened.current = false;

    if (belowMin) {
      setRemote([]);
      setCursor(null);
      setRemoteFor(null);
      return;
    }
    if (immediate) {
      pagedFrom.current = null;
      autoPagedAt.current = -1;
      void search(filterQuery, null);
      return;
    }
    const timer = setTimeout(() => {
      pagedFrom.current = null;
      autoPagedAt.current = -1;
      void search(filterQuery, null);
    }, debounceMs);
    return () => clearTimeout(timer);
  }, [filterQuery, open, isAsync, belowMin, debounceMs, search]);

  /*
   * Arms "search immediately" only on a genuine closed → open transition. Setting it on every
   * focus and click left it armed while the field was already open — `setOpen(true)` is then a
   * no-op, so no render, so the effect never consumed it — and the next keystroke skipped the
   * debounce. Clicking to place the caret mid-edit is the most ordinary thing a person does.
   */
  const openList = useCallback(() => {
    setOpen((wasOpen) => {
      if (!wasOpen) justOpened.current = true;
      return true;
    });
  }, []);

  useEffect(() => {
    if (open) return;
    /* Bumping the id as well as aborting: an in-flight response can still settle after the
     * abort, and the guard inside `search` is id-based, so the id is what actually invalidates
     * it. Without this, closing the list still let a late response write into it. */
    inFlight.current?.abort();
    requestId.current += 1;
    setActiveRow(null);
    setFailed(false);
    setCreateFailed(false);
    pagedFrom.current = null;
    autoPagedAt.current = -1;
  }, [open]);

  /*
   * Which cursor has already been asked for. Without it the "walked onto the last row" effect
   * re-fired every time `loadMore`'s identity changed — twice per request — and when the list
   * could not actually grow (at `maxOptions`, or an empty page that still returns a cursor)
   * that became an unbounded request loop rather than the documented "say so and stop".
   */
  const pagedFrom = useRef<string | null>(null);

  /* ---------------- the rows ---------------- */

  /*
   * Every static match, before the cap. Kept separate from `visible` so the cap notice can tell
   * "there are more, you are only seeing some" from "there are exactly this many" — the sliced
   * list alone cannot distinguish the two, and claiming truncation on a complete list tells
   * someone to refine a search that has nothing left to hide.
   */
  const filtered = useMemo(() => {
    if (isAsync) return remote;
    if (belowMin) return [];
    return (options ?? []).filter((option) => matches(option, filterQuery));
  }, [isAsync, remote, options, filterQuery, belowMin]);

  const visible = useMemo(() => filtered.slice(0, maxOptions), [filtered, maxOptions]);

  /*
   * The query the rows on screen actually answer.
   *
   * In async mode that is what the server last replied to — never `filterQuery`, which is set on
   * the keystroke. Comparing `query` against `filterQuery` compared two values that a single
   * `onChange` sets together, so the guard was always true: inside the debounce window `visible`
   * still answered the *previous* query, an existing name looked new, and the panel offered to
   * create a duplicate master at typing speed. In static mode the filter is synchronous, so the
   * list does answer `filterQuery` — except below the minimum, where nothing has been searched
   * at all and there is therefore no basis for calling a name new.
   */
  const resultsFor = isAsync ? remoteFor : belowMin ? null : filterQuery.trim();

  const showCreate =
    canCreate &&
    typeof onCreate === 'function' &&
    query.trim().length > 0 &&
    !loading &&
    resultsFor === query.trim() &&
    !visible.some((option) => option.label.toLowerCase() === query.trim().toLowerCase());

  /** Row keys in render order. `CREATE_ROW` is a sentinel, not an entity id. */
  const rows = useMemo(
    () => [...visible.map((option) => option.id), ...(showCreate ? [CREATE_ROW] : [])],
    [visible, showCreate],
  );

  const rowCount = rows.length;
  const activeIndex = activeRow === null ? -1 : rows.indexOf(activeRow);
  const createIndex = showCreate ? visible.length : -1;
  /** The accumulation limit is reached, so nothing may be added — paging stops here. */
  const atCap = visible.length >= maxOptions;
  /*
   * …and something was actually withheld. A final page that fills the cap exactly, or a static
   * list exactly `maxOptions` long, is complete — so `atCap` still stops paging, but the notice
   * stays silent rather than sending the reader off to refine a search that is already whole.
   */
  const showCapNotice = atCap && (isAsync ? cursor !== null : filtered.length > maxOptions);

  // A field disabled while its list is open must not keep the list open.
  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  // Navigating away mid-search should not leave the connection open.
  useEffect(() => () => inFlight.current?.abort(), []);

  const loadMore = useCallback(() => {
    if (!cursor || loading || loadingMore) return;
    // A cursor minted for a different query is a 422 waiting to happen.
    if (cursor.q !== filterQuery.trim()) return;
    if (atCap) return;
    if (pagedFrom.current === cursor.value) return;
    pagedFrom.current = cursor.value;
    void search(filterQuery, cursor.value);
  }, [cursor, loading, loadingMore, filterQuery, search, atCap]);

  // Pointer paging. Keyboard paging happens by walking to the end of the list, so there is no
  // focusable control in here that Tab would have to reach.
  useEffect(() => {
    const node = sentinelRef.current;
    if (!open || !node || !cursor || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadMore();
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [open, cursor, loadMore]);


  /* Ordered by how much the user needs to hear it. A failed create outranks everything else on
   * the panel — it is the one state where an action they took did not happen. */
  const announcement = createFailed
    ? `Couldn’t create “${query.trim()}”. Try again.`
    : failed
      ? 'Search failed'
      : loading
        ? 'Searching'
        : belowMin
          ? `Type at least ${minQ} characters to search`
          : rowCount === 0
            ? emptyLabel
            : `${visible.length} ${visible.length === 1 ? 'result' : 'results'}${cursor ? ', more available' : ''}`;

  /* ---------------- selection ---------------- */

  const commit = useCallback(
    (option: SearchSelectOption) => {
      // The panel is portalled, so disabling the field leaves it on screen and clickable.
      if (disabled || option.disabled) return;
      cache.current.set(option.id, option);

      if (multiple) {
        const current = [...((props as MultipleProps).value ?? [])];
        const next = current.includes(option.id)
          ? current.filter((id) => id !== option.id)
          : [...current, option.id];
        (props as MultipleProps).onChange(
          next,
          next.map((id) => cache.current.get(id)).filter((o): o is SearchSelectOption => Boolean(o)),
        );
        /*
         * The input clears so the next name can be typed straight away; `filterQuery` does not,
         * so the list you were picking from is still there. Clearing both emptied the panel that
         * was deliberately left open, and clearing neither made you select-all and retype.
         */
        setQuery('');
        /* Every other place the input empties reports it — the keystroke path, Escape and
         * `clearAll`. Staying silent here left a caller mirroring the query into a heading or the
         * URL showing a search term that is no longer in the field. */
        onQueryChange?.('');
      } else {
        (props as SingleProps).onChange(option.id, option);
        setQuery('');
        // Single mode closes the list, so retaining the filter has no purpose — and reopening
        // then showed a filtered list with an empty search box and nothing explaining why.
        setFilterQuery('');
        onQueryChange?.('');
        setOpen(false);
      }
    },
    [multiple, props, disabled, onQueryChange],
  );

  const clearAll = useCallback(() => {
    if (disabled) return;
    if (multiple) (props as MultipleProps).onChange([], []);
    else (props as SingleProps).onChange(null, null);
    setQuery('');
    setFilterQuery('');
    onQueryChange?.('');
    // The clear button unmounts on activation, so without this focus lands on <body> and the
    // next Tab restarts from the top of the page.
    focusInput();
  }, [disabled, multiple, props, onQueryChange]);

  const runCreate = useCallback(async () => {
    // Two guards on one line of intent: a disabled field creates nothing, and a second Enter
    // while the first is still in flight must not create a second master record.
    if (!onCreate || disabled || creating) return;
    setCreating(true);
    setCreateFailed(false);
    try {
      const created = await onCreate(query.trim());
      if (created) commit(created);
      else setOpen(false);
    } catch {
      /* A failed *write* with no state at all is worse than a failed search: the spinner stops
       * and the user is told nothing, and the rejection escapes as an unhandled promise. */
      setCreateFailed(true);
    } finally {
      setCreating(false);
    }
  }, [onCreate, disabled, creating, query, commit]);

  const activate = useCallback(
    (index: number) => {
      if (index === createIndex) {
        void runCreate();
        return;
      }
      const option = visible[index];
      if (option) commit(option);
    },
    [createIndex, visible, commit, runCreate],
  );

  /* ---------------- keyboard ---------------- */

  const move = useCallback(
    (delta: number) => {
      if (rowCount === 0) return;
      const from = activeRow === null ? (delta > 0 ? -1 : 0) : rows.indexOf(activeRow);
      const next = from + delta;
      const wrapped = next < 0 ? rowCount - 1 : next >= rowCount ? 0 : next;
      setActiveRow(rows[wrapped] ?? null);
    },
    [rowCount, rows, activeRow],
  );

  // Walking onto the last row pages the next page in, which is what keeps paging reachable
  // without a focusable button inside a list that Tab is supposed to dismiss.
  useEffect(() => {
    if (!open || atCap) return;
    if (!cursor || activeIndex < 0 || activeIndex !== rowCount - 1) return;
    if (autoPagedAt.current === rowCount) return;
    autoPagedAt.current = rowCount;
    loadMore();
  }, [open, atCap, cursor, activeIndex, rowCount, loadMore]);

  /*
   * The highlight moves by `aria-activedescendant`, which moves no scroll position — so on a
   * list taller than its own box, arrowing down walked the highlight straight out of view and
   * left the user pressing a key with nothing visibly happening. `block: 'nearest'` keeps the
   * list still while the highlight is already on screen.
   */
  useEffect(() => {
    if (!open || activeIndex < 0) return;
    const row = document.getElementById(`${uid}-row-${activeIndex}`);
    // jsdom implements no scrolling, and a missing row is not worth throwing over.
    if (typeof row?.scrollIntoView === 'function') row.scrollIntoView({ block: 'nearest' });
  }, [open, activeIndex, uid]);

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (!open) {
          openList();
          return;
        }
        move(1);
        return;
      case 'ArrowUp':
        event.preventDefault();
        if (!open) {
          openList();
          return;
        }
        move(-1);
        return;
      case 'Home':
        if (!open) return;
        event.preventDefault();
        setActiveRow(rows[0] ?? null);
        return;
      case 'End':
        if (!open) return;
        event.preventDefault();
        setActiveRow(rows[rowCount - 1] ?? null);
        return;
      case 'PageDown':
        if (!open) return;
        event.preventDefault();
        move(5);
        return;
      case 'PageUp':
        if (!open) return;
        event.preventDefault();
        move(-5);
        return;
      case 'Enter':
        if (!open || activeIndex < 0) return;
        event.preventDefault();
        activate(activeIndex);
        return;
      case 'Escape':
        // Consume Escape only when this control has something to dismiss. Otherwise a containing
        // dialog must be able to handle it.
        if (!open && !query) return;
        event.preventDefault();
        // First press closes. A second, with the list already shut, clears what you typed.
        if (open) setOpen(false);
        else if (query) {
          setQuery('');
          setFilterQuery('');
          onQueryChange?.('');
        }
        return;
      case 'Tab':
        // Tab leaves the field and commits nothing. Closing here rather than on blur means the
        // list cannot outlive the focus that owns it.
        if (open) setOpen(false);
        return;
      case 'Backspace':
        if (multiple && query === '' && selectedIds.length > 0) {
          const last = pool.get(selectedIds[selectedIds.length - 1] as string);
          if (last) commit(last);
        }
        return;
      default:
        return;
    }
  }

  /* ---------------- dismissal ---------------- */

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      // The list is portalled, so "inside" is two subtrees, not one.
      if (anchorRef.current?.contains(target) || listRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open]);

  /* ---------------- render ---------------- */

  const selectedOptions = selectedIds
    .map((id) => pool.get(id))
    .filter((o): o is SearchSelectOption => Boolean(o));

  const shownChips = maxChips ? selectedOptions.slice(0, maxChips) : selectedOptions;
  const hiddenChips = selectedOptions.length - shownChips.length;

  const singleLabel = multiple ? '' : (selectedOptions[0]?.label ?? '');
  const inputValue = multiple ? query : open ? query : singleLabel;
  const hasValue = selectedIds.length > 0;
  // Only one of the two paragraphs is ever rendered, so only that id may be referenced —
  // a dangling idref is dropped silently by assistive technology.
  const describedBy = error ? errorId : hint ? hintId : undefined;

  const list = open && placement ? (
    <div
      ref={listRef}
      className="pms-search-select__panel"
      data-flipped={placement.flipped ? 'true' : undefined}
      style={placement.style}
    >
      {/* Options only, so `role="listbox"` stays valid; status lines live beside it. */}
      <div
        id={listId}
        role="listbox"
        className="pms-search-select__options"
        /* Not `label`: naming the list the same as the field makes `getByLabelText(label)`
           match two elements, and announces the same word twice on entry. */
        aria-label={`${label} results`}
        aria-multiselectable={multiple ? true : undefined}
      >
        {visible.map((option, index) => {
          const isSelected = selectedIds.includes(option.id);
          return (
            <div
              key={option.id}
              id={`${uid}-row-${index}`}
              role="option"
              className="pms-search-select__option"
              aria-selected={isSelected}
              aria-disabled={option.disabled ? true : undefined}
              data-active={index === activeIndex ? 'true' : undefined}
              data-tone={option.tone}
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => commit(option)}
              onPointerEnter={() => setActiveRow(option.id)}
            >
              <span className="pms-search-select__mark" aria-hidden="true">
                {isSelected ? <CheckIcon size={16} /> : option.icon}
              </span>
              <span className="pms-search-select__text">
                <span className="pms-search-select__label">{option.label}</span>
                {option.meta ? (
                  <span className="pms-search-select__meta">{option.meta}</span>
                ) : null}
              </span>
              {option.figure ? (
                <span className="pms-search-select__figure pms-figure">{option.figure}</span>
              ) : null}
            </div>
          );
        })}

        {showCreate ? (
          <div
            id={`${uid}-row-${createIndex}`}
            role="option"
            aria-selected={false}
            className="pms-search-select__create"
            data-active={activeIndex === createIndex ? 'true' : undefined}
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => void runCreate()}
          >
            <span className="pms-search-select__mark" aria-hidden="true">
              {creating ? <span className="pms-btn__spinner" /> : <SearchIcon size={16} />}
            </span>
            <span className="pms-search-select__label">{createLabel(query.trim())}</span>
          </div>
        ) : null}
      </div>

      {/*
        The live region on the field is what announces these. Hiding them here stops the same
        sentence being read twice, and stops it matching twice in a caller's tests.
      */}
      {createFailed ? (
        /* First, and ahead of every other status line: a failed *write* is the most important
           thing on this panel. The create row stays rendered underneath, so "try again" is the
           row the user already knows how to press. */
        <p className="pms-search-select__status" data-tone="danger" aria-hidden="true">
          <WarnTriangleIcon size={15} />
          <span>Couldn’t create “{query.trim()}”. Try again.</span>
        </p>
      ) : null}

      {belowMin ? (
        <p className="pms-search-select__status" aria-hidden="true">
          Type at least {minQ} characters to search
        </p>
      ) : failed ? (
        /* Not hidden, unlike the other status lines: this one contains the retry control, and
           hiding the paragraph takes the button out of the accessibility tree with it. */
        <p className="pms-search-select__status" data-tone="danger">
          <WarnTriangleIcon size={15} />
          <span>Couldn’t load results.</span>
          <button
            type="button"
            className="pms-search-select__retry"
            tabIndex={-1}
            onClick={() => void search(filterQuery, null)}
          >
            Try again
          </button>
        </p>
      ) : loading ? (
        <p className="pms-search-select__status" aria-hidden="true">Searching…</p>
      ) : rowCount === 0 ? (
        <p className="pms-search-select__status" aria-hidden="true">{emptyLabel}</p>
      ) : null}

      {showCapNotice ? (
        <p className="pms-search-select__status" aria-hidden="true">
          Showing the first {maxOptions}. Refine your search to narrow it down.
        </p>
      ) : null}

      {cursor && !atCap ? (
        <div ref={sentinelRef} className="pms-search-select__sentinel">
          {loadingMore ? (
            <span className="pms-search-select__status" aria-hidden="true">Loading more…</span>
          ) : (
            /*
             * Pointer affordance only — `tabIndex={-1}` because Tab is defined to close the
             * list, so a tab stop in here would be a control you can never reach. Keyboard
             * users page by walking onto the last row.
             */
            <button
              type="button"
              className="pms-search-select__more"
              tabIndex={-1}
              onClick={loadMore}
            >
              Load more
            </button>
          )}
        </div>
      ) : null}
    </div>
  ) : null;

  return (
    <div className="pms-field pms-search-select" data-open={open ? 'true' : undefined}>
      {/*
        No "Optional" marker: on a lookup it is noise, and `required` already carries the
        semantic. `hideLabel` keeps the label as the accessible name and drops it from the
        layout, for a filter sitting in a row of controls.
      */}
      {hideLabel ? (
        /* The label carries the class, not a wrapper: nothing else lives in this row, so hiding
         * one element is the whole job — and it keeps the shape identical to `Select`'s. */
        <label className="pms-label pms-visually-hidden" htmlFor={inputId}>
          {label}
        </label>
      ) : (
        <div className="pms-field__row">
          <label className="pms-label" htmlFor={inputId}>
            {label}
          </label>
        </div>
      )}

      <div
        ref={anchorRef}
        className="pms-search-select__control"
        data-invalid={error ? 'true' : undefined}
        data-disabled={disabled ? 'true' : undefined}
      >
        {multiple
          ? shownChips.map((option) => (
              <span key={option.id} className="pms-search-select__chip">
                <span className="pms-search-select__chip-label">{option.label}</span>
                <button
                  type="button"
                  className="pms-search-select__chip-remove"
                  aria-label={`Remove ${option.label}`}
                  disabled={disabled}
                  onClick={() => commit(option)}
                >
                  <CloseIcon size={13} />
                </button>
              </span>
            ))
          : null}
        {hiddenChips > 0 ? (
          <span className="pms-search-select__chip-count">+{hiddenChips} more</span>
        ) : null}

        <input
          id={inputId}
          className="pms-search-select__input"
          type="text"
          role="combobox"
          autoComplete="off"
          spellCheck={false}
          /* `list`, not `both`: inline autocompletion fights entity search, where what you
             type rarely prefixes what you want. */
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          aria-activedescendant={open && activeIndex >= 0 ? `${uid}-row-${activeIndex}` : undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          aria-required={required || undefined}
          placeholder={placeholder}
          disabled={disabled}
          value={inputValue}
          maxLength={MAX_QUERY}
          onChange={(event) => {
            // Clamped in state, not only on the way out: a 250-character paste otherwise left
            // 250 characters visible in a field that will only ever search the first 200.
            const next = event.target.value.slice(0, MAX_QUERY);
            setQuery(next);
            setFilterQuery(next);
            onQueryChange?.(next);
            // A failure belongs to the query that produced it, not to the next one.
            setFailed(false);
            setCreateFailed(false);
            setActiveRow(null);
            /*
             * A *new* query invalidates the cursor immediately, rather than when the debounce
             * happens to run — otherwise paging in that window sends the old cursor.
             *
             * The same query does not. Multiple mode clears the input on a commit and keeps the
             * results, so the identical query can arrive again in one change event (a paste, or a
             * one-character search) — and then `filterQuery` never changes, the search effect never
             * re-runs, and a cursor dropped here is never minted again. The rows stayed on screen
             * with no way left to page past them.
             */
            if (cursor === null || cursor.q !== next.trim()) {
              setCursor(null);
              pagedFrom.current = null;
              autoPagedAt.current = -1;
            }
            if (!open) openList();
          }}
          onKeyDown={onKeyDown}
          onFocus={openList}
          onClick={openList}
        />

        {clearable && hasValue && !disabled ? (
          <button
            type="button"
            className="pms-search-select__clear"
            aria-label={`Clear ${label}`}
            onClick={clearAll}
          >
            <CloseIcon size={15} />
          </button>
        ) : null}

        <span className="pms-search-select__chevron" aria-hidden="true">
          <ChevronDownIcon size={16} />
        </span>
      </div>

      {error ? (
        <p className="pms-error" id={errorId}>
          <WarnTriangleIcon size={14} />
          {error}
        </p>
      ) : hint ? (
        <p className="pms-hint" id={hintId}>
          {hint}
        </p>
      ) : null}

      {/* A list that changes silently does not exist to a screen reader. */}
      <span className="pms-visually-hidden" role="status" aria-live="polite">
        {open ? announcement : ''}
      </span>

      {/* `disabled` on the hidden inputs, because native `disabled` excludes a control from
          submission — otherwise a disabled field still posts the value it was disabled to
          withhold. */}
      {name
        ? selectedIds.map((id) => (
            <input key={id} type="hidden" name={name} value={id} disabled={disabled} />
          ))
        : null}

      {list && typeof document !== 'undefined' ? createPortal(list, document.body) : null}
    </div>
  );
}
