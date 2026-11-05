import { describe, expect, it } from 'vitest';
import { currentYear } from '../src/lib/date';

describe('currentYear', () => {
  it('returns the current year as a number, for a copyright line', () => {
    const year = currentYear();

    expect(typeof year).toBe('number');
    expect(year).toBe(new Date().getFullYear());
    // A sanity band rather than a fixed value: hardcoding a year would make this test a
    // time bomb, and asserting nothing at all would let a `getMonth()` typo through.
    expect(year).toBeGreaterThanOrEqual(2024);
    expect(year).toBeLessThan(2100);
  });
});
