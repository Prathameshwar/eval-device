/**
 * Formatting tests.
 *
 * The point of most of these is not "does it print prettily" — it is that a figure survives the
 * client unchanged: exact decimal rounding, no float coercion at any input length, and a render
 * that does not move when the browser's locale or the machine's timezone does.
 */
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_DISPLAY_CONFIG,
  EM_DASH,
  formatCompact,
  formatDate,
  formatDateTime,
  formatMoney,
  formatPercent,
  formatQuantity,
  formatRange,
  formatRelative,
  groupDigits,
  roundDecimalString,
  type DisplayConfig,
} from '../src/lib/format';

const cfg = (overrides: Partial<DisplayConfig> = {}): DisplayConfig => ({
  ...DEFAULT_DISPLAY_CONFIG,
  ...overrides,
});

const western = cfg({
  currency: 'USD',
  currencySymbol: '$',
  digitGrouping: 'western',
  locale: 'en-US',
  timezone: 'UTC',
});

describe('roundDecimalString', () => {
  describe('half_up', () => {
    it.each([
      ['2.5', 0, '3'],
      ['-2.5', 0, '-3'],
      ['2.4', 0, '2'],
      ['-2.4', 0, '-2'],
      ['2.345', 2, '2.35'],
      ['-2.345', 2, '-2.35'],
      ['2.344', 2, '2.34'],
      ['2.3451', 2, '2.35'],
      ['0.005', 2, '0.01'],
    ])('%s at %i places → %s', (value, places, expected) => {
      expect(roundDecimalString(value, places, 'half_up')).toBe(expected);
    });
  });

  describe('half_even', () => {
    it.each([
      ['2.5', 0, '2'],
      ['3.5', 0, '4'],
      ['-2.5', 0, '-2'],
      ['-3.5', 0, '-4'],
      ['2.345', 2, '2.34'],
      ['2.355', 2, '2.36'],
      // Not a tie: anything past the half breaks it, so it rounds away from zero.
      ['2.3451', 2, '2.35'],
    ])('%s at %i places → %s', (value, places, expected) => {
      expect(roundDecimalString(value, places, 'half_even')).toBe(expected);
    });
  });

  describe('floor and ceil are directional, not magnitude-based', () => {
    it.each([
      ['2.9', 'floor' as const, '2'],
      ['-2.1', 'floor' as const, '-3'],
      ['2.1', 'ceil' as const, '3'],
      ['-2.9', 'ceil' as const, '-2'],
    ])('%s %s → %s', (value, mode, expected) => {
      expect(roundDecimalString(value, 0, mode)).toBe(expected);
    });

    it('does not move an already-exact value in either direction', () => {
      expect(roundDecimalString('-2.000', 0, 'floor')).toBe('-2');
      expect(roundDecimalString('2.000', 0, 'ceil')).toBe('2');
      expect(roundDecimalString('-2.00', 2, 'floor')).toBe('-2.00');
    });
  });

  it('pads when the input carries fewer decimals than requested', () => {
    expect(roundDecimalString('1.5', 4, 'half_up')).toBe('1.5000');
    expect(roundDecimalString('7', 2, 'half_up')).toBe('7.00');
    expect(roundDecimalString('-7', 2, 'half_up')).toBe('-7.00');
    expect(roundDecimalString('7.', 2, 'half_up')).toBe('7.00');
  });

  it('accepts a bare fraction and a leading plus', () => {
    expect(roundDecimalString('.5', 0, 'half_up')).toBe('1');
    expect(roundDecimalString('.5', 0, 'floor')).toBe('0');
    expect(roundDecimalString('-.5', 0, 'half_up')).toBe('-1');
    expect(roundDecimalString('+2.5', 0, 'half_up')).toBe('3');
    expect(roundDecimalString('.125', 2, 'half_up')).toBe('0.13');
  });

  it('leaves an already-exact value untouched at 0 places', () => {
    expect(roundDecimalString('100', 0, 'half_up')).toBe('100');
    expect(roundDecimalString('0', 0, 'half_up')).toBe('0');
    expect(roundDecimalString('0.0000', 4, 'half_up')).toBe('0.0000');
  });

  it('renders a negative that rounds to zero without a sign', () => {
    expect(roundDecimalString('-0.004', 2, 'half_up')).toBe('0.00');
    expect(roundDecimalString('-0.4', 0, 'half_up')).toBe('0');
  });

  it('keeps every digit of a 30-digit input', () => {
    const value = '123456789012345678901234567.891';
    expect(roundDecimalString(value, 2, 'half_up')).toBe('123456789012345678901234567.89');
    expect(roundDecimalString(value, 0, 'ceil')).toBe('123456789012345678901234568');
  });

  it('rounds past Number.MAX_SAFE_INTEGER exactly', () => {
    // Number('9007199254740993.005') is already 9007199254740992 — a float path loses the
    // digit before rounding ever happens.
    expect(roundDecimalString('9007199254740993.005', 2, 'half_up')).toBe('9007199254740993.01');
    expect(Number('9007199254740993.005').toFixed(2)).not.toBe('9007199254740993.01');
  });

  it('rejects malformed input and bad places rather than guessing', () => {
    expect(() => roundDecimalString('abc', 2, 'half_up')).toThrow(RangeError);
    expect(() => roundDecimalString('1e5', 2, 'half_up')).toThrow(RangeError);
    expect(() => roundDecimalString('', 2, 'half_up')).toThrow(RangeError);
    expect(() => roundDecimalString('1.2.3', 2, 'half_up')).toThrow(RangeError);
    expect(() => roundDecimalString('1.2', -1, 'half_up')).toThrow(RangeError);
    expect(() => roundDecimalString('1.2', 1.5, 'half_up')).toThrow(RangeError);
  });
});

