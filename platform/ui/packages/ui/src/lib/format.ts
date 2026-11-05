/**
 * Display formatting for money, quantities and dates.
 *
 * Two rules shape every function here, and both come from the platform contract
 *:
 *
 * 1. **Amounts and quantities are decimal strings, in and out.** Nothing in this module
 *    converts a figure to a JS `number` — rounding and grouping are done with string and
 *    `BigInt` arithmetic. `Number('0.1') + Number('0.2')` is exactly the silent float
 *    coercion the backend's `Decimal` rules exist to prevent, and the client is the last
 *    place it would be caught. (Dates do use numbers: a calendar field is a count, not money.)
 * 2. **Presentation comes from the resolved config, never from the environment.** No
 *    `toLocaleString`, no `Intl.NumberFormat`, no implicit locale or timezone. A browser in
 *    another locale must render the same total, byte for byte, as the PDF worker does.
 *
 * Storage scale for every amount and quantity column is a fixed 4 decimals; the precisions
 * here are *display* scale only and never change a stored value.
 */

export type RoundingMode = 'half_up' | 'half_even' | 'floor' | 'ceil';
export type DigitGrouping = 'western' | 'indian';
export type CurrencyDisplay = 'symbol' | 'code' | 'none';

export type CurrencySymbolPosition = 'prefix' | 'suffix';
/** `parens` is the accounting convention: `(1,234.00)` rather than `-1,234.00`. */
export type NegativeFormat = 'minus' | 'parens';

export type DisplayConfig = {
  currency: string;
  /** Falls back to the code when absent — asking for a symbol must never render nothing. */
  currencySymbol?: string;
  amountPrecision: number;
  quantityPrecision: number;
  roundingMode: RoundingMode;
  dateFormat: string;
  datetimeFormat: string;
  digitGrouping: DigitGrouping;
  currencyDisplay: CurrencyDisplay;
  /** The character between the integer and the fractional part, e.g. `.` or `,`. */
  decimalSeparator: string;
  /** The character between digit groups, e.g. `,` `.` or a space. */
  groupSeparator: string;
  /** Which side of the figure the currency *symbol* sits on. The code always trails. */
  currencySymbolPosition: CurrencySymbolPosition;
  negativeFormat: NegativeFormat;
  timezone: string;
  /** Carried for downstream copy decisions only. This module never formats *from* it. */
  locale: string;
};

/**
 * "No value" and "zero" are different facts in accounting: an unposted invoice total is not
 * ₹0.00. Every formatter renders the em-dash for absent input and never coerces it to zero.
 */
export const EM_DASH = '—';

/** Ranges join with an en-dash, per typographic convention for spans. */
const EN_DASH = '–';

export const DEFAULT_DISPLAY_CONFIG: DisplayConfig = {
  currency: 'INR',
  currencySymbol: '₹',
  amountPrecision: 2,
  quantityPrecision: 4,
  roundingMode: 'half_up',
  dateFormat: 'dd MMM yyyy',
  datetimeFormat: 'dd MMM yyyy, HH:mm',
  digitGrouping: 'indian',
  currencyDisplay: 'symbol',
  decimalSeparator: '.',
  groupSeparator: ',',
  currencySymbolPosition: 'prefix',
  negativeFormat: 'minus',
  timezone: 'Asia/Kolkata',
  locale: 'en-IN',
};

/**
 * The canonical separators of a decimal *string* — the shape `roundDecimalString` speaks and
 * every intermediate value in this module carries. They are swapped for the configured
 * separators at the display boundary only, so no arithmetic ever has to know about a comma.
 *
 * `show_amount_in_words` is deliberately out of scope here: rendering
 * "one lakh twenty thousand" is a language concern, not a numeric-format one, and it belongs
 * with the copy layer rather than with the figure formatter.
 */
const DECIMAL_SEPARATOR = '.';
const GROUP_SEPARATOR = ',';

/* -------------------------------------------------------------------------- */
/* Decimal string arithmetic                                                   */
/* -------------------------------------------------------------------------- */

