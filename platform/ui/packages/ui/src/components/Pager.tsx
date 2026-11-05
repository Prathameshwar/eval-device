'use client';

import { useFormatters } from '../lib/display-config';
import { LIMIT_MAX } from '../lib/list-query';
import { pluralNoun, pluralOf } from '../lib/text';
import { Select } from './Select';
import { ChevronRightIcon } from './icons-console';
import { ChevronLeftIcon } from './icons-table';
import { IconButton } from './IconButton';

/** The page sizes offered by default. The last one is the server's ceiling (§2.1). */
export const PAGE_LIMITS = [25, 50, 100, 200] as const;

export type PagerProps = {
  /** Rows on the page in hand. */
  count: number;
  /**
   * 1-based position of this page's first row in the sequence walked so far, or `null` when it
   * cannot be known — a page reached from a cursor handed over in a URL, say.
   */
  from?: number | null;
  limit: number;
  hasPrevious: boolean;
  /** Straight from the response's `has_more`. It is the only forward signal a keyset page gets. */
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  /** Omit to fix the page size for this screen. */
  onLimitChange?: (limit: number) => void;
  limitOptions?: readonly number[];
  /** A page is in flight: both directions are held so a double press cannot skip a page. */
  busy?: boolean;
  /** What is being paged, singular — "invoice", "event". */
  noun?: string;
  /**
   * The plural, when the regular rule would get it wrong. `pluralOf` handles `company` and `tax`;
   * an invoice **series** is the case no rule covers, since its plural is itself (`lib/text`).
   */
  nounPlural?: string;
};

/**
 * The list's pager.
 *
 * **There are no page numbers, and there is no total, by design.** Lists page by signed keyset
 * cursor and the API deliberately returns no unconditional count —
 * counting a filtered ledger on every page view is the query that takes a production database
 * down. So a page states the range it is showing and offers one step either way. "Page 7 of 24"
 * would need the count; "1,240 invoices" would need it twice.
 *
 * Previous is a real step back rather than a re-query: the caller keeps the cursors it has used
 * (`useListQuery` does this), because a keyset cursor only points forward.
 */
export function Pager({
  count,
  from = null,
  limit,
  hasPrevious,
  hasNext,
  onPrevious,
  onNext,
  onLimitChange,
  limitOptions = PAGE_LIMITS,
  busy = false,
  noun = 'row',
  nounPlural,
}: PagerProps) {
  const format = useFormatters();
  /* Grouped by the reader's configured grouping, not `toLocaleString`: a five-figure row index
   * reads `1,00,001` under Indian grouping and `100,001` under Western, and both are correct. */
  const integer = (value: number) => format.quantity(String(value), { precision: 0 });

  /* Both forms come from one rule (`lib/text`) rather than a `${noun}s` per sentence: this component
   * writes the noun into four strings, and "No companys" only has to be wrong in one of them. */
  const plural = pluralNoun(noun, count, nounPlural);
  /* The always-plural form, for the copy that never agrees with a count: "No invoices" and "Next
   * page of invoices" are plural whatever this page happens to hold. */
  const plurals = nounPlural ?? pluralOf(noun);
  const range =
    count === 0
      ? `No ${plurals}`
      : from === null
        ? `Showing ${integer(count)} ${plural}`
        : `Showing ${integer(from)}–${integer(from + count - 1)}`;

  const choices = limitOptions
    /* A screen cannot offer past the server's ceiling by passing a bigger number — that would be a
     * 422 on the first request rather than a bigger page. */
    .filter((option) => option > 0 && option <= LIMIT_MAX)
    .map((option) => ({ value: String(option), label: `${integer(option)} per page` }));

  return (
    <div className="pms-pager">
      {/*
        The range is the only place a reader learns where they are, and it changes on every step,
        so it is announced. Politely: they asked for the page, they are not being interrupted.
      */}
      <p className="pms-pager__range" role="status" aria-live="polite">
        {range}
      </p>

      <div className="pms-pager__controls">
        {onLimitChange && choices.length > 0 ? (
          <Select
            label="Rows per page"
            hideLabel
            inline
            value={String(limit)}
            options={choices}
            /* Changing the page size invalidates every cursor in hand — it is part of what a
               cursor is signed over — so the caller restarts the list. That belongs to the
               caller, not here, which is why this only reports the number. */
            onChange={(next) => onLimitChange(Number(next))}
            disabled={busy}
          />
        ) : null}

        <IconButton
          label={`Previous page of ${plurals}`}
          icon={<ChevronLeftIcon size={16} />}
          variant="outline"
          onClick={onPrevious}
          disabled={!hasPrevious || busy}
        />
        <IconButton
          label={`Next page of ${plurals}`}
          icon={<ChevronRightIcon size={16} />}
          variant="outline"
          onClick={onNext}
          disabled={!hasNext || busy}
        />
      </div>
    </div>
  );
}
