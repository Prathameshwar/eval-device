/**
 * `TableSearch` — the list's `q`.
 *
 * The behaviours here are all about *not* talking to the server: a query below the endpoint's
 * minimum is a 422, a query per keystroke is a scan per keystroke, and a query the field already
 * reported is a round trip that changes nothing. Each of those is a test.
 */
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { TableSearch } from '../src/components/TableSearch';

/**
 * The same clock shim `search-select.test.tsx` documents: RTL's `asyncWrapper` only pumps a fake
 * clock when it recognises jest's, so under Vitest's the first `await user.type` deadlocks.
 */
function installFakeClock() {
  vi.useFakeTimers();
  vi.stubGlobal('jest', { advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms) });
}

describe('TableSearch', () => {
  beforeEach(installFakeClock);
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  const setup = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  /** The timer has to fire *and* React has to flush what it caused. */
  const settle = async (ms = 300) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  };
  it('renders a real label and a search field', () => {
    render(<TableSearch value="" onChange={vi.fn()} hint="Number or customer" />);

    expect(screen.getByLabelText('Search')).toHaveAttribute('type', 'search');
    expect(screen.getByText('Number or customer')).toBeInTheDocument();
  });

  it('reports the query once the typing stops, not once per keystroke', async () => {
    const user = setup();
    const onChange = vi.fn();
    render(<TableSearch value="" onChange={onChange} />);

    await user.type(screen.getByLabelText('Search'), 'north');
    expect(onChange).not.toHaveBeenCalled();

    await settle(300);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('north');
  });

  it('never reports a query shorter than the endpoint minimum, and says why', async () => {
    const user = setup();
    const onChange = vi.fn();
    render(<TableSearch value="" onChange={onChange} />);

    await user.type(screen.getByLabelText('Search'), 'n');
    await settle(1000);

    // A one-character `q` is a 422 from the server, so it is never sent at all.
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText('Type at least 2 characters to search.')).toBeInTheDocument();
  });

  it('trims the query, because the server does and the cursor is signed over the result', async () => {
    const user = setup();
    const onChange = vi.fn();
    render(<TableSearch value="" onChange={onChange} />);

    await user.type(screen.getByLabelText('Search'), '  north  ');
    await settle(300);

    expect(onChange).toHaveBeenCalledWith('north');
  });

  it('applies immediately on Enter rather than waiting out the debounce', async () => {
    const user = setup();
    const onChange = vi.fn();
    render(<TableSearch value="" onChange={onChange} />);

    await user.type(screen.getByLabelText('Search'), 'north{Enter}');

    expect(onChange).toHaveBeenCalledWith('north');

    // And the pending timer does not fire the same query a second time.
    await settle(1000);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('clears the search on Escape', async () => {
    const user = setup();
    const onChange = vi.fn();
    render(<TableSearch value="north" onChange={onChange} />);

    await user.type(screen.getByLabelText('Search'), '{Escape}');

    expect(onChange).toHaveBeenCalledWith('');
    expect(screen.getByLabelText('Search')).toHaveValue('');
  });

  it('offers a clear button only while there is something to clear', async () => {
    const user = setup();
    const onChange = vi.fn();
    render(<TableSearch value="" onChange={onChange} />);

    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Search'), 'north');
    await settle(300);
    await user.click(screen.getByRole('button', { name: 'Clear search' }));

    expect(onChange).toHaveBeenLastCalledWith('');
    expect(screen.getByLabelText('Search')).toHaveValue('');
  });

  it('reports nothing when clearing a query that was never applied', async () => {
    const user = setup();
    const onChange = vi.fn();
    render(<TableSearch value="" onChange={onChange} />);

    // Typed, then abandoned before the debounce elapsed: the list was never narrowed, so widening
    // it again is not a change — and a refetch here would be a page load nobody asked for.
    await user.type(screen.getByLabelText('Search'), 'north');
    await user.click(screen.getByRole('button', { name: 'Clear search' }));
    await settle(1000);

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Search')).toHaveValue('');
  });

  it('adopts a value pushed from outside — a cleared filter set, a URL change', () => {
    const { rerender } = render(<TableSearch value="north" onChange={vi.fn()} />);
    expect(screen.getByLabelText('Search')).toHaveValue('north');

    rerender(<TableSearch value="" onChange={vi.fn()} />);

    expect(screen.getByLabelText('Search')).toHaveValue('');
  });

  it('does not reset what is being typed when the parent echoes the applied query back', async () => {
    const user = setup();
    const onChange = vi.fn();
    // The parent re-renders with the value the field just reported — the ordinary controlled cycle.
    const { rerender } = render(<TableSearch value="" onChange={onChange} />);

    await user.type(screen.getByLabelText('Search'), 'north');
    await settle(300);
    rerender(<TableSearch value="north" onChange={onChange} />);
    await user.type(screen.getByLabelText('Search'), 'wind');

    expect(screen.getByLabelText('Search')).toHaveValue('northwind');
  });

  it('caps the field at the server maximum', () => {
    render(<TableSearch value="" onChange={vi.fn()} />);

    expect(screen.getByLabelText('Search')).toHaveAttribute('maxLength', '200');
  });

  it('stays operable while a search is in flight — a reader may keep refining', () => {
    render(<TableSearch value="north" onChange={vi.fn()} busy />);

    const input = screen.getByLabelText('Search');
    expect(input).toHaveAttribute('aria-busy', 'true');
    expect(input).not.toBeDisabled();
  });
});