describe('groupDigits', () => {
  it.each([
    ['1', '1'],
    ['12', '12'],
    ['123', '123'],
    ['1234', '1,234'],
    ['12345', '12,345'],
    ['123456', '123,456'],
    ['1234567', '1,234,567'],
    ['12345678', '12,345,678'],
    ['-1234567', '-1,234,567'],
  ])('western: %s → %s', (input, expected) => {
    expect(groupDigits(input, 'western')).toBe(expected);
  });

  it.each([
    ['1', '1'],
    ['12', '12'],
    ['123', '123'],
    ['1234', '1,234'],
    ['12345', '12,345'],
    ['123456', '1,23,456'],
    ['1234567', '12,34,567'],
    ['12345678', '1,23,45,678'],
    ['-1234567', '-12,34,567'],
  ])('indian: %s → %s', (input, expected) => {
    expect(groupDigits(input, 'indian')).toBe(expected);
  });

  it('returns a non-numeric input untouched instead of throwing mid-render', () => {
    expect(groupDigits('n/a', 'indian')).toBe('n/a');
  });

  it('takes the group separator from the caller rather than a fixed comma', () => {
    expect(groupDigits('1234567', 'western', '.')).toBe('1.234.567');
    expect(groupDigits('1234567', 'indian', ' ')).toBe('12 34 567');
    expect(groupDigits('-1234567', 'western', '.')).toBe('-1.234.567');
  });
});