type ParsedDecimal = {
  negative: boolean;
  /** Integer digits, at least one, possibly with leading zeros. */
  int: string;
  /** Fractional digits, possibly empty. */
  frac: string;
};

/** Deliberately rejects exponent notation: `1e5` is not a shape the money path produces. */
function parseDecimal(value: string): ParsedDecimal | null {
  const match = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(value.trim());
  if (!match) return null;
  const sign = match[1] ?? '';
  const int = match[2] ?? '';
  const frac = match[3] ?? '';
  if (int === '' && frac === '') return null; // '', '.', '-' are not numbers
  return { negative: sign === '-', int: int === '' ? '0' : int, frac };
}

function isAllZeros(digits: string): boolean {
  return /^0*$/.test(digits);
}

/** -1 / 0 / 1 for `0.<rest>` against exactly one half, without building a float. */
function compareRestToHalf(rest: string): -1 | 0 | 1 {
  const first = rest.charCodeAt(0) - 48;
  if (first > 5) return 1;
  if (first < 5) return -1;
  return isAllZeros(rest.slice(1)) ? 0 : 1;
}

type ScaledDecimal = { negative: boolean; scaled: bigint };

function scaleAndRound(value: ParsedDecimal, places: number, mode: RoundingMode): ScaledDecimal {
  if (value.frac.length <= places) {
    return { negative: value.negative, scaled: BigInt(value.int + value.frac.padEnd(places, '0')) };
  }
  const rest = value.frac.slice(places);
  const scaled = BigInt(value.int + value.frac.slice(0, places));
  // `scaled` is the magnitude, so "increment" always means away from zero. That is what makes
  // half_up on -2.5 give -3, and what keeps floor/ceil directional rather than magnitude-based.
  const up = ((): boolean => {
    switch (mode) {
      case 'floor':
        return value.negative && !isAllZeros(rest);
      case 'ceil':
        return !value.negative && !isAllZeros(rest);
      case 'half_up':
        return compareRestToHalf(rest) >= 0;
      case 'half_even': {
        const cmp = compareRestToHalf(rest);
        return cmp > 0 || (cmp === 0 && scaled % 2n === 1n);
      }
    }
  })();
  return { negative: value.negative, scaled: up ? scaled + 1n : scaled };
}

function renderScaled({ negative, scaled }: ScaledDecimal, places: number): string {
  const digits = scaled.toString();
  // A negative that rounds to zero renders as `0.00`: `-0.00` is not a figure anyone wants
  // on an invoice.
  const sign = negative && scaled !== 0n ? '-' : '';
  if (places === 0) return `${sign}${digits}`;
  const padded = digits.padStart(places + 1, '0');
  return `${sign}${padded.slice(0, padded.length - places)}${DECIMAL_SEPARATOR}${padded.slice(-places)}`;
}

/**
 * Round a decimal string to `places` decimals, exactly, via `BigInt`.
 *
 * Pads when the input has fewer decimals than requested, so the output always carries exactly
 * `places` decimals — a column of figures must align. Input length is unbounded: a 30-digit
 * value keeps every digit, where `Number` would have quietly rounded past 2^53.
 *
 * @throws RangeError on a non-decimal string or a negative/fractional `places`.
 */
export function roundDecimalString(value: string, places: number, mode: RoundingMode): string {
  if (!Number.isInteger(places) || places < 0) {
    throw new RangeError(`roundDecimalString: places must be a non-negative integer, got ${places}`);
  }
  const parsed = parseDecimal(value);
  if (!parsed) {
    throw new RangeError(`roundDecimalString: not a decimal string: ${JSON.stringify(value)}`);
  }
  return renderScaled(scaleAndRound(parsed, places, mode), places);
}

/**
 * Group the integer digits of a figure. `western` groups in threes (1,234,567);
 * `indian` groups the last three then twos (12,34,567) — lakh/crore reading, which an Indian
 * user spots as wrong instantly if it comes out western.
 *
 * A non-numeric input is returned untouched: grouping is cosmetic and must not throw mid-render.
 *
 * `separator` comes from the resolved display config and defaults to the
 * canonical comma, so a caller holding a plain decimal string needs no config.
 */
