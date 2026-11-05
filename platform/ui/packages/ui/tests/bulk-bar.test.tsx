/**
 * `BulkBar` — what is selected, and what may be done to it.
 *
 * The wording is the behaviour here. `DataTable` scopes a selection to the page in hand and there is
 * deliberately no "select everything matching this query", so the bar has to say **"on this page"**:
 * "12 selected" alone quietly implies the larger set, and a bulk verb read that way is how one
 * mistaken filter becomes forty wrong documents.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { BulkBar } from '../src/components/BulkBar';
import { Button } from '../src/components/Button';
import { DisplayConfigProvider } from '../src/lib/display-config';

const wrap = (node: ReactNode) => render(<DisplayConfigProvider>{node}</DisplayConfigProvider>);

describe('BulkBar', () => {
  it('states the count, the noun and the scope', () => {
    wrap(
      <BulkBar count={12} noun="invoice" onClear={vi.fn()}>
        <Button>Void</Button>
      </BulkBar>,
    );

    expect(screen.getByRole('status')).toHaveTextContent('12 invoices selected on this page');
  });

  it('never claims more than the page', () => {
    wrap(<BulkBar count={50} onClear={vi.fn()} />);

    const text = screen.getByRole('status').textContent ?? '';
    // "50 selected" with no scope would read as the whole result set, which nothing here can select.
    expect(text).toContain('on this page');
    expect(text).not.toMatch(/matching|all rows/i);
  });

  it('agrees with itself about one row', () => {
    wrap(<BulkBar count={1} noun="invoice" onClear={vi.fn()} />);

    expect(screen.getByRole('status')).toHaveTextContent('1 invoice selected on this page');
  });

  it('inflects the noun rather than bolting an s onto it', () => {
    // "2 companys selected" is what a `${noun}s` produces, and `company` is the second resource
    // this platform has. One rule, in `lib/text`, shared with the pager and the table's row count.
    wrap(<BulkBar count={2} noun="company" onClear={vi.fn()} />);

    expect(screen.getByRole('status')).toHaveTextContent('2 companies selected on this page');
  });

  it('takes an explicit plural for a noun no rule covers', () => {
    // An invoice series: its plural is itself, and no rule produces that.
    wrap(<BulkBar count={3} noun="series" nounPlural="series" onClear={vi.fn()} />);

    expect(screen.getByRole('status')).toHaveTextContent('3 series selected on this page');
  });

  it('says "rows" when the screen names nothing more specific', () => {
    // 200 is the page maximum (`LIMIT_MAX`), so the count is stated whole and never abbreviated.
    wrap(<BulkBar count={200} onClear={vi.fn()} />);

    expect(screen.getByRole('status')).toHaveTextContent('200 rows selected on this page');
  });

  it('is absent when nothing is selected, rather than an empty strip', () => {
    const { container } = wrap(<BulkBar count={0} onClear={vi.fn()} />);

    expect(container.querySelector('.pms-bulk-bar')).toBeNull();
  });

  it('announces the count politely — the reader is the one ticking boxes', () => {
    wrap(<BulkBar count={3} onClear={vi.fn()} />);

    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
  });

  it('is a named region, so a screen reader can tell it from the table', () => {
    wrap(<BulkBar count={3} onClear={vi.fn()} />);

    expect(screen.getByRole('region', { name: 'Bulk actions' })).toBeInTheDocument();
  });

  it('renders the screen’s own verbs, and the way out last', () => {
    wrap(
      <BulkBar count={3} onClear={vi.fn()}>
        <Button>Void</Button>
        <Button>Send</Button>
      </BulkBar>,
    );

    const actions = screen.getByRole('region', { name: 'Bulk actions' });
    const labels = within(actions)
      .getAllByRole('button')
      .map((button) => button.textContent);
    expect(labels).toEqual(['Void', 'Send', 'Clear selection']);
  });

  it('reports the way out', async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    wrap(<BulkBar count={3} onClear={onClear} />);

    await user.click(screen.getByRole('button', { name: 'Clear selection' }));

    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('holds every verb while a batch is running, the screen’s own included', () => {
    wrap(
      <BulkBar count={3} onClear={vi.fn()} busy>
        <Button>Void</Button>
      </BulkBar>,
    );

    // A `<fieldset disabled>` really disables its descendants, keyboard and all — so a second press
    // cannot start the same batch twice, and the screen's buttons need not know one is in flight.
    expect(screen.getByRole('button', { name: 'Void' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Clear selection' })).toBeDisabled();
  });

  it('leaves the verbs usable when nothing is running', () => {
    wrap(
      <BulkBar count={3} onClear={vi.fn()}>
        <Button>Void</Button>
      </BulkBar>,
    );

    expect(screen.getByRole('button', { name: 'Void' })).toBeEnabled();
  });
});
