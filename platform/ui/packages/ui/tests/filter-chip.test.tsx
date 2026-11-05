/**
 * `FilterChip` — one applied predicate, shown above a table.
 *
 * The distinguishing behaviour is naming: eight chips whose remove buttons are all called
 * "Remove" is an unusable control on a screen reader, and a chip row is exactly that case.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { FilterChip } from '../src/components/FilterChip';

const TABLE_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'table.css'), 'utf8');

describe('FilterChip', () => {
  /** The three parts, in DOM order. Spacing is `gap`, so there is no text between them. */
  const parts = (container: HTMLElement): (string | null)[] =>
    [
      '.pms-filter-chip__label',
      '.pms-filter-chip__op',
      '.pms-filter-chip__value',
    ].map((selector) => container.querySelector(selector)?.textContent ?? null);

  it('reads as a sentence: field, operator, value', () => {
    const { container } = render(<FilterChip label="Status" value="Posted" onRemove={vi.fn()} />);

    expect(parts(container)).toEqual(['Status', 'is', 'Posted']);
  });

  it('uses the given operator when the comparison is not equality', () => {
    const { container } = render(
      <FilterChip label="Posted on" operator="on or after" value="01 Apr 2026" onRemove={vi.fn()} />,
    );

    expect(parts(container)).toEqual(['Posted on', 'on or after', '01 Apr 2026']);
  });

  it('names the remove button after the filter it lifts', () => {
    render(<FilterChip label="Status" value="Posted" onRemove={vi.fn()} />);

    expect(
      screen.getByRole('button', { name: 'Remove filter: Status is Posted' }),
    ).toBeInTheDocument();
  });

  it('keeps the operator in the remove button name, since it is the whole difference', () => {
    render(
      <FilterChip label="Total" operator="at least" value="₹1,00,000.00" onRemove={vi.fn()} />,
    );

    expect(
      screen.getByRole('button', { name: 'Remove filter: Total at least ₹1,00,000.00' }),
    ).toBeInTheDocument();
  });

  it('lifts the filter when removed', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(<FilterChip label="Status" value="Posted" onRemove={onRemove} />);

    await user.click(screen.getByRole('button'));

    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it('renders no remove button for a filter the screen forces', () => {
    render(<FilterChip label="Company" value="Northwind Traders" />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('Northwind Traders')).toBeInTheDocument();
  });

  it('truncates the value only — the field and operator stay whole', () => {
    expect(TABLE_CSS).toMatch(/\.pms-filter-chip__value\s*\{[^}]*text-overflow: ellipsis/);
    expect(TABLE_CSS).not.toMatch(/\.pms-filter-chip__label\s*\{[^}]*text-overflow/);
  });

  it('is hit larger than it is painted, so a thumb can drop a filter', () => {
    /* The × glyph is small on purpose — a chip is a label first — but the target it answers to is
     * grown by a transparent overlay rather than by padding, which would push the glyph off centre.
     * `position: relative` is what the overlay is measured against; without it the inset resolves
     * against the chip and the two remove buttons on one row would overlap. */
    expect(TABLE_CSS).toMatch(/\.pms-filter-chip__remove\s*\{[^}]*position: relative/);
    expect(TABLE_CSS).toMatch(
      /\.pms-filter-chip__remove::after\s*\{[^}]*inset: -0\.25rem/,
    );
  });

  it('gives the bar’s own clear a target with height, not just a text baseline', () => {
    // A bare text button is as tall as its line box; on a phone that is a target under 20px.
    expect(TABLE_CSS).toMatch(/\.pms-filter-bar__clear\s*\{[^}]*min-height: 1\.5rem/);
  });
});