export function groupDigits(
  integerPart: string,
  grouping: DigitGrouping,
  separator: string = GROUP_SEPARATOR,
): string {
  const match = /^([+-]?)(\d+)$/.exec(integerPart.trim());
  if (!match) return integerPart;
  const sign = match[1] === '-' ? '-' : '';
  const digits = match[2] ?? '';
  if (digits.length <= 3) return `${sign}${digits}`;
  if (grouping === 'western') {
    return `${sign}${digits.replace(/\B(?=(\d{3})+(?!\d))/g, separator)}`;
  }
  const last3 = digits.slice(-3);
  const head = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, separator);
  return `${sign}${head}${separator}${last3}`;
}

/**
 * Restate a canonical decimal string with the configured separators. Purely a display step —
 * it runs once, at the end, on a string that has already been rounded and grouped.
 */
function withConfiguredSeparators(canonical: string, config: DisplayConfig): string {
  const [int = canonical, frac] = canonical.split(DECIMAL_SEPARATOR);
  const grouped = groupDigits(int, config.digitGrouping, config.groupSeparator);
  return frac === undefined ? grouped : `${grouped}${config.decimalSeparator}${frac}`;
}

/** Round + group, or `null` when there is nothing to render. Shared by every figure formatter. */
function formatFigure(
  value: string | null | undefined,
  config: DisplayConfig,
  places: number,
): string | null {
  if (value === null || value === undefined || value.trim() === '') return null;
  const parsed = parseDecimal(value);
  if (!parsed) return null;
  const rounded = renderScaled(scaleAndRound(parsed, places, config.roundingMode), places);
  return withConfiguredSeparators(rounded, config);
}

/**
 * Split a formatted figure into its sign and its magnitude, so an affix can be attached
 * *inside* the negative marker: the accounting convention wraps the symbol too — `(₹1,234.00)`,
 * never `-(₹1,234.00)` and never `(₹)1,234.00`.
 */
function splitSign(figure: string): { negative: boolean; magnitude: string } {
  return figure.startsWith('-')
    ? { negative: true, magnitude: figure.slice(1) }
    : { negative: false, magnitude: figure };
}

/** Re-attach the sign in the configured convention, around everything the figure carries. */
function markNegative(body: string, config: DisplayConfig): string {
  return config.negativeFormat === 'parens' ? `(${body})` : `-${body}`;
}

/** Sign-aware assembly: `attach` decorates the magnitude, the sign then wraps the result. */
function signed(
  figure: string,
  config: DisplayConfig,
  attach: (magnitude: string) => string = (magnitude) => magnitude,
): string {
  const { negative, magnitude } = splitSign(figure);
  const body = attach(magnitude);
  return negative ? markNegative(body, config) : body;
}

/* -------------------------------------------------------------------------- */
/* Money, quantity, percent, compact                                           */
/* -------------------------------------------------------------------------- */

export type MoneyOptions = {
  /** Overrides `amountPrecision` for one call site (a unit rate shown at 4, say). */
  precision?: number;
  display?: CurrencyDisplay;
};

export function formatMoney(
  value: string | null | undefined,
  config: DisplayConfig,
  opts?: MoneyOptions,
): string {
  const figure = formatFigure(value, config, opts?.precision ?? config.amountPrecision);
  if (figure === null) return EM_DASH;

  const display = opts?.display ?? config.currencyDisplay;
  // Sign leads the symbol (`-₹1,200.00`, not `₹-1,200.00`) and the parens convention wraps
  // both (`(₹1,200.00)`), which is why the affix is attached to the magnitude.
  if (display === 'none') return signed(figure, config);
  const symbol = config.currencySymbol;
  if (display === 'code' || symbol === undefined || symbol === '') {
    // The code always trails, on either symbol setting: `INR 1,234.50` is not a form the
    // config asks for, and `currency_symbol_position` names the symbol.
    return signed(figure, config, (magnitude) => `${magnitude} ${config.currency}`);
  }
  return signed(figure, config, (magnitude) =>
    config.currencySymbolPosition === 'suffix' ? `${magnitude}${symbol}` : `${symbol}${magnitude}`,
  );
}

