/**
 * One cell of a `DataTable`, rendered from its column's declared type.
 *
 * A plain function rather than a component, on purpose. A hundred-row table with twelve columns is
 * 1,200 cells; wrapping each in its own component buys nothing and costs a fibre each. It also
 * means this cannot call a hook — the formatters and the company currency are passed in, resolved
 * once by the table.
 *
 * The two rules every branch obeys:
 *
 *  - **A missing value is an em dash, never a zero.** Every list-item field except `id` is
 *    nullable, and `0` is a real amount (see `isBlank`).
 *  - **Nothing is formatted here by hand.** Money, quantities, percentages and dates all go
 *    through the config-bound formatters, so one company's precision and date pattern apply
 *    everywhere.
 */
import type { ReactNode } from 'react';
import { EM_DASH } from '../lib/format';
import type { Formatters } from '../lib/display-config';
import { isSafeHref } from '../lib/url';
import {
  asText,
  columnType,
  fieldValue,
  isBlank,
  rawValue,
  share,
  type Column,
} from '../lib/table';
import { Badge } from './Badge';
import { Menu } from './Menu';
import { Meter } from './Meter';
import { ExternalLinkIcon } from './icons-console';

/** Chips beyond this collapse into a `+N` with the full list on hover. */
const CHIP_LIMIT = 3;

/** The redaction prefix. Four bullets and a space, matching the four digits the server sends. */
const MASK = '•••• ';

export type RenderedCell = {
  content: ReactNode;
  /**
   * The cell's plain-text form, where it has one — used as the tooltip when the column truncates
   * and as the value a test can assert on. `null` for a cell that is a control or a graphic.
   */
  text: string | null;
  /** There was no value. The table dims the em dash rather than letting it read as content. */
  blank: boolean;
};

export type CellArgs<Row> = {
  column: Column<Row>;
  row: Row;
  format: Formatters;
  /** The company's currency, so a row in another one can be told apart from it. */
  currency: string;
  /** A human name for the row, used to name the row's own controls. */
  rowLabel: string;
  onAction?: (id: string, row: Row) => void;
};

const BLANK: RenderedCell = { content: EM_DASH, text: EM_DASH, blank: true };

/** A value that needs no wrapper: the string is the whole cell. */
function plain(text: string): RenderedCell {
  return { content: text, text, blank: false };
}

/**
 * Money, with the currency it is denominated in.
 *
 * A row in a currency other than the company's must not borrow the company's symbol — `₹` against
 * a USD amount is a money-correctness defect, not a formatting preference. Such a
 * row loses the symbol and states its code instead, which is also the only form that lets two
 * currencies sit in one column without misleading anyone.
 */
function moneyCell<Row>({ column, row, format, currency }: CellArgs<Row>, value: unknown): RenderedCell {
  const amount = asText(value);
  const code = column.currencyKey === undefined ? null : asText(fieldValue(row, column.currencyKey));

  if (code !== null && code !== currency) {
    const figure = format.money(amount, { precision: column.precision, display: 'none' });
    return {
      content: (
        <>
          {figure}
          <span className="pms-table__ccy">{code}</span>
        </>
      ),
      text: `${figure} ${code}`,
      blank: false,
    };
  }

  return plain(format.money(amount, { precision: column.precision }));
}

function statusCell<Row>({ column, row }: CellArgs<Row>, value: unknown): RenderedCell {
  const code = asText(value) ?? '';
  const label = column.label ? column.label(code, row) : code;
  const tone = column.tone ? column.tone(code, row) : 'neutral';
  return { content: <Badge tone={tone}>{label}</Badge>, text: label, blank: false };
}

function chipsCell<Row>({ column, row }: CellArgs<Row>, value: unknown): RenderedCell {
  const codes = Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === 'string' && entry !== '')
    : [];
  if (codes.length === 0) return BLANK;

  const labels = codes.map((code) => (column.label ? column.label(code, row) : code));
  const shown = codes.slice(0, CHIP_LIMIT);
  const hidden = codes.length - shown.length;

  return {
    content: (
      <span className="pms-table__chips">
        {shown.map((code, index) => (
          <Badge key={code} tone={column.tone ? column.tone(code, row) : 'neutral'} variant="outline">
            {labels[index]}
          </Badge>
        ))}
        {/* The overflow count carries the whole list, so nothing is unreachable without a click. */}
        {hidden > 0 ? (
          <span className="pms-table__chips-more" title={labels.join(', ')}>
            {`+${hidden}`}
          </span>
        ) : null}
      </span>
    ),
    text: labels.join(', '),
    blank: false,
  };
}

