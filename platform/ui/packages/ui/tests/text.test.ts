import { describe, expect, it } from 'vitest';
import { pluralNoun, pluralOf } from '../src/lib/text';

/**
 * The plural rule the list surface writes its copy with (`lib/text`).
 *
 * Every noun here is one this platform actually names a resource with — that is the point of the
 * rule set being small: it has to be right for `company`, `tax` and `entry`, and it has to admit
 * that `series` needs telling.
 */

describe('pluralOf', () => {
  it('adds -s to a regular noun', () => {
    expect(pluralOf('row')).toBe('rows');
    expect(pluralOf('invoice')).toBe('invoices');
    expect(pluralOf('customer')).toBe('customers');
    expect(pluralOf('event')).toBe('events');
    expect(pluralOf('item')).toBe('items');
  });

  it('turns a consonant + y into -ies', () => {
    // The reason this file exists: "2 companys selected on this page" shipped from a `${noun}s`.
    expect(pluralOf('company')).toBe('companies');
    expect(pluralOf('entry')).toBe('entries');
    expect(pluralOf('currency')).toBe('currencies');
    expect(pluralOf('country')).toBe('countries');
    expect(pluralOf('category')).toBe('categories');
  });

  it('keeps the y after a vowel', () => {
    expect(pluralOf('day')).toBe('days');
    expect(pluralOf('key')).toBe('keys');
  });

  it('adds -es to a sibilant ending', () => {
    expect(pluralOf('tax')).toBe('taxes');
    expect(pluralOf('address')).toBe('addresses');
    expect(pluralOf('batch')).toBe('batches');
    expect(pluralOf('branch')).toBe('branches');
  });

  it('only ever appends, so a capitalised noun stays capitalised', () => {
    expect(pluralOf('Invoice')).toBe('Invoices');
    expect(pluralOf('Company')).toBe('Companies');
  });

  it('leaves an empty noun alone rather than returning a bare s', () => {
    expect(pluralOf('')).toBe('');
  });
});

describe('pluralNoun', () => {
  it('uses the singular for one and the plural for everything else', () => {
    expect(pluralNoun('invoice', 1)).toBe('invoice');
    expect(pluralNoun('invoice', 2)).toBe('invoices');
  });

  it('treats zero as plural, which is what English does', () => {
    // "No invoices", not "No invoice" — the case a `count > 1` test gets wrong.
    expect(pluralNoun('invoice', 0)).toBe('invoices');
  });

  it('takes an explicit plural for a noun no rule covers', () => {
    /* An invoice series: its plural is itself, and `pluralOf` would say
     * "serieses". A dictionary of exceptions here would be a dictionary to maintain. */
    expect(pluralOf('series')).toBe('serieses');
    expect(pluralNoun('series', 4, 'series')).toBe('series');
    expect(pluralNoun('series', 1, 'series')).toBe('series');
    expect(pluralNoun('person', 3, 'people')).toBe('people');
  });
});