export function formatQuantity(
  value: string | null | undefined,
  config: DisplayConfig,
  opts?: { precision?: number },
): string {
  const figure = formatFigure(value, config, opts?.precision ?? config.quantityPrecision);
  return figure === null ? EM_DASH : signed(figure, config);
}

/**
 * Formats a percentage *value* — `'18.5'` renders as `18.5%`, matching how rates and shares
 * are stored (a percent, not a 0–1 ratio). One decimal by default: on a tile, `12.3%` reads
 * and `12.34%` does not.
 */
export function formatPercent(
  value: string | null | undefined,
  config: DisplayConfig,
  places = 1,
): string {
  const figure = formatFigure(value, config, places);
  return figure === null ? EM_DASH : signed(figure, config, (magnitude) => `${magnitude}%`);
}

/** Divide by 10^n by moving the point, so no float ever touches the figure. */
function shiftPointLeft(value: ParsedDecimal, n: number): string {
  const digits = value.int + value.frac;
  const point = value.int.length - n;
  const sign = value.negative ? '-' : '';
  if (point <= 0) return `${sign}0${DECIMAL_SEPARATOR}${'0'.repeat(-point)}${digits}`;
  // `n` is always at least 3 here, so there are digits left of the point and digits right of it.
  return `${sign}${digits.slice(0, point)}${DECIMAL_SEPARATOR}${digits.slice(point)}`;
}

type CompactTier = { exponent: number; suffix: string };

const WESTERN_TIERS: readonly CompactTier[] = [
  { exponent: 9, suffix: 'B' },
  { exponent: 6, suffix: 'M' },
  { exponent: 3, suffix: 'K' },
];

// A product used in India must not render 4.16 crore as "41.6M" — lakh and crore are the
// units its users count in, so the tier ladder is part of the display config, not a locale guess.
const INDIAN_TIERS: readonly CompactTier[] = [
  { exponent: 7, suffix: 'Cr' },
  { exponent: 5, suffix: 'L' },
  { exponent: 3, suffix: 'K' },
];

function significantIntDigits(int: string): number {
  const stripped = int.replace(/^0+/, '');
  return stripped.length;
}

/** Abbreviated figure for a KPI tile. One decimal; nothing below 1000 is abbreviated. */
export function formatCompact(value: string | null | undefined, config: DisplayConfig): string {
  if (value === null || value === undefined || value.trim() === '') return EM_DASH;
  const parsed = parseDecimal(value);
  if (!parsed) return EM_DASH;

  const tiers = config.digitGrouping === 'indian' ? INDIAN_TIERS : WESTERN_TIERS;
  const digits = significantIntDigits(parsed.int);
  const index = tiers.findIndex((candidate) => digits > candidate.exponent);
  const matched = index === -1 ? undefined : tiers[index];
  if (!matched) {
    const plain = formatFigure(value, config, config.amountPrecision);
    return plain === null ? EM_DASH : signed(plain, config);
  }

  const at = (candidate: CompactTier): string =>
    roundDecimalString(shiftPointLeft(parsed, candidate.exponent), 1, config.roundingMode);
  const overflows = (figure: string): boolean =>
    significantIntDigits(figure.replace('-', '').split(DECIMAL_SEPARATOR)[0] ?? '') > 3;

  let tier = matched;
  let rounded = at(tier);
  // 999.96M would otherwise print as "1000.0M"; rounding can promote a value one tier up.
  const bigger = tiers[index - 1];
  if (bigger && overflows(rounded)) {
    tier = bigger;
    rounded = at(tier);
  }
  const suffix = tier.suffix;
  return signed(
    withConfiguredSeparators(rounded, config),
    config,
    (magnitude) => `${magnitude}${suffix}`,
  );
}

/* -------------------------------------------------------------------------- */
/* Dates                                                                       */
/* -------------------------------------------------------------------------- */

const MONTHS_SHORT = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const;

const MONTHS_LONG = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;

