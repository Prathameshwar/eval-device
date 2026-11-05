'use client';

import { useEffect, useRef, useState } from 'react';
import { SEARCH_MAX, SEARCH_MIN } from '../lib/list-query';
import { TextField } from './TextField';
import { CloseIcon, SearchIcon } from './icons-console';

export type TableSearchProps = {
  /** The query the list is actually filtered by — not what is currently typed. */
  value: string;
  /**
   * The query to apply, already trimmed, debounced. `''` means "no search".
   *
   * Nothing between one character and `minLength` is ever reported: a short `q` is a 422 from the
   * server, and turning every first keystroke into a rejected request is the worst of both.
   */
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
  /** What this list searches, in the reader's words — "number, customer or reference". */
  hint?: string;
  minLength?: number;
  maxLength?: number;
  /** Quiet time before the query is applied, in ms. */
  delay?: number;
  /** A search is in flight. The field stays operable — a reader may keep refining. */
  busy?: boolean;
};

/**
 * The table's search box.
 *
 * Search here is the server's `q`: exact-or-prefix over a resource's own indexed fields, never a
 * client-side filter of the page in hand. That distinction is the whole reason this is debounced
 * and bounded rather than filtering as you type — the rows on screen are one page of many, so
 * narrowing them locally would quietly hide matches on every other page.
 */
export function TableSearch({
  value,
  onChange,
  label = 'Search',
  placeholder = 'Search…',
  hint,
  minLength = SEARCH_MIN,
  maxLength = SEARCH_MAX,
  delay = 300,
  busy = false,
}: TableSearchProps) {
  const [draft, setDraft] = useState(value);

  /*
   * The last query this control reported. It is what lets the field tell its own echo from a real
   * change: the parent re-renders with the value we just sent, which must not reset the input, but
   * a reset from elsewhere — "Clear filters", a rejected cursor, a URL change — must adopt it.
   */
  const applied = useRef(value);

  /* Held in a ref so the debounce below does not restart every time the parent re-renders with a
   * fresh inline callback — which would be every render, on most screens. */
  const report = useRef(onChange);
  useEffect(() => {
    report.current = onChange;
  });

  useEffect(() => {
    if (value !== applied.current) {
      applied.current = value;
      setDraft(value);
    }
  }, [value]);

  const trimmed = draft.trim();
  const tooShort = trimmed !== '' && trimmed.length < minLength;

  useEffect(() => {
    if (trimmed === applied.current || tooShort) return;

    const timer = setTimeout(() => {
      // Re-checked inside the timer: Enter may have already flushed this exact query, and firing
      // again would cost the list a second round trip for no change.
      if (trimmed === applied.current) return;
      applied.current = trimmed;
      report.current(trimmed);
    }, delay);

    return () => clearTimeout(timer);
  }, [trimmed, tooShort, delay]);

  function flush(next: string) {
    if (next === applied.current) return;
    applied.current = next;
    report.current(next);
  }

  return (
    <div className="pms-table-search">
      <TextField
        type="search"
        label={label}
        placeholder={placeholder}
        value={draft}
        maxLength={maxLength}
        autoComplete="off"
        spellCheck={false}
        aria-busy={busy || undefined}
        hint={
          tooShort
            ? `Type at least ${minLength} characters to search.`
            : hint
        }
        leading={<SearchIcon size={14} />}
        /* `type="search"` gets the browser's own clear affordance on some engines and none on
           others, so this button is always drawn rather than relying on it. Same trailing hook as
           the password toggle — a control inside an input already has a home in the design system. */
        trailing={
          draft === '' ? null : (
            <button
              type="button"
              className="pms-input__toggle"
              aria-label="Clear search"
              title="Clear search"
              onClick={() => {
                setDraft('');
                flush('');
              }}
            >
              <CloseIcon size={14} />
            </button>
          )
        }
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            // A reader who presses Enter has finished typing; waiting out the debounce after an
            // explicit submit reads as a control that ignored them.
            event.preventDefault();
            if (!tooShort) flush(trimmed);
            return;
          }
          if (event.key === 'Escape' && draft !== '') {
            // Escape clears the search, not the focus — the next thing wanted is another query.
            event.preventDefault();
            setDraft('');
            flush('');
          }
        }}
      />
    </div>
  );
}