function meterCell<Row>({ column, row }: CellArgs<Row>, value: unknown): RenderedCell {
  const ratio = share(value, column.total ? column.total(row) : null);
  // No denominator is not a zero share: without a total there is no share to state at all.
  if (ratio === null) return BLANK;
  return {
    content: (
      <Meter
        value={ratio}
        tone={column.tone ? column.tone(asText(value) ?? '', row) : 'brand'}
        label={`${column.header} share`}
      />
    ),
    text: null,
    blank: false,
  };
}

function linkCell<Row>({ column, row }: CellArgs<Row>, value: unknown): RenderedCell {
  const text = asText(value) ?? EM_DASH;
  const href = column.href ? column.href(row) : null;
  // A row the actor may see but not open keeps its text: a dead link is worse than no link. So does
  // one whose destination is not a destination — `column.href` reads a payload, and `external`
  // exists because that payload legitimately points off-site, which is exactly the case a
  // `javascript:` URL arrives in (`lib/url`).
  if (href === null || !isSafeHref(href)) return plain(text);

  return {
    content: (
      <a
        className="pms-link pms-table__link"
        href={href}
        {...(column.external ? { target: '_blank', rel: 'noreferrer noopener' } : {})}
      >
        {text}
        {column.external ? (
          <>
            <ExternalLinkIcon size={13} />
            <span className="pms-visually-hidden"> (opens in a new tab)</span>
          </>
        ) : null}
      </a>
    ),
    text,
    blank: false,
  };
}

/**
 * `true`/`false` as words.
 *
 * The string and numeric forms are accepted because a boolean column is exactly where a
 * serialiser's `1`/`0` shows up, and rendering "No" for a truthy `1` would be a silent inversion.
 * Anything unrecognised is treated as false rather than guessed at.
 */
function booleanCell<Row>({ column }: CellArgs<Row>, value: unknown): RenderedCell {
  const [yes, no] = column.words ?? ['Yes', 'No'];
  const on = value === true || value === 'true' || value === 1 || value === '1';
  return plain(on ? yes : no);
}

export function renderCell<Row>(args: CellArgs<Row>): RenderedCell {
  const { column, row, format, rowLabel, onAction } = args;
  const type = columnType(column);

  // Both of these are about the row rather than a value in it, so neither reads one.
  if (type === 'actions') {
    const items = column.actions ? column.actions(row) : [];
    return {
      // An empty verb list renders nothing at all — an always-disabled kebab in every row is
      // noise, and `Menu` already drops `aria-haspopup` when it has nothing to show.
      content:
        items.length === 0 ? null : (
          <Menu
            label={`Actions for ${rowLabel}`}
            items={items}
            onSelect={(id) => onAction?.(id, row)}
          />
        ),
      text: null,
      blank: false,
    };
  }

  if (type === 'custom') {
    return { content: column.render ? column.render(row, format) : null, text: null, blank: false };
  }

  const value = rawValue(column, row);
  // One test for every type, before any of them format anything. A blank boolean is an em dash
  // too — an unset flag is unknown, not "No" — and `false` is not blank, so it still reads "No".
  if (isBlank(value)) return BLANK;

  switch (type) {
    case 'code': {
      const text = asText(value) ?? EM_DASH;
      return { content: <span className="pms-table__code">{text}</span>, text, blank: false };
    }
    case 'money':
      return moneyCell(args, value);
    case 'quantity':
      return plain(format.quantity(asText(value), { precision: column.precision }));
    case 'percent':
      return plain(format.percent(asText(value), column.precision));
    case 'date':
      return plain(format.date(asText(value)));
    case 'datetime':
      return plain(format.dateTime(asText(value)));
    case 'relative': {
      const iso = asText(value);
      const text = format.relative(iso);
      return {
        // `<time>` carries the machine-readable instant, and the absolute value is the tooltip:
        // "3 hours ago" is the right scan target, but an audit reader eventually needs the stamp.
        content: (
          <time dateTime={iso ?? undefined} title={format.dateTime(iso)}>
            {text}
          </time>
        ),
        text,
        blank: false,
      };
    }
    case 'status':
      return statusCell(args, value);
    case 'chips':
      return chipsCell(args, value);
    case 'meter':
      return meterCell(args, value);
    case 'link':
      return linkCell(args, value);
    case 'boolean':
      return booleanCell(args, value);
    case 'masked': {
      // The server sends the tail only — this adds the redaction, it does not
      // perform it, and there is never a full value here to leak.
      const tail = asText(value) ?? '';
      const text = `${MASK}${tail}`;
      return { content: <span className="pms-table__masked">{text}</span>, text, blank: false };
    }
    default:
      return plain(asText(value) ?? EM_DASH);
  }
}
