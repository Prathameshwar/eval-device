'use client';

import type { ReactNode } from 'react';
import { useFormatters } from '../lib/display-config';
import { pluralNoun } from '../lib/text';
import { Button } from './Button';

export type BulkBarProps = {
  /** How many rows are selected. Nothing is rendered at zero — the screen keeps no condition. */
  count: number;
  /** What is being acted on, singular: "invoice", "user", "event". */
  noun?: string;
  /** The plural, where the regular rule would get it wrong — an invoice **series** (`lib/text`). */
  nounPlural?: string;
  onClear: () => void;
  /** The verbs. Each one is the screen's, because each one has its own permission and confirmation. */
  children?: ReactNode;
  /**
   * Holds every verb — and clearing — while a batch is running, so a second press cannot start the
   * same one twice. The verbs belong to the screen, so this is enforced by the `<fieldset>` they sit
   * in rather than by a prop each caller would have to thread through its own buttons.
   */
  busy?: boolean;
};

/**
 * The bar above a table stating what is selected and what may be done to it.
 *
 * The wording is load-bearing: **"on this page"**. `DataTable` scopes a selection to the rows in
 * hand and there is no "select everything matching this query" — a keyset list has no total to
 * count such a set with, and a bulk operation over rows nobody has seen is how one mistaken filter
 * becomes forty wrong documents. Saying "12 selected" alone would quietly imply the larger set.
 *
 * It is a region rather than a toolbar: the verbs inside it are ordinary buttons, and a toolbar's
 * arrow-key contract would take those keys away from the reader for no gain.
 */
export function BulkBar({
  count,
  noun = 'row',
  nounPlural,
  children,
  onClear,
  busy = false,
}: BulkBarProps) {
  const format = useFormatters();

  if (count <= 0) return null;

  // One plural rule for the whole list surface (`lib/text`): this sentence, the pager's range and
  // the table's row count all name the same resource, so they cannot disagree about its plural.
  const label = `${format.quantity(String(count), { precision: 0 })} ${pluralNoun(noun, count, nounPlural)}`;

  return (
    <div className="pms-bulk-bar" role="region" aria-label="Bulk actions">
      {/*
       * Announced politely: the reader is ticking boxes and the count is the feedback for that.
       * `aria-live` on the count alone, not the bar, or every verb appearing would be read out too.
       */}
      <p className="pms-bulk-bar__count" role="status" aria-live="polite">
        {`${label} selected on this page`}
      </p>
      {/* A `<fieldset>` because `disabled` on one genuinely disables every control inside it,
        * keyboard included — the screen's own buttons need not know a batch is in flight. */}
      <fieldset className="pms-bulk-bar__actions" disabled={busy}>
        {children}
        {/* Last, and quiet: it is the way out, not the point of the bar. */}
        <Button variant="ghost" onClick={onClear}>
          Clear selection
        </Button>
      </fieldset>
    </div>
  );
}
