'use client';

import { Fragment, useId, useState, type ReactNode } from 'react';
import { useDisplayConfig, useFormatters } from '../lib/display-config';
import { useGranted } from '../lib/permissions';
import { pluralNoun } from '../lib/text';
import {
  alignOf,
  columnType,
  isFigure,
  nextSort,
  sortedBy,
  type Column,
  type Density,
  type Sort,
} from '../lib/table';
import { Button } from './Button';
import { Checkbox } from './Checkbox';
import { IconButton } from './IconButton';
import type { MenuItem } from './Menu';
import { EmptyState, ErrorState, Skeleton, type ErrorStatus } from './States';
import { BoxIcon, LockIcon } from './icons';
import { ChevronDownIcon, ChevronRightIcon, ChevronUpDownIcon, SearchIcon } from './icons-console';
import { ChevronUpIcon } from './icons-table';
import { renderCell } from './table-cells';

export type DataTableProps<Row> = {
  /**
   * The table's accessible name, rendered as a visually-hidden `<caption>`. Required: a page with
   * two tables gives a screen-reader user nothing to tell them apart otherwise.
   */
  caption: string;
  columns: readonly Column<Row>[];
  rows: readonly Row[];
  /** Stable row identity — the React key, and what names the row's own controls by default. */
  rowId: (row: Row) => string;
  /** A human name for the row ("Invoice INV-0004"), used to name its per-row controls. */
  rowLabel?: (row: Row) => string;
  /**
   * Why this row can no longer be changed — "posted on 31 Mar 2026", "period closed". Marks the
   * row and states the reason.
   *
   * This is a *marker*, not enforcement: a posted document in a closed period is never editable
   *, and that is settled in `domain/`. What this prevents is the reader finding
   * out only after the request fails.
   */
  rowLocked?: (row: Row) => string | null;
  /**
   * The sort in force. A list always has one — the server needs a stable order to page by — so
   * there is no unsorted state to return to, only a different sort.
   */
  sort?: readonly Sort[];
  /**
   * Receives the whole new sort when a sortable header is pressed. Without it no header is
   * pressable, however many columns say `sortable`: a control that cannot report anywhere is a
   * dead control.
   */
  onSortChange?: (sort: readonly Sort[]) => void;
  density?: Density;
  /** Replaces the body with placeholder rows. The previous page's rows are not left on screen. */
  loading?: boolean;
  skeletonRows?: number;
  /** A failed load. Each status has its own intended copy — a 403 is not an outage (`States`). */
  error?: ErrorStatus | null;
  errorDetail?: ReactNode;
  onRetry?: () => void;
  /**
   * True when a search or a filter is narrowing the list. It changes what "no rows" means: an
   * empty ledger needs a way to start one, an over-filtered one needs its filters lifted.
   */
  filtered?: boolean;
  emptyTitle?: ReactNode;
  emptyBody?: ReactNode;
  /** The way out of a genuinely empty list — "Create the first invoice". */
  emptyAction?: ReactNode;
  onClearFilters?: () => void;
  /**
   * Turns on the leading selection column.
   *
   * **Selection is scoped to the page in hand, by construction.** Toggling anything reports ids
   * drawn from the current page only, so an id from a page the reader has left cannot survive — and
   * there is deliberately no "select everything matching this query". Two reasons, and both are
   * about money: a keyset list has no total, so such a set could not
   * even be counted before acting on it; and a bulk operation over rows nobody has seen is how a
   * mistaken filter becomes forty wrong documents. What the reader can see is what they can act on.
   */
  selectable?: boolean;
  /** The selected row ids. Controlled — the screen owns the set, and clears it when it navigates. */
  selected?: readonly string[];
  /**
   * Receives the whole new selection. Without it no checkbox is drawn, however `selectable` is set:
   * same rule as `onSortChange`.
   */
  onSelectionChange?: (ids: readonly string[]) => void;
  /** Whether a row may be selected at all — a posted document in a bulk-void list may not. */
  rowSelectable?: (row: Row) => boolean;
  /**
   * The row's verbs, as a kebab in a trailing column the table adds itself. The shorthand for the
   * common case; a screen that needs the verbs somewhere other than the last column declares its
   * own `type: 'actions'` column instead, and then this is ignored rather than drawing a second one.
   */
  rowActions?: (row: Row) => readonly MenuItem[];
  /**
   * The panel shown beneath an expanded row — the lines of an invoice, the diff of an audit event.
   * Called only for a row that is actually open, so a page of 200 rows builds one panel, not 200.
   */
  renderDetail?: (row: Row) => ReactNode;
  /** Whether a row has anything to expand. Defaults to every row once `renderDetail` is given. */
  rowExpandable?: (row: Row) => boolean;
  /** Freezes the heading row while the body scrolls. On by default. */
  stickyHeader?: boolean;
  /** Freezes the first column against horizontal scroll, so the identifier stays in view. */
  pinFirstColumn?: boolean;
  /**
   * Stacks each row into a labelled block on a narrow viewport. On by default: a twelve-column
   * ledger on a phone is unreadable sideways. Turn it off for a table whose only value is the
   * column alignment — a trial balance.
   */
  stack?: boolean;
  /** A row action was chosen: the `MenuItem` id, and the row it belongs to. */
  onAction?: (id: string, row: Row) => void;
};