type CalendarParts = {
  year: number;
  /** 1–12. */
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

// One `Intl.DateTimeFormat` per zone, reused: a 500-row ledger would otherwise construct 500.
const zoneFormatters = new Map<string, Intl.DateTimeFormat>();

function formatterFor(timezone: string): Intl.DateTimeFormat {
  const cached = zoneFormatters.get(timezone);
  if (cached) return cached;
  const options: Intl.DateTimeFormatOptions = {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  };
  // 'en-US' is a fixed part-extraction locale, not a display locale: only the numeric parts are
  // read out, and month names come from our own table — so a machine in another locale cannot
  // change a rendered date. An unknown zone falls back to UTC rather than blanking the field.
  let formatter: Intl.DateTimeFormat;
  try {
    formatter = new Intl.DateTimeFormat('en-US', options);
  } catch {
    formatter = new Intl.DateTimeFormat('en-US', { ...options, timeZone: 'UTC' });
  }
  zoneFormatters.set(timezone, formatter);
  return formatter;
}

/**
 * A **business date** — `posting_date`, `document_date`, a fiscal period bound — is a calendar
 * date with no instant attached, so converting one through a timezone is not
 * merely lossy, it is meaningless: there is no moment to convert. `new Date('2026-07-01')` is
 * UTC midnight, and reading that back in `America/New_York` gives 30 June — every company on a
 * negative UTC offset saw its fiscal period start a day early. A date-only string is therefore
 * read straight off the string and never sees a zone.
 */
const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * An instant. The shape is required *before* `new Date` sees the string, because the legacy
 * fallback parser accepts `'2026'` (→ 01 Jan 2026), `'1'` (→ 01 Jan 2001) and `'0'`
 * (→ 01 Jan 2000) and answers with a confident wrong date. Seconds, fractional seconds and the
 * offset are optional; a missing offset is UTC, not the machine's zone, because timestamps
 * cross the wire in UTC and a render must not move with the machine.
 */
const DATE_TIME =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,9})?)?(Z|[+-]\d{2}:?\d{2})?$/;

/**
 * Is this a date that exists? V8 rolls `2026-02-30` forward into March rather than rejecting
 * it — exactly what a bad importer or a hand-edited payload produces — so the extracted fields
 * are round-tripped: silently showing 02 Mar for a stored 30 Feb is worse than showing nothing.
 */
function isRealDate(year: number, month: number, day: number): boolean {
  if (month < 1 || month > 12 || day < 1 || day > 31) return false;
  // `setUTCFullYear`, not `Date.UTC`, which maps years 0–99 onto 1900–1999.
  const probe = new Date(0);
  probe.setUTCFullYear(year, month - 1, day);
  probe.setUTCHours(0, 0, 0, 0);
  return (
    probe.getUTCFullYear() === year && probe.getUTCMonth() === month - 1 && probe.getUTCDate() === day
  );
}

function calendarParts(iso: string | null | undefined, timezone: string): CalendarParts | null {
  if (iso === null || iso === undefined) return null;
  const text = iso.trim();
  if (text === '') return null;

  const dateOnly = DATE_ONLY.exec(text);
  if (dateOnly) {
    const [, yyyy = '', mm = '', dd = ''] = dateOnly;
    const year = Number(yyyy);
    const month = Number(mm);
    const day = Number(dd);
    if (!isRealDate(year, month, day)) return null;
    return { year, month, day, hour: 0, minute: 0, second: 0 };
  }

  const stamp = DATE_TIME.exec(text);
  if (!stamp) return null;
  const [, yyyy = '', mm = '', dd = '', HH = '', min = '', ss = '0', offset] = stamp;
  if (!isRealDate(Number(yyyy), Number(mm), Number(dd))) return null;
  if (Number(HH) > 23 || Number(min) > 59 || Number(ss) > 59) return null;

  const date = new Date(offset === undefined ? `${text}Z` : text);
  if (Number.isNaN(date.getTime())) return null;

  const found: Partial<Record<Intl.DateTimeFormatPartTypes, string>> = {};
  for (const part of formatterFor(timezone).formatToParts(date)) {
    found[part.type] = part.value;
  }
  const read = (type: Intl.DateTimeFormatPartTypes): number => Number(found[type] ?? '0');
  return {
    year: read('year'),
    month: read('month'),
    day: read('day'),
    hour: read('hour'),
    minute: read('minute'),
    second: read('second'),
  };
}

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

