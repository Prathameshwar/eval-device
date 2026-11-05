/**
 * `FilterBar` — what narrows a list, and the account of what currently narrows it.
 *
 * The chip row is the tested behaviour: a filter the reader never chose — from the URL, a saved
 * view, or the screen itself — is exactly the one that makes a record look missing, so every
 * predicate in force has to be visible and every liftable one has to be liftable.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FilterBar, type AppliedFilter } from '../src/components/FilterBar';
import { Button } from '../src/components/Button';

const APPLIED: readonly AppliedFilter[] = [
  { id: 'status', label: 'Status', value: 'Posted' },
  { id: 'posted_from', label: 'Posted on', value: '01 Apr 2026', operator: 'on or after' },
];

describe('FilterBar', () => {
  it('renders the query controls it is given', () => {
    render(
      <FilterBar>
        <span>search box</span>
      </FilterBar>,
    );

    expect(screen.getByText('search box')).toBeInTheDocument();
  });

  it('keeps table controls in their own slot, apart from the query controls', () => {
    const { container } = render(
      <FilterBar actions={<Button variant="ghost">Columns</Button>}>
        <span>search box</span>
      </FilterBar>,
    );

    const actions = container.querySelector('.pms-filter-bar__actions');
    expect(within(actions as HTMLElement).getByRole('button', { name: 'Columns' })).toBeInTheDocument();
    expect(container.querySelector('.pms-filter-bar__controls')).toHaveTextContent('search box');
  });

  it('shows a chip for every predicate in force, operator included', () => {
    render(<FilterBar applied={APPLIED} onRemove={vi.fn()} />);

    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Posted')).toBeInTheDocument();
    // "Posted on 01 Apr 2026" and "Posted on or after 01 Apr 2026" are different filters.
    expect(screen.getByText('on or after')).toBeInTheDocument();
  });

  it('names the chip row, so it is the filters in force rather than a pile of buttons', () => {
    render(<FilterBar applied={APPLIED} onRemove={vi.fn()} />);

    const group = screen.getByRole('group', { name: 'Filters in force' });
    expect(within(group).getAllByRole('button', { name: /^Remove filter/ })).toHaveLength(2);
  });

  it('reports which filter was lifted', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(<FilterBar applied={APPLIED} onRemove={onRemove} />);

    await user.click(screen.getByRole('button', { name: 'Remove filter: Status is Posted' }));

    expect(onRemove).toHaveBeenCalledWith('status');
  });

  it('shows a screen-imposed filter but does not offer to lift it', () => {
    render(
      <FilterBar
        applied={[{ id: 'company', label: 'Company', value: 'Northwind', fixed: true }]}
        onRemove={vi.fn()}
      />,
    );

    // Still stated — the list is narrowed and must say so — but this one is not the reader's to lift.
    expect(screen.getByText('Northwind')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Remove filter/ })).not.toBeInTheDocument();
  });

  it('offers "Clear all" only when more than one filter would actually be lifted', async () => {
    const user = userEvent.setup();
    const onClearAll = vi.fn();
    const { rerender } = render(
      <FilterBar applied={[APPLIED[0] as AppliedFilter]} onRemove={vi.fn()} onClearAll={onClearAll} />,
    );

    // One chip already has its own remove button; a second control doing the same thing is noise.
    expect(screen.queryByRole('button', { name: 'Clear all' })).not.toBeInTheDocument();

    rerender(<FilterBar applied={APPLIED} onRemove={vi.fn()} onClearAll={onClearAll} />);
    await user.click(screen.getByRole('button', { name: 'Clear all' }));

    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it('does not count screen-imposed filters towards "Clear all"', () => {
    render(
      <FilterBar
        applied={[
          { id: 'company', label: 'Company', value: 'Northwind', fixed: true },
          { id: 'scope', label: 'Scope', value: 'Mine', fixed: true },
        ]}
        onRemove={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Clear all' })).not.toBeInTheDocument();
  });

  it('renders no chip row at all when nothing is filtered', () => {
    const { container } = render(<FilterBar onRemove={vi.fn()} />);

    expect(container.querySelector('.pms-filter-bar__chips')).toBeNull();
  });

  it('renders a fixed chip when there is no way to remove anything', () => {
    render(<FilterBar applied={APPLIED} />);

    // No handler means no remove buttons — a screen that has not wired removal must not draw it.
    expect(screen.queryByRole('button', { name: /^Remove filter/ })).not.toBeInTheDocument();
    expect(screen.getByText('Posted')).toBeInTheDocument();
  });
});