/**
 * The shared table.
 *
 * A semantic `<table>` — not a `role="grid"`. A grid is a spreadsheet: it takes over the arrow
 * keys and owes the user cell-by-cell navigation, and a list of records that happens to be
 * rectangular is not that. Reading rows, following a link and opening a row's menu are all served
 * by the browser's own tab order.
 *
 * Everything the caller declares is data: columns say what a field *is*, and the table decides
 * alignment, formatting, truncation and how a missing value reads. See `lib/table`.
 */
export function DataTable<Row>({
  caption,
  columns,
  rows,
  rowId,
  rowLabel,
  rowLocked,
  sort = [],
  onSortChange,
  density = 'comfortable',
  loading = false,
  skeletonRows = 5,
  error = null,
  errorDetail,
  onRetry,
  filtered = false,
  emptyTitle,
  emptyBody,
  emptyAction,
  onClearFilters,
  selectable = false,
  selected = [],
  onSelectionChange,
  rowSelectable,
  rowActions,
  renderDetail,
  rowExpandable,
  stickyHeader = true,
  pinFirstColumn = false,
  stack = true,
  onAction,
}: DataTableProps<Row>) {
  const format = useFormatters();
  const { currency } = useDisplayConfig();
  const granted = useGranted();
  /* Expansion is presentation and nothing else — no request, no query, nothing to share — so it is
   * the one piece of table state the table itself keeps. A stale id simply matches no row. */
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());
  const detailId = useId();

  /*
   * The column set is resolved once, before anything measures it, so the `colSpan` of a state row,
   * the stacked labels and the pinned edge all speak about what is actually rendered.
   *
   * Permission here is layout only. A field the actor may not read never arrives in the payload,
   * and blocking it is the application's authorization layer's job server-side — dropping
   * the column keeps the table from rendering a row of em dashes for data that was never sent.
   */
  const declared = columns.filter((column) => !column.hidden && granted(column.permission));
  /*
   * `rowActions` is a shorthand for a trailing actions column, resolved into one here so there is a
   * single rendering path: alignment, the hidden heading and the stacked layout all already know
   * what an actions cell is (`table-cells`). Skipped when the screen declared its own, or a table
   * asking for both would grow two kebabs.
   */
  const shown =
    rowActions && !declared.some((column) => columnType(column) === 'actions')
      ? [
          ...declared,
          {
            key: '__actions',
            header: 'Actions',
            hideHeader: true,
            type: 'actions',
            actions: rowActions,
          } satisfies Column<Row>,
        ]
      : declared;

  const state = error !== null ? 'error' : loading ? 'loading' : rows.length === 0 ? 'empty' : 'ready';

  /* A control column reports nowhere without its handler, so it is not drawn — the same rule that
   * keeps an unpressable sort header from existing. */
  const selecting = selectable && onSelectionChange !== undefined;
  /** The leading control columns, in render order. Their count is every offset in this component. */
  const controls: readonly ('select' | 'expand')[] = [
    ...(selecting ? (['select'] as const) : []),
    ...(renderDetail ? (['expand'] as const) : []),
  ];
  const span = Math.max(1, shown.length + controls.length);

  /*
   * Selection, page-scoped: every set below is built from the rows on screen, which is what makes
   * the guarantee in the `selectable` docblock structural rather than remembered.
   */
  const chosen = new Set(selected);
  const pageRows = state === 'ready' ? rows : [];
  const selectableIds = selecting
    ? pageRows.filter((row) => (rowSelectable ? rowSelectable(row) : true)).map(rowId)
    : [];
  const selectedOnPage = selectableIds.filter((id) => chosen.has(id));
  const allSelected = selectableIds.length > 0 && selectedOnPage.length === selectableIds.length;

  function reportSelection(next: ReadonlySet<string>): void {
    // Reported in page order, and filtered through the page's own ids — so nothing off this page,
    // and nothing unselectable, can be in what a bulk action receives.
    onSelectionChange?.(selectableIds.filter((id) => next.has(id)));
  }

  function toggleRow(id: string, on: boolean): void {
    const next = new Set(selectedOnPage);
    if (on) next.add(id);
    else next.delete(id);
    reportSelection(next);
  }

  function toggleDetail(id: string): void {
    setExpanded((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  /*
   * The pinned run's offsets. A control cell is a known width — this component sets it — so each
   * one's sticky position is that width times its place in the run, and the first data column sits
   * past all of them. Measuring instead would mean a layout effect and a frame of overlap.
   */
  const pinOffset = (position: number): { insetInlineStart: string } | undefined =>
    position === 0 ? undefined : { insetInlineStart: `calc(var(--pms-table-ctrl-w) * ${position})` };

  /*
   * Explicit ARIA roles, but only for the stacked variant. `display: block` on a table's elements
   * strips their implicit roles in every engine, so the narrow layout would otherwise hand a
   * screen reader a pile of unrelated blocks. Restating the roles is the documented remedy; on the
   * wide layout they are redundant noise, which is why they are not emitted unconditionally.
   */
  const roles = stack
    ? {
        table: 'table' as const,
        group: 'rowgroup' as const,
        row: 'row' as const,
        cell: 'cell' as const,
        head: 'columnheader' as const,
      }
    : {};

  const className = [
    'pms-table',
    stack ? 'pms-table--stack' : null,
    stickyHeader ? 'pms-table--sticky' : null,
  ]
    .filter(Boolean)
    .join(' ');

  function stateRow(): ReactNode {
    if (state === 'error' && error !== null) {
      return (
        <ErrorState
          status={error}
          detail={errorDetail}
          action={
            onRetry ? (
              <Button variant="ghost" onClick={onRetry}>
                Try again
              </Button>
            ) : undefined
          }
        />
      );
    }

    // Two different failures wearing the same word. "No matches" is about the query and is
    // recoverable by lifting it; "nothing yet" is about the ledger and needs the first record.
    return filtered ? (
      <EmptyState
        icon={<SearchIcon size={20} />}
        title={emptyTitle ?? 'No matching rows'}
        body={emptyBody ?? 'No rows match the current search and filters.'}
        action={
          onClearFilters ? (
            <Button variant="ghost" onClick={onClearFilters}>
              Clear filters
            </Button>
          ) : (
            emptyAction
          )
        }
      />
    ) : (
      <EmptyState
        icon={<BoxIcon size={20} />}
        title={emptyTitle ?? 'Nothing here yet'}
        body={emptyBody}
        action={emptyAction}
      />
    );
  }

  return (
    /*
     * A **focusable, named scroll region**, not a bare wrapper.
     *
     * This element scrolls — sideways always, and vertically whenever the header is frozen — and a
     * scroll container that cannot be reached by keyboard is content a keyboard-only reader cannot
     * get to (WCAG 2.1.1). Arrow keys scroll a container only while focus is inside it, and a wide
     * ledger's off-screen columns may hold nothing focusable at all, so the container itself takes
     * the tab stop. `role="region"` with the caption as its name is what stops that stop being an
     * unexplained one: a reader who lands here is told which table they are in.
     *
     * The cost is one tab stop per table, which is the accepted trade of this pattern.
     */
    <div
      className="pms-table-shell"
      role="region"
      aria-label={caption}
      tabIndex={0}
      data-sticky={stickyHeader ? 'true' : undefined}
      /* The stylesheet lifts the height cap in the stacked layout: with the heading row clipped
       * there is no frozen header for the nested scroller to serve, and a scroller inside the page's
       * own is worst exactly where the viewport is smallest. */
      data-stack={stack ? 'true' : undefined}
    >
      <table className={className} data-density={density} aria-busy={loading || undefined} role={roles.table}>
        <caption className="pms-visually-hidden">{caption}</caption>
        {/* Widths belong to the column, not to a cell, or every row restates them. */}
        <colgroup>
          {/* The control columns are a fixed width, which is also what makes `pinOffset` possible. */}
          {controls.map((control) => (
            <col key={control} style={{ width: 'var(--pms-table-ctrl-w)' }} />
          ))}
          {shown.map((column) => (
            <col key={column.key} style={column.width ? { width: column.width } : undefined} />
          ))}
        </colgroup>
        <thead role={roles.group}>
          <tr role={roles.row}>
            {controls.map((control, position) => (
              <th
                key={control}
                scope="col"
                role={roles.head}
                className="pms-table__ctrl"
                data-pinned={pinFirstColumn ? 'true' : undefined}
                style={pinFirstColumn ? pinOffset(position) : undefined}
              >
                {control === 'select' ? (
                  <Checkbox
                    checked={allSelected}
                    /* A partly-selected page is not a checked one, and a tick there would claim
                     * rows that are not in the set — which is a bulk action on the wrong rows. */
                    indeterminate={selectedOnPage.length > 0 && !allSelected}
                    disabled={selectableIds.length === 0}
                    onChange={(event) =>
                      onSelectionChange?.(event.target.checked ? selectableIds : [])
                    }
                  >
                    {/* Named for what it does select: not "all rows", which is a promise the
                     * component cannot keep across a keyset walk. */}
                    <span className="pms-visually-hidden">Select all rows on this page</span>
                  </Checkbox>
                ) : (
                  <span className="pms-visually-hidden">Details</span>
                )}
              </th>
            ))}
            {shown.map((column, index) => {
              const sortable = Boolean(column.sortable) && onSortChange !== undefined;
              const direction = sortable ? sortedBy(column, sort) : null;
              const heading = column.hideHeader ? (
                <span className="pms-visually-hidden">{column.header}</span>
              ) : (
                column.header
              );

              return (
                <th
                  key={column.key}
                  scope="col"
                  role={roles.head}
                  data-align={alignOf(column)}
                  data-pinned={pinFirstColumn && index === 0 ? 'true' : undefined}
                  /* The separating edge is drawn once, by the last cell of the pinned run — a
                   * shadow on each of them would print hairlines between the frozen cells. */
                  data-pin-edge={pinFirstColumn && index === 0 ? 'true' : undefined}
                  style={pinFirstColumn && index === 0 ? pinOffset(controls.length) : undefined}
                  data-sorted={direction ?? undefined}
                  /*
                   * `aria-sort` belongs on the header cell, not on the button inside it, and only
                   * a sortable column carries it — `none` on a column that can never sort tells a
                   * reader there is a control to find when there isn't.
                   */
                  aria-sort={
                    sortable
                      ? direction === 'asc'
                        ? 'ascending'
                        : direction === 'desc'
                          ? 'descending'
                          : 'none'
                      : undefined
                  }
                  title={column.description}
                >
                  {sortable ? (
                    <button
                      type="button"
                      className="pms-table__sort"
                      onClick={() => onSortChange(nextSort(column, sort))}
                    >
                      {heading}
                      {/* The affordance is stated by `aria-sort`, so the glyph is decoration. */}
                      <span className="pms-table__sort-icon" aria-hidden="true">
                        {direction === 'asc' ? (
                          <ChevronUpIcon size={12} />
                        ) : direction === 'desc' ? (
                          <ChevronDownIcon size={12} />
                        ) : (
                          <ChevronUpDownIcon size={12} />
                        )}
                      </span>
                    </button>
                  ) : (
                    heading
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody role={roles.group}>
          {state === 'ready'
            ? rows.map((row) => {
                const id = rowId(row);
                const label = rowLabel ? rowLabel(row) : id;
                const lockReason = rowLocked ? rowLocked(row) : null;
                const expandable = renderDetail !== undefined && (rowExpandable?.(row) ?? true);
                const open = expandable && expanded.has(id);
                const panelId = `${detailId}-${id}`;

                return (
                  <Fragment key={id}>
                    <tr
                      role={roles.row}
                      data-locked={lockReason ? 'true' : undefined}
                      data-selected={chosen.has(id) ? 'true' : undefined}
                    >
                      {controls.map((control, position) => (
                        <td
                          key={control}
                          role={roles.cell}
                          className="pms-table__ctrl"
                          data-pinned={pinFirstColumn ? 'true' : undefined}
                          style={pinFirstColumn ? pinOffset(position) : undefined}
                        >
                          {control === 'select' ? (
                            rowSelectable === undefined || rowSelectable(row) ? (
                              <Checkbox
                                checked={chosen.has(id)}
                                onChange={(event) => toggleRow(id, event.target.checked)}
                              >
                                <span className="pms-visually-hidden">{`Select ${label}`}</span>
                              </Checkbox>
                            ) : null
                          ) : expandable ? (
                            <IconButton
                              label={open ? `Hide details for ${label}` : `Show details for ${label}`}
                              icon={open ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
                              aria-expanded={open}
                              /* Only while the panel exists: pointing at an absent id is a broken
                               * reference, and `aria-expanded` already states the closed case. */
                              aria-controls={open ? panelId : undefined}
                              onClick={() => toggleDetail(id)}
                            />
                          ) : null}
                        </td>
                      ))}
                      {shown.map((column, index) => {
                        const cell = renderCell({ column, row, format, currency, rowLabel: label, onAction });
                        const type = columnType(column);

                        return (
                          <td
                            key={column.key}
                            role={roles.cell}
                            data-align={alignOf(column)}
                            data-figure={isFigure(type) ? 'true' : undefined}
                            data-empty={cell.blank ? 'true' : undefined}
                            data-pinned={pinFirstColumn && index === 0 ? 'true' : undefined}
                            data-pin-edge={pinFirstColumn && index === 0 ? 'true' : undefined}
                            style={pinFirstColumn && index === 0 ? pinOffset(controls.length) : undefined}
                            // The stacked layout prints this as the cell's own label. Omitted with
                            // the heading, so an actions cell doesn't grow a "Actions" caption.
                            data-label={column.hideHeader ? undefined : column.header}
                          >
                            {/* The marker leads the row's first cell, where the eye starts. */}
                            {index === 0 && lockReason ? (
                              <span className="pms-table__lock" title={lockReason}>
                                <LockIcon size={13} />
                                <span className="pms-visually-hidden">{`Locked: ${lockReason}`}</span>
                              </span>
                            ) : null}
                            {column.truncate ? (
                              <span
                                className="pms-table__ellipsis"
                                title={cell.blank ? undefined : cell.text ?? undefined}
                              >
                                {cell.content}
                              </span>
                            ) : (
                              cell.content
                            )}
                          </td>
                        );
                      })}
                    </tr>
                    {open && renderDetail ? (
                      /* A second row rather than a nested table: the detail belongs to this row's
                       * group in the accessibility tree, and spanning the width keeps it from
                       * pretending to be a value in one of the columns. */
                      <tr className="pms-table__detail-row" role={roles.row}>
                        <td
                          id={panelId}
                          className="pms-table__detail"
                          colSpan={span}
                          role={roles.cell}
                        >
                          {renderDetail(row)}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })
            : null}

          {state === 'loading'
            ? Array.from({ length: Math.max(1, skeletonRows) }, (_, index) => (
                <tr key={`skeleton-${index}`} role={roles.row} aria-hidden="true">
                  {controls.map((control) => (
                    <td key={control} role={roles.cell} className="pms-table__ctrl" />
                  ))}
                  {shown.map((column) => (
                    <td key={column.key} role={roles.cell} data-align={alignOf(column)}>
                      <Skeleton lines={1} />
                    </td>
                  ))}
                </tr>
              ))
            : null}

          {state === 'empty' || state === 'error' ? (
            <tr role={roles.row}>
              <td className="pms-table__state" colSpan={span} role={roles.cell}>
                {stateRow()}
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>

      {/*
       * The one announcement. A table's own rows are not announced when they change, so a reader
       * who presses "next page" is told the count rather than left to discover it — and a load or
       * a failure is stated rather than being a silent redraw.
       */}
      <span className="pms-visually-hidden" role="status" aria-live="polite">
        {state === 'loading'
          ? 'Loading rows'
          : state === 'error'
            ? 'The list could not be loaded'
            : state === 'empty'
              ? 'No rows'
              : `${rows.length} ${pluralNoun('row', rows.length)}`}
      </span>
    </div>
  );
}