/**
 * A quoted run comes first in the alternation, so a literal is matched before any token inside
 * it can be. `date_format` is company-configured: without an escape mechanism, an admin typing
 * `'day' d MMMM` corrupted every date on the page (`'5ay' 5 March`). The closing quote is
 * optional so an unterminated run passes through verbatim rather than reverting to
 * substitution, and `''` is an escaped apostrophe, as in every other pattern language.
 */
const TOKENS = /'[^']*'?|yyyy|yy|MMMM|MMM|MM|M|dd|d|HH|mm|ss/g;

/** The content of a quoted run, without its quotes. */
function unquote(token: string): string {
  const end = token.length > 1 && token.endsWith("'") ? token.length - 1 : token.length;
  const inner = token.slice(1, end);
  // `''` (and a lone stray quote) renders one apostrophe.
  return inner === '' ? "'" : inner;
}

/** One pass with a replacer, so a substituted month name can never be re-scanned as a token. */
function applyPattern(pattern: string, parts: CalendarParts): string {
  return pattern.replace(TOKENS, (token) => {
    if (token.startsWith("'")) return unquote(token);
    switch (token) {
      case 'yyyy':
        // Padded: a year below 1000 must not print three digits into a `yyyy-MM-dd` slot.
        return String(parts.year).padStart(4, '0');
      case 'yy':
        return pad2(parts.year % 100);
      case 'MMMM':
        return MONTHS_LONG[parts.month - 1] ?? '';
      case 'MMM':
        return MONTHS_SHORT[parts.month - 1] ?? '';
      case 'MM':
        return pad2(parts.month);
      case 'M':
        return String(parts.month);
      case 'dd':
        return pad2(parts.day);
      case 'd':
        return String(parts.day);
      case 'HH':
        return pad2(parts.hour);
      case 'mm':
        return pad2(parts.minute);
      case 'ss':
        return pad2(parts.second);
      default:
        return token;
    }
  });
}

/**
 * A date. Two accepted shapes, and the difference is the point:
 *
 * - `YYYY-MM-DD` — a **business date**. Rendered exactly as stored, in every timezone. Pass
 *   `posting_date` and friends in this form; appending `T00:00:00Z` to one turns a calendar
 *   date into an instant and re-introduces the day shift.
 * - a full ISO timestamp — an instant, rendered in `config.timezone`.
 *
 * Anything else — including a date that does not exist, like `2026-02-30` — renders the em-dash.
 */
export function formatDate(iso: string | null | undefined, config: DisplayConfig): string {
  const parts = calendarParts(iso, config.timezone);
  return parts === null ? EM_DASH : applyPattern(config.dateFormat, parts);
}

export function formatDateTime(iso: string | null | undefined, config: DisplayConfig): string {
  const parts = calendarParts(iso, config.timezone);
  return parts === null ? EM_DASH : applyPattern(config.datetimeFormat, parts);
}

/**
 * The instant a timestamp names, in epoch milliseconds — or `null` for anything that is not a
 * timestamp, a business date included. A calendar date has no instant, so there is no elapsed
 * time to measure from it.
 */
function instantOf(iso: string, timezone: string): number | null {
  const stamp = DATE_TIME.exec(iso);
  if (!stamp) return null;
  // Re-validating through `calendarParts` rather than trusting the regex: it is the one place
  // that rejects 30 February and an out-of-range hour.
  if (calendarParts(iso, timezone) === null) return null;
  const offset = stamp[7];
  const date = new Date(offset === undefined ? `${iso}Z` : iso);
  const time = date.getTime();
  return Number.isNaN(time) ? null : time;
}

/** A calendar day as a single integer, so "yesterday" is a day difference and not 24 hours. */
function dayNumber(parts: CalendarParts): number {
  const probe = new Date(0);
  probe.setUTCFullYear(parts.year, parts.month - 1, parts.day);
  probe.setUTCHours(0, 0, 0, 0);
  return Math.round(probe.getTime() / 86_400_000);
}

