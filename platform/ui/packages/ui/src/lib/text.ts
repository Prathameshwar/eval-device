/**
 * Regular English plural forms for caller-supplied labels used by tables, pagers,
 * and selection controls. Consumers can supply an explicit plural for irregular nouns.
 */

/** Ends in `y` after a consonant: `company`, `entry`, `currency`. `day` and `assay` do not. */
const CONSONANT_Y = /[^aeiou]y$/i;

/** Endings that need the extra syllable: `tax`, `address`, `batch`, `dispatch`, `size`. */
const SIBILANT = /(s|x|z|ch|sh)$/i;

/**
 * The plural of an English noun.
 *
 * Case is preserved by only ever appending — `Invoice` becomes `Invoices`, never `invoices` — so a
 * noun that arrives capitalised for a heading stays that way.
 */
export function pluralOf(noun: string): string {
  if (noun === '') return noun;
  if (CONSONANT_Y.test(noun)) return `${noun.slice(0, -1)}ies`;
  if (SIBILANT.test(noun)) return `${noun}es`;
  return `${noun}s`;
}

/**
 * The noun in the number the count calls for.
 *
 * Only `1` takes the singular: zero is plural in English ("No invoices", "0 rows"), which is the
 * case a naive `count > 1` gets wrong.
 */
export function pluralNoun(noun: string, count: number, plural?: string): string {
  return count === 1 ? noun : (plural ?? pluralOf(noun));
}
