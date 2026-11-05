/**
 * `DataTable`'s column model: the types, and the pure helpers that read a row.
 *
 * **Columns are data, not JSX.** A screen declares what each column *is* — a money amount, a
 * status code, a masked identifier — and the table decides how that renders. Handing the caller a
 * `render` callback for every column would move formatting back into the screens, which is exactly
 * how a stray `toLocaleString` or a `Number()` on an amount gets in. `type: 'custom'` exists for
 * the genuinely one-off cell and is the only escape hatch.
 *
 * Everything here is framework-free and hook-free: it is called during a cell's render, so it must
 * be. The rendering itself lives in `components/table-cells.tsx`.
 */
import type { ReactNode } from 'react';
import type { Tone } from '../components/Badge';
import type { MenuItem } from '../components/Menu';
import type { Formatters } from './display-config';

/**
 * What a cell holds. This is the list contract's vocabulary, not a styling choice: `money` carries
 * a currency, `quantity` and `money` round to different configured precisions, `date` is a
 * business date with no timezone while `datetime` is an instant, and `masked` is a value the server
 * only ever sends the tail of.
 */
export type CellType =
  | 'text'
  /** An identifier, series or reference — mono, because character width carries meaning. */
  | 'code'
  | 'money'
  | 'quantity'
  | 'percent'
  /** A business date: formatted off the `YYYY-MM-DD` string, never through a timezone. */
  | 'date'
  /** An instant, rendered in the configured display timezone. */
  | 'datetime'
  /** An instant as elapsed time ("3 hours ago"), with the absolute value on hover. */
  | 'relative'
  /** One code from a closed set, as a toned badge. */
  | 'status'
  /** Several codes from a closed set — roles, tags, features. */
  | 'chips'
  /** A share of a total, as a bar plus its percentage. */
  | 'meter'
  | 'link'
  | 'boolean'
  /** A partially redacted value — card last four, tax-ID tail. */
  | 'masked'
  | 'custom'
  /** The row's verbs, as a kebab menu. */
  | 'actions';

export type CellAlign = 'start' | 'end' | 'center';

export type SortDirection = 'asc' | 'desc';

/**
 * One sort key. A list's real sort always ends with `id` as the tie-breaker
 * — the server appends it, so it never appears here.
 */
export type Sort = { key: string; direction: SortDirection };

/** Row height. Both are comfortable enough to hit; `compact` fits a working day's ledger. */
export type Density = 'comfortable' | 'compact';

export type Column<Row> = {
  /** The field key, React key and column-picker identity. Must be unique. */
  key: string;
  /** The visible column heading, and the label the stacked narrow layout shows per cell. */
  header: string;
  /** Defaults to `text`. */
  type?: CellType;
  /**
   * Reads the cell's value out of the row. Defaults to `row[key]`, which covers a flat list item;
   * supply this for a nested or derived field.
   */
  value?: (row: Row) => unknown;
  /** `type: 'custom'` only. The formatters are passed in because a renderer cannot call hooks. */
  render?: (row: Row, format: Formatters) => ReactNode;
  /** Overrides the alignment derived from `type` — figures right, everything else left. */
  align?: CellAlign;
  /**
   * Offers this column as a sort key. The *allowlisted combinations* live server-side
   *; this only says the header may be pressed.
   */
  sortable?: boolean;
  /** Which way this column sorts on its first press, overriding the type's default. */
  defaultSortDirection?: SortDirection;
  /** A CSS width for the column, applied through `<colgroup>`. */
  width?: string;
  /** Hidden until the reader turns it on in the column picker. */
  hidden?: boolean;
  /** Never hideable — the column that identifies the row. */
  locked?: boolean;
  /**
   * Presentation gate. The column is **absent** when the actor lacks the key. This is layout: a
   * field denied for read never arrives in the payload, and denying it is the application's authorization layer's job,
   * not this component's.
   */
  permission?: string;
  /** Clips to one line, with the full text as the cell's tooltip. */
  truncate?: boolean;
  /** Keeps the heading out of sight but in the accessibility tree — for an actions column. */
  hideHeader?: boolean;
  /** Longer explanation of the column, shown as the heading's tooltip. */
  description?: string;
  /** `money` — the row field holding this amount's ISO currency code. */
  currencyKey?: string;
  /** `money` · `quantity` · `percent` — overrides the configured display precision. */
  precision?: number;
  /** `status` · `chips` · `meter` — the tone for a raw code. Defaults to `neutral`. */
  tone?: (value: string, row: Row) => Tone;
  /** `status` · `chips` — the human label for a raw code. Defaults to the code itself. */
  label?: (value: string, row: Row) => string;
  /** `link` — the target. Returning `null` renders the text unlinked. */
  href?: (row: Row) => string | null;
  /** `link` — opens in a new tab, and says so. */
  external?: boolean;
  /** `meter` — the denominator; the cell's own value is the numerator. */
  total?: (row: Row) => string | null;
  /** `boolean` — the two words, in that order. Defaults to `['Yes', 'No']`. */
  words?: readonly [string, string];
  /** `actions` — this row's verbs. Each item carries its own permission and disabled reason. */
  actions?: (row: Row) => readonly MenuItem[];
};