const MINUTE_MS = 60_000;
const HOUR_MS = 3_600_000;

/** How far back relative wording stays useful. Past that, `formatDate` is the honest answer. */
const RELATIVE_DAY_LIMIT = 7;

function agoPhrase(count: number, unit: string, future: boolean): string {
  const quantity = `${count} ${unit}${count === 1 ? '' : 's'}`;
  return future ? `in ${quantity}` : `${quantity} ago`;
}

/**
 * Elapsed time in words — the `created_at` / `updated_at` column of an audit or activity list.
 *
 * Three deliberate constraints:
 *
 * - **English from our own table, not `Intl.RelativeTimeFormat`.** Same rule as every other
 *   formatter here: the machine's locale must not change what is rendered.
 * - **Only ever an accompaniment.** "3 hours ago" is unusable for reconciling against a bank
 *   statement, so a caller pairs this with the absolute `formatDateTime` in a `title` — never
 *   shows it alone.
 * - **It stops at a week.** Beyond that it degrades to `formatDate`; "43 days ago" is a figure
 *   nobody can act on, and counting months and years drifts by leap day.
 *
 * A small clock difference between the browser and the server reads as "just now" in either
 * direction rather than as a timestamp from the future.
 *
 * @param now Injected for determinism in tests; defaults to the current instant.
 */
export function formatRelative(
  iso: string | null | undefined,
  config: DisplayConfig,
  now: number = Date.now(),
): string {
  if (iso === null || iso === undefined) return EM_DASH;
  const text = iso.trim();
  const instant = text === '' ? null : instantOf(text, config.timezone);
  // A business date, or a malformed value: `formatDate` renders the one and em-dashes the other.
  if (instant === null) return formatDate(iso, config);

  const elapsed = now - instant;
  const future = elapsed < 0;
  const magnitude = Math.abs(elapsed);

  if (magnitude < 45_000) return 'just now';
  if (magnitude < 90_000) return future ? 'in a minute' : 'a minute ago';
  if (magnitude < 45 * MINUTE_MS) {
    return agoPhrase(Math.round(magnitude / MINUTE_MS), 'minute', future);
  }
  if (magnitude < 90 * MINUTE_MS) return future ? 'in an hour' : 'an hour ago';
  if (magnitude < 22 * HOUR_MS) {
    return agoPhrase(Math.round(magnitude / HOUR_MS), 'hour', future);
  }

  // Past a day, wording follows the calendar in the configured zone: at 00:30 an event from
  // 23:00 is 90 minutes old but it is still "yesterday", and that is what a user is looking for.
  const then = calendarParts(text, config.timezone);
  const today = calendarParts(new Date(now).toISOString(), config.timezone);
  if (then === null || today === null) return formatDate(iso, config);
  const days = dayNumber(today) - dayNumber(then);

  // 01:00 and 23:00 are 22 hours apart and the same calendar day, so the hour wording has to
  // remain reachable here — "0 days ago" is not a sentence.
  if (days === 0) return agoPhrase(Math.round(magnitude / HOUR_MS), 'hour', future);
  if (days === 1) return 'yesterday';
  if (days === -1) return 'tomorrow';
  if (Math.abs(days) <= RELATIVE_DAY_LIMIT) return agoPhrase(Math.abs(days), 'day', days < 0);
  return formatDate(iso, config);
}

/**
 * A date span. Collapses to a single date when both ends fall on the same day *in the configured
 * zone*. Either end missing or invalid gives an em-dash: half a range is a misleading range.
 */
export function formatRange(
  startIso: string | null | undefined,
  endIso: string | null | undefined,
  config: DisplayConfig,
): string {
  const start = calendarParts(startIso, config.timezone);
  const end = calendarParts(endIso, config.timezone);
  if (start === null || end === null) return EM_DASH;
  const sameDay =
    start.year === end.year && start.month === end.month && start.day === end.day;
  const from = applyPattern(config.dateFormat, start);
  return sameDay ? from : `${from} ${EN_DASH} ${applyPattern(config.dateFormat, end)}`;
}