describe('formatMoney', () => {
  it('takes a string and returns a string, grouped per config', () => {
    expect(formatMoney('1234567.8900', DEFAULT_DISPLAY_CONFIG)).toBe('₹12,34,567.89');
    expect(formatMoney('1234567.8900', western)).toBe('$1,234,567.89');
  });

  it('formats a long precise figure exactly — no float coercion anywhere in the path', () => {
    expect(formatMoney('9007199254740993.005', DEFAULT_DISPLAY_CONFIG)).toBe(
      '₹9,00,71,99,25,47,40,993.01',
    );
    expect(formatMoney('123456789012345678901234567.891', western)).toBe(
      '$123,456,789,012,345,678,901,234,567.89',
    );
  });

  it('honours each currencyDisplay', () => {
    expect(formatMoney('1234.5', cfg({ currencyDisplay: 'symbol' }))).toBe('₹1,234.50');
    expect(formatMoney('1234.5', cfg({ currencyDisplay: 'code' }))).toBe('1,234.50 INR');
    expect(formatMoney('1234.5', cfg({ currencyDisplay: 'none' }))).toBe('1,234.50');
    expect(formatMoney('1234.5', DEFAULT_DISPLAY_CONFIG, { display: 'code' })).toBe(
      '1,234.50 INR',
    );
  });

  it('falls back to the code when the config carries no symbol', () => {
    expect(formatMoney('1234.5', cfg({ currency: 'BHD', currencySymbol: undefined }))).toBe(
      '1,234.50 BHD',
    );
  });

  it('puts the sign ahead of the symbol', () => {
    expect(formatMoney('-1234.5', DEFAULT_DISPLAY_CONFIG)).toBe('-₹1,234.50');
    expect(formatMoney('-0.001', DEFAULT_DISPLAY_CONFIG)).toBe('₹0.00');
  });

  it('renders an em-dash for no value — "absent" is not "zero"', () => {
    expect(formatMoney(null, DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatMoney(undefined, DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatMoney('', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatMoney('   ', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatMoney('oops', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatMoney('0', DEFAULT_DISPLAY_CONFIG)).toBe('₹0.00');
  });

  it('takes an explicit precision override', () => {
    expect(formatMoney('1234.56789', DEFAULT_DISPLAY_CONFIG, { precision: 4 })).toBe(
      '₹1,234.5679',
    );
    expect(formatMoney('1234.56789', DEFAULT_DISPLAY_CONFIG, { precision: 0 })).toBe('₹1,235');
  });

  it('rounds by the configured mode, not a fixed one', () => {
    expect(formatMoney('2.345', cfg({ roundingMode: 'half_up' }))).toBe('₹2.35');
    expect(formatMoney('2.345', cfg({ roundingMode: 'half_even' }))).toBe('₹2.34');
    expect(formatMoney('2.341', cfg({ roundingMode: 'ceil' }))).toBe('₹2.35');
    expect(formatMoney('2.349', cfg({ roundingMode: 'floor' }))).toBe('₹2.34');
  });

  it('ignores the locale for separators and grouping', () => {
    // A German-locale browser must still see the company's configured rendering.
    expect(formatMoney('1234567.89', cfg({ locale: 'de-DE' }))).toBe('₹12,34,567.89');
  });
});

describe('formatQuantity', () => {
  it('uses quantityPrecision and never attaches a currency', () => {
    expect(formatQuantity('2.5', DEFAULT_DISPLAY_CONFIG)).toBe('2.5000');
    expect(formatQuantity('123456.78901', DEFAULT_DISPLAY_CONFIG)).toBe('1,23,456.7890');
    expect(formatQuantity('2.5', DEFAULT_DISPLAY_CONFIG)).not.toContain('₹');
  });

  it('takes a precision override and an em-dash for no value', () => {
    expect(formatQuantity('2.5', DEFAULT_DISPLAY_CONFIG, { precision: 2 })).toBe('2.50');
    expect(formatQuantity(null, DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatQuantity('0.001', cfg({ quantityPrecision: 0 }))).toBe('0');
  });
});

describe('formatPercent', () => {
  it('formats a percent value at one decimal by default', () => {
    expect(formatPercent('18.55', DEFAULT_DISPLAY_CONFIG)).toBe('18.6%');
    expect(formatPercent('18', DEFAULT_DISPLAY_CONFIG)).toBe('18.0%');
  });

  it('takes an explicit places and groups large values', () => {
    expect(formatPercent('18.55', DEFAULT_DISPLAY_CONFIG, 2)).toBe('18.55%');
    expect(formatPercent('18.55', DEFAULT_DISPLAY_CONFIG, 0)).toBe('19%');
    expect(formatPercent('123456.7', DEFAULT_DISPLAY_CONFIG)).toBe('1,23,456.7%');
    expect(formatPercent('-4.25', DEFAULT_DISPLAY_CONFIG)).toBe('-4.3%');
  });

  it('renders an em-dash for no value', () => {
    expect(formatPercent(null, DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatPercent('nope', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
  });
});

describe('formatCompact', () => {
  it('uses K / M / B for western grouping', () => {
    expect(formatCompact('1000', western)).toBe('1.0K');
    expect(formatCompact('41600', western)).toBe('41.6K');
    expect(formatCompact('41600000', western)).toBe('41.6M');
    expect(formatCompact('1234567890', western)).toBe('1.2B');
  });

  it('uses K / L / Cr for indian grouping', () => {
    expect(formatCompact('1000', DEFAULT_DISPLAY_CONFIG)).toBe('1.0K');
    expect(formatCompact('150000', DEFAULT_DISPLAY_CONFIG)).toBe('1.5L');
    expect(formatCompact('9975000', DEFAULT_DISPLAY_CONFIG)).toBe('99.8L');
    expect(formatCompact('41600000', DEFAULT_DISPLAY_CONFIG)).toBe('4.2Cr');
  });

  it('never renders a crore-scale figure as millions', () => {
    const compact = formatCompact('41600000', DEFAULT_DISPLAY_CONFIG);
    expect(compact).toContain('Cr');
    expect(compact).not.toContain('M');
    expect(compact).not.toBe('41.6M');
  });

  it('does not abbreviate below 1000', () => {
    expect(formatCompact('999', DEFAULT_DISPLAY_CONFIG)).toBe('999.00');
    expect(formatCompact('999.99', western)).toBe('999.99');
    expect(formatCompact('0', DEFAULT_DISPLAY_CONFIG)).toBe('0.00');
    expect(formatCompact('-12', western)).toBe('-12.00');
  });

  it('promotes a tier rather than printing a four-digit abbreviation', () => {
    expect(formatCompact('999999.9', western)).toBe('1.0M');
    expect(formatCompact('999999999.9', western)).toBe('1.0B');
  });

  it('keeps the sign and handles no value', () => {
    expect(formatCompact('-41600000', DEFAULT_DISPLAY_CONFIG)).toBe('-4.2Cr');
    expect(formatCompact(null, DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatCompact('abc', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
  });

  it('abbreviates a figure far past the safe integer range', () => {
    expect(formatCompact('12345678901234567890', western)).toBe('12,345,678,901.2B');
  });
});

/**
 * The resolved display config carries the separators, the symbol side and the negative
 * convention. A company configured with `decimal_separator = ','`
 * seeing `1,234.00` is a wrong-looking figure on every screen, so none of these may be
 * module constants.
 */
describe('separators, symbol side and negative format come from config', () => {
  const german = cfg({
    currency: 'EUR',
    currencySymbol: '€',
    digitGrouping: 'western',
    decimalSeparator: ',',
    groupSeparator: '.',
    currencySymbolPosition: 'suffix',
    locale: 'de-DE',
  });

  it('defaults to the previous behaviour, so no existing caller moves', () => {
    expect(DEFAULT_DISPLAY_CONFIG.decimalSeparator).toBe('.');
    expect(DEFAULT_DISPLAY_CONFIG.groupSeparator).toBe(',');
    expect(DEFAULT_DISPLAY_CONFIG.currencySymbolPosition).toBe('prefix');
    expect(DEFAULT_DISPLAY_CONFIG.negativeFormat).toBe('minus');
  });

  it('honours a comma decimal separator and a dot group separator everywhere', () => {
    expect(formatMoney('1234567.89', german)).toBe('1.234.567,89€');
    expect(formatQuantity('1234.5', german)).toBe('1.234,5000');
    expect(formatPercent('1234.56', german)).toBe('1.234,6%');
    expect(formatCompact('1234567', german)).toBe('1,2M');
    expect(formatCompact('999.99', german)).toBe('999,99');
  });

  it('puts the symbol on the configured side and keeps the code trailing', () => {
    expect(formatMoney('1234.5', cfg({ currencySymbolPosition: 'suffix' }))).toBe('1,234.50₹');
    expect(formatMoney('1234.5', cfg({ currencySymbolPosition: 'prefix' }))).toBe('₹1,234.50');
    expect(
      formatMoney('1234.5', cfg({ currencySymbolPosition: 'suffix', currencyDisplay: 'code' })),
    ).toBe('1,234.50 INR');
    expect(formatMoney('-1234.5', cfg({ currencySymbolPosition: 'suffix' }))).toBe('-1,234.50₹');
  });

  it('wraps a negative in parens — the accounting convention — symbol included', () => {
    const parens = cfg({ negativeFormat: 'parens' });
    expect(formatMoney('-1234', parens)).toBe('(₹1,234.00)');
    expect(formatMoney('-1234', cfg({ negativeFormat: 'parens', currencyDisplay: 'code' }))).toBe(
      '(1,234.00 INR)',
    );
    expect(formatMoney('-1234', cfg({ negativeFormat: 'parens', currencyDisplay: 'none' }))).toBe(
      '(1,234.00)',
    );
    expect(
      formatMoney('-1234', cfg({ negativeFormat: 'parens', currencySymbolPosition: 'suffix' })),
    ).toBe('(1,234.00₹)');
    expect(formatQuantity('-2.5', parens)).toBe('(2.5000)');
    expect(formatPercent('-4.25', parens)).toBe('(4.3%)');
    expect(formatCompact('-41600000', parens)).toBe('(4.2Cr)');
    expect(formatCompact('-12', parens)).toBe('(12.00)');
  });

  it('leaves a positive and a rounds-to-zero figure unwrapped', () => {
    const parens = cfg({ negativeFormat: 'parens' });
    expect(formatMoney('1234', parens)).toBe('₹1,234.00');
    expect(formatMoney('-0.001', parens)).toBe('₹0.00');
    expect(formatQuantity('0', parens)).toBe('0.0000');
  });

  it('returns a string for every configured shape — no float touches a figure', () => {
    for (const config of [german, cfg({ negativeFormat: 'parens' })]) {
      expect(typeof formatMoney('-9007199254740993.005', config)).toBe('string');
    }
    // Exact past 2^53, with the configured separators and the parens convention applied.
    expect(
      formatMoney('-9007199254740993.005', cfg({ negativeFormat: 'parens' })),
    ).toBe('(₹9,00,71,99,25,47,40,993.01)');
  });
});

describe('formatDate and formatDateTime', () => {
  const iso = '2026-03-05T06:00:00Z'; // 11:30 in Asia/Kolkata

  it('supports each pattern token', () => {
    expect(formatDate(iso, DEFAULT_DISPLAY_CONFIG)).toBe('05 Mar 2026');
    expect(formatDate(iso, cfg({ dateFormat: 'yyyy-MM-dd' }))).toBe('2026-03-05');
    expect(formatDate(iso, cfg({ dateFormat: 'd/M/yy' }))).toBe('5/3/26');
    expect(formatDate(iso, cfg({ dateFormat: 'MMMM d, yyyy' }))).toBe('March 5, 2026');
    expect(formatDate(iso, cfg({ dateFormat: 'dd.MM.yyyy' }))).toBe('05.03.2026');
    expect(formatDateTime(iso, DEFAULT_DISPLAY_CONFIG)).toBe('05 Mar 2026, 11:30');
    expect(formatDateTime(iso, cfg({ datetimeFormat: 'yyyy-MM-dd HH:mm:ss' }))).toBe(
      '2026-03-05 11:30:00',
    );
  });

  it('renders the day in the configured timezone, not the machine one', () => {
    const nearMidnightUtc = '2026-09-11T18:30:00Z';
    expect(formatDate(nearMidnightUtc, cfg({ timezone: 'UTC' }))).toBe('11 Sep 2026');
    expect(formatDate(nearMidnightUtc, cfg({ timezone: 'Asia/Kolkata' }))).toBe('12 Sep 2026');
    expect(formatDate(nearMidnightUtc, cfg({ timezone: 'America/New_York' }))).toBe('11 Sep 2026');
    expect(formatDateTime(nearMidnightUtc, cfg({ timezone: 'Asia/Kolkata' }))).toBe(
      '12 Sep 2026, 00:00',
    );
  });

  it('uses a 24-hour clock with midnight as 00, not 24', () => {
    expect(formatDateTime('2026-03-05T18:30:00Z', cfg({ datetimeFormat: 'HH:mm' }))).toBe('00:00');
    expect(formatDateTime('2026-03-05T12:00:00Z', cfg({ datetimeFormat: 'HH:mm' }))).toBe('17:30');
  });

  it('does not consult the locale — a non-en config renders identically', () => {
    const german = cfg({ locale: 'de-DE' });
    const french = cfg({ locale: 'fr-FR' });
    expect(formatDate(iso, german)).toBe(formatDate(iso, DEFAULT_DISPLAY_CONFIG));
    expect(formatDate(iso, cfg({ locale: 'fr-FR', dateFormat: 'MMMM yyyy' }))).toBe('March 2026');
    expect(formatDate(iso, french)).not.toContain('mars');
    expect(formatDateTime(iso, german)).toBe('05 Mar 2026, 11:30');
  });

  it('renders an em-dash rather than "Invalid Date"', () => {
    expect(formatDate('not-a-date', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate(null, DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate(undefined, DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDateTime('nope', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
  });

  it('falls back to UTC for an unknown timezone instead of blanking the field', () => {
    expect(formatDate('2026-09-11T18:30:00Z', cfg({ timezone: 'Not/AZone' }))).toBe('11 Sep 2026');
  });

  it('reads a business date off the string, in every zone', () => {
    // A `posting_date` has no instant, so no zone may move it. Converting one
    // made every company in a negative-UTC-offset zone see a fiscal period start a day early.
    for (const timezone of ['Asia/Kolkata', 'America/New_York', 'UTC', 'Pacific/Kiritimati']) {
      expect(formatDate('2026-07-01', cfg({ timezone }))).toBe('01 Jul 2026');
      expect(formatDate('2026-01-01', cfg({ timezone }))).toBe('01 Jan 2026');
      expect(formatDate('2026-12-31', cfg({ timezone }))).toBe('31 Dec 2026');
    }
  });

  it('renders a date-only value with a zero clock rather than the machine one', () => {
    expect(formatDateTime('2026-07-01', cfg({ timezone: 'America/New_York' }))).toBe(
      '01 Jul 2026, 00:00',
    );
  });

  it('rejects a malformed-but-parseable date instead of rolling it forward', () => {
    // Each of these renders a confident wrong date through `new Date`'s fallback parser.
    expect(formatDate('2026-02-30', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('2026-02-30T00:00:00Z', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('2026-13-01', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('2026-00-10', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('2026-04-00', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('2026-04-31', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('2026', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('2026-07', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('1', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('0', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('2026-7-1', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDateTime('2026-03-05T25:00:00Z', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDateTime('2026-03-05T10:61:00Z', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatRange('2026-02-30', '2026-03-31', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
  });

  it('accepts a real leap day and rejects one that does not exist', () => {
    expect(formatDate('2024-02-29', DEFAULT_DISPLAY_CONFIG)).toBe('29 Feb 2024');
    expect(formatDate('2026-02-29', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('1900-02-29', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatDate('2000-02-29', DEFAULT_DISPLAY_CONFIG)).toBe('29 Feb 2000');
  });

  it('accepts the timestamp shapes the API actually sends', () => {
    expect(formatDateTime('2026-03-05T06:00:00.123456Z', DEFAULT_DISPLAY_CONFIG)).toBe(
      '05 Mar 2026, 11:30',
    );
    expect(formatDateTime('2026-03-05T06:00Z', DEFAULT_DISPLAY_CONFIG)).toBe('05 Mar 2026, 11:30');
    expect(formatDateTime('2026-03-05T11:30:00+05:30', DEFAULT_DISPLAY_CONFIG)).toBe(
      '05 Mar 2026, 11:30',
    );
    expect(formatDateTime('2026-03-05T11:30:00+0530', DEFAULT_DISPLAY_CONFIG)).toBe(
      '05 Mar 2026, 11:30',
    );
    // An offset-less timestamp is UTC, not the machine's zone — timestamps are stored UTC.
    expect(formatDateTime('2026-03-05T06:00:00', cfg({ timezone: 'UTC' }))).toBe(
      '05 Mar 2026, 06:00',
    );
  });

  it('zero-pads a year below 1000 rather than printing three digits', () => {
    expect(formatDate('0005-01-02T00:00:00Z', cfg({ dateFormat: 'yyyy-MM-dd', timezone: 'UTC' }))).toBe(
      '0005-01-02',
    );
    expect(formatDate('0005-01-02', cfg({ dateFormat: 'yyyy-MM-dd' }))).toBe('0005-01-02');
    expect(formatDate('0805-01-02', cfg({ dateFormat: 'yyyy' }))).toBe('0805');
  });

  it('passes a quoted literal through verbatim, tokens inside it included', () => {
    // `date_format` is company-configured, so an admin must not be able to corrupt every date
    // on the page with a word that happens to contain `d` or `M`.
    expect(formatDate('2026-03-05', cfg({ dateFormat: "'day' d MMMM" }))).toBe('day 5 March');
    expect(formatDate('2026-03-05', cfg({ dateFormat: "d 'de' MMMM 'de' yyyy" }))).toBe(
      '5 de March de 2026',
    );
    expect(
      formatDateTime('2026-03-05T06:00:00Z', cfg({ datetimeFormat: "dd MMM yyyy 'at' HH:mm" })),
    ).toBe('05 Mar 2026 at 11:30');
    // A doubled quote is an escaped apostrophe, as in every other pattern language.
    expect(formatDate('2026-03-05', cfg({ dateFormat: "d MMM ''yy" }))).toBe("5 Mar '26");
    // An unterminated run still passes through rather than substituting inside it.
    expect(formatDate('2026-03-05', cfg({ dateFormat: "yyyy 'end of day" }))).toBe(
      '2026 end of day',
    );
  });
});

describe('formatRange', () => {
  it('collapses a same-day range', () => {
    expect(
      formatRange('2026-03-05T01:00:00Z', '2026-03-05T09:00:00Z', DEFAULT_DISPLAY_CONFIG),
    ).toBe('05 Mar 2026');
  });

  it('decides same-day in the configured zone', () => {
    const start = '2026-03-05T18:00:00Z';
    const end = '2026-03-05T19:00:00Z';
    expect(formatRange(start, end, cfg({ timezone: 'UTC' }))).toBe('05 Mar 2026');
    expect(formatRange(start, end, cfg({ timezone: 'Asia/Kolkata' }))).toBe(
      '05 Mar 2026 – 06 Mar 2026',
    );
  });

  it('joins two days with an en-dash', () => {
    expect(
      formatRange('2026-03-05T06:00:00Z', '2026-04-02T06:00:00Z', DEFAULT_DISPLAY_CONFIG),
    ).toBe('05 Mar 2026 – 02 Apr 2026');
  });

  it('renders a date-only fiscal period identically in every zone', () => {
    // The measured defect: `01 Jul – 11 Sep` in Asia/Kolkata but `30 Jun – 10 Sep` in
    // America/New_York, for the same fiscal period bounds.
    const kolkata = cfg({ timezone: 'Asia/Kolkata', dateFormat: 'dd MMM' });
    const newYork = cfg({ timezone: 'America/New_York', dateFormat: 'dd MMM' });
    expect(formatRange('2026-07-01', '2026-09-11', kolkata)).toBe('01 Jul – 11 Sep');
    expect(formatRange('2026-07-01', '2026-09-11', newYork)).toBe('01 Jul – 11 Sep');
    expect(formatRange('2026-07-01', '2026-07-01', newYork)).toBe('01 Jul');
  });

  it('renders an em-dash when either end is missing or invalid', () => {
    expect(formatRange('2026-03-05T06:00:00Z', null, DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatRange(null, '2026-03-05T06:00:00Z', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
    expect(formatRange('nope', 'nope', DEFAULT_DISPLAY_CONFIG)).toBe(EM_DASH);
  });
});

describe('formatRelative', () => {
  // A fixed "now" throughout: relative wording is the one formatter whose output depends on the
  // clock, so every case here injects the instant rather than reading it.
  const NOW = Date.parse('2026-03-05T12:00:00Z');
  const ago = (iso: string, config = DEFAULT_DISPLAY_CONFIG): string =>
    formatRelative(iso, config, NOW);

  it('says "just now" inside the clock-skew window, in either direction', () => {
    expect(ago('2026-03-05T11:59:40Z')).toBe('just now');
    expect(ago('2026-03-05T12:00:00Z')).toBe('just now');
    // A browser clock a few seconds ahead of the server must not print a future timestamp.
    expect(ago('2026-03-05T12:00:30Z')).toBe('just now');
  });

  it('counts minutes and hours, singular and plural', () => {
    expect(ago('2026-03-05T11:59:00Z')).toBe('a minute ago');
    expect(ago('2026-03-05T11:58:00Z')).toBe('2 minutes ago');
    expect(ago('2026-03-05T11:45:00Z')).toBe('15 minutes ago');
    expect(ago('2026-03-05T10:45:00Z')).toBe('an hour ago');
    expect(ago('2026-03-05T09:00:00Z')).toBe('3 hours ago');
  });

  it('words a genuine future instant as "in"', () => {
    expect(ago('2026-03-05T12:20:00Z')).toBe('in 20 minutes');
    expect(ago('2026-03-05T15:00:00Z')).toBe('in 3 hours');
    expect(ago('2026-03-08T12:00:00Z')).toBe('in 3 days');
  });

  it('switches to calendar words past a day', () => {
    expect(ago('2026-03-04T12:00:00Z')).toBe('yesterday');
    expect(ago('2026-03-06T12:00:00Z')).toBe('tomorrow');
    expect(ago('2026-03-01T12:00:00Z')).toBe('4 days ago');
  });

  it('says "yesterday" by the calendar, not by 24 hours', () => {
    // 23:50 yesterday viewed at 00:30 is 40 minutes old, and the minute wording wins.
    const utc = cfg({ timezone: 'UTC' });
    const justAfterMidnight = Date.parse('2026-03-05T00:30:00Z');
    expect(formatRelative('2026-03-04T23:50:00Z', utc, justAfterMidnight)).toBe('40 minutes ago');
    // At 22 hours the hour wording is exhausted but it is still the same calendar day.
    expect(formatRelative('2026-03-05T01:00:00Z', utc, Date.parse('2026-03-05T23:00:00Z'))).toBe(
      '22 hours ago',
    );
  });

  it('decides the calendar day in the configured zone, not the machine one', () => {
    // 18:40 UTC on the 4th is already the 5th in Kolkata but still the 4th in New York, so the
    // same instant is one calendar day back in one zone and two in the other.
    const stamp = '2026-03-04T18:40:00Z';
    const at = Date.parse('2026-03-06T14:00:00Z');
    expect(formatRelative(stamp, cfg({ timezone: 'Asia/Kolkata' }), at)).toBe('yesterday');
    expect(formatRelative(stamp, cfg({ timezone: 'America/New_York' }), at)).toBe('2 days ago');
  });

  it('degrades to an absolute date past a week — "43 days ago" is not actionable', () => {
    expect(ago('2026-03-05T12:00:00Z'.replace('03-05', '02-20'))).toBe('20 Feb 2026');
    expect(ago('2026-02-26T12:00:00Z')).toBe('7 days ago');
    expect(ago('2026-02-25T12:00:00Z')).toBe('25 Feb 2026');
  });

  it('renders a business date absolutely — a calendar date has no elapsed time', () => {
    expect(ago('2026-03-04')).toBe('04 Mar 2026');
    // And identically in every zone, like every other business-date render.
    expect(formatRelative('2026-07-01', cfg({ timezone: 'America/New_York' }), NOW)).toBe(
      '01 Jul 2026',
    );
  });

  it('renders the em-dash for a missing or impossible value', () => {
    expect(ago(null as unknown as string)).toBe(EM_DASH);
    expect(formatRelative(undefined, DEFAULT_DISPLAY_CONFIG, NOW)).toBe(EM_DASH);
    expect(ago('   ')).toBe(EM_DASH);
    expect(ago('2026-02-30T10:00:00Z')).toBe(EM_DASH);
    expect(ago('yesterday-ish')).toBe(EM_DASH);
  });

  it('reads an explicit offset rather than assuming UTC', () => {
    // 17:30+05:30 is 12:00Z — the same instant as "now", so nothing has elapsed.
    expect(ago('2026-03-05T17:30:00+05:30')).toBe('just now');
  });

  it('does not need an injected clock to work', () => {
    expect(formatRelative(new Date().toISOString(), DEFAULT_DISPLAY_CONFIG)).toBe('just now');
  });
});