/** Types whose content is a figure: right-aligned, and tabular so a column of them lines up. */
const FIGURE_TYPES: ReadonlySet<CellType> = new Set(['money', 'quantity', 'percent', 'meter']);

export function columnType<Row>(column: Column<Row>): CellType {
  return column.type ?? 'text';
}

export function isFigure(type: CellType): boolean {
  return FIGURE_TYPES.has(type);
}

export function alignOf<Row>(column: Column<Row>): CellAlign {
  if (column.align) return column.align;
  const type = columnType(column);
  // Figures align on their last digit; the row's verbs sit at the end of the row. Everything
  // else reads from the start, including a right-to-left script — hence `start`, not `left`.
  return isFigure(type) || type === 'actions' ? 'end' : 'start';
}

/**
 * Which way a column sorts the first time its header is pressed.
 *
 * Descending for anything where the interesting end is the top — the newest document, the largest
 * balance, the biggest variance. Ascending for names and codes, where the alphabet is the point.
 */
export function firstDirection<Row>(column: Column<Row>): SortDirection {
  if (column.defaultSortDirection) return column.defaultSortDirection;
  const type = columnType(column);
  return isFigure(type) || type === 'date' || type === 'datetime' || type === 'relative'
    ? 'desc'
    : 'asc';
}

/**
 * The sort produced by pressing a column's header: flip it if it already leads, otherwise sort by
 * it alone.
 *
 * **Deliberately single-key.** The server accepts allowlisted sort *combinations*, not arbitrary
 * ones, so letting a reader assemble their own triple by shift-clicking
 * would mostly earn them a 422. A screen that needs a compound sort states it as the default and
 * keeps those headers unsortable.
 */
export function nextSort<Row>(column: Column<Row>, current: readonly Sort[]): Sort[] {
  const leading = current[0];
  if (leading && leading.key === column.key) {
    return [{ key: column.key, direction: leading.direction === 'asc' ? 'desc' : 'asc' }];
  }
  return [{ key: column.key, direction: firstDirection(column) }];
}

/** The direction this column is currently sorted by, or `null` when it is not the sort key. */
export function sortedBy<Row>(column: Column<Row>, current: readonly Sort[]): SortDirection | null {
  const found = current.find((entry) => entry.key === column.key);
  return found ? found.direction : null;
}

/**
 * Reads `key` off a row, tolerating a row that is not a plain object.
 *
 * A dotted key is walked as a path — `custom_fields.discount_cap.currency`. Not a convenience: a
 * `currency_amount` custom field stores `{amount, currency}` together inside the custom-field bag
 *, so a money column's `currencyKey` has no top-level field to name.
 * Without the path it would have to fall back to *no* currency, and an amount in USD rendered with
 * the company's ₹ is a money-correctness defect rather than a formatting one.
 *
 * A key with no dot in it is looked up exactly as written, which is every native field.
 */
export function fieldValue<Row>(row: Row, key: string): unknown {
  let current: unknown = row;
  for (const step of key.includes('.') ? key.split('.') : [key]) {
    if (current === null || typeof current !== 'object') return undefined;
    current = (current as Record<string, unknown>)[step];
  }
  return current;
}

export function rawValue<Row>(column: Column<Row>, row: Row): unknown {
  return column.value ? column.value(row) : fieldValue(row, column.key);
}

/**
 * Nothing to show. Every list-item field is nullable except `id`
 *, so this is the common case rather than the edge one.
 *
 * `0` and `false` are **not** blank. A zero balance is a fact, and rendering it as an em dash —
 * or worse, rendering a missing balance as `0` — is the kind of quiet money bug that survives
 * review, so the test is against `null`, `undefined` and the empty string only.
 */
export function isBlank(value: unknown): boolean {
  return value === null || value === undefined || value === '';
}

/**
 * The value as a string, for a formatter that takes one. Amounts and quantities are strings end
 * to end; a `number` is accepted only because a JSON payload can carry one, and
 * it is stringified rather than arithmetic being done on it.
 */
export function asText(value: unknown): string | null {
  if (isBlank(value)) return null;
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : null;
  // Arrays, objects and booleans have no single text form — their cell types handle them.
  return null;
}

/**
 * A share, 0–1, for the meter's bar width.
 *
 * The one place a decimal string meets `Number()`, and deliberately so: this is a bar's width,
 * never an amount. The amount itself is still formatted from its string, and nothing computed
 * here is ever shown as money. Returns `null` when there is no usable denominator, so the cell
 * renders an em dash rather than a confident 0%.
 */
export function share(value: unknown, total: unknown): number | null {
  const numerator = asText(value);
  const denominator = asText(total);
  if (numerator === null || denominator === null) return null;
  const top = Number(numerator);
  const bottom = Number(denominator);
  if (!Number.isFinite(top) || !Number.isFinite(bottom) || bottom === 0) return null;
  return top / bottom;
}
