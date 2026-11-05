'use client';

/**
 * Which columns a reader has turned off, remembered per table.
 *
 * Three deliberate limits:
 *
 *  - **Only column keys are stored.** No values, no rows, no ids — a layout preference is not a
 *    cache of records, and `localStorage` is readable by anything running on the origin.
 *  - **It is layout, never authorization.** A column the actor may not read never arrives in the
 *    payload and is refused server-side by the application's authorization layer; hiding one
 *    here changes what is drawn and nothing else. The same reason tenant field config is layout
 *    rather than a permission.
 *  - **The stored set is untrusted input.** It comes from a store the reader can edit, so an
 *    unknown key is ignored, a locked column can never be hidden by it, and it can never hide the
 *    last column standing.
 */
import { useCallback, useEffect, useState } from 'react';
import type { Column } from './table';

/** Namespaced per table, so two tables on one screen keep their own layout. */
export function columnPrefsKey(tableId: string): string {
  return `pms.table.${tableId}.hidden`;
}

function read(tableId: string): readonly string[] | null {
  // Absent on the server, and throwing in a browser with storage denied (private mode, quota) —
  // neither is a reason to fail a render, so both fall through to the columns' own defaults.
  try {
    const raw = globalThis.localStorage?.getItem(columnPrefsKey(tableId));
    if (raw === null || raw === undefined) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return parsed.filter((entry): entry is string => typeof entry === 'string');
  } catch {
    return null;
  }
}

function write(tableId: string, hidden: readonly string[]): void {
  try {
    globalThis.localStorage?.setItem(columnPrefsKey(tableId), JSON.stringify(hidden));
  } catch {
    // A preference that could not be saved is a preference that does not survive the tab. That is
    // an acceptable outcome; an exception thrown out of a click handler is not.
  }
}

export type ColumnPreferences<Row> = {
  /** The column set with the reader's choices applied — hand this straight to `DataTable`. */
  columns: readonly Column<Row>[];
  /** The columns offered in the picker, hidden ones included, in declaration order. */
  choices: readonly Column<Row>[];
  hidden: ReadonlySet<string>;
  toggle: (key: string) => void;
  /** Back to the column set as the screen declared it. */
  reset: () => void;
};

/**
 * Resolves a declared column set against what the reader has turned off, and persists the change.
 *
 * The stored set is adopted in an effect rather than read during the first render: `localStorage`
 * does not exist while the page is rendered on the server, so reading it in the initial state would
 * make the server and the client disagree — a hydration mismatch. The first paint is therefore the
 * screen's own defaults, and the remembered layout arrives immediately after.
 */
export function useColumnPreferences<Row>(
  tableId: string,
  columns: readonly Column<Row>[],
): ColumnPreferences<Row> {
  const [hidden, setHidden] = useState<ReadonlySet<string>>(
    () => new Set(columns.filter((column) => column.hidden).map((column) => column.key)),
  );

  useEffect(() => {
    const stored = read(tableId);
    if (stored !== null) setHidden(new Set(stored));
  }, [tableId]);

  /*
   * `hidden` is the whole authority: a column is drawn unless it is in the set, whatever its own
   * `hidden` default said. Once the reader has an opinion, the default is no longer the answer.
   */
  const locked = new Set(columns.filter((column) => column.locked).map((column) => column.key));
  const effective = new Set([...hidden].filter((key) => !locked.has(key)));
  const visible = columns.filter((column) => !effective.has(column.key));

  const toggle = useCallback(
    (key: string) => {
      setHidden((current) => {
        const column = columns.find((entry) => entry.key === key);
        // An unknown key, and the column that identifies the row, are both refused here rather
        // than only being left out of the picker — this is the function a screen can call directly.
        if (column === undefined || column.locked) return current;

        const next = new Set(current);
        if (!next.delete(key)) {
          // A table with nothing in it is not a layout the reader can recover from without the
          // picker they just emptied, so the last column standing stays.
          const shownNow = columns.filter((entry) => !current.has(entry.key) || entry.locked);
          if (shownNow.length <= 1) return current;
          next.add(key);
        }
        write(tableId, [...next]);
        return next;
      });
    },
    [columns, tableId],
  );

  const reset = useCallback(() => {
    const defaults = new Set(columns.filter((column) => column.hidden).map((column) => column.key));
    write(tableId, [...defaults]);
    setHidden(defaults);
  }, [columns, tableId]);

  return { columns: visible, choices: columns, hidden: effective, toggle, reset };
}
