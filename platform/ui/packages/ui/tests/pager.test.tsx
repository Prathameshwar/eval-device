/**
 * `Pager` — one step either way, and the range in hand.
 *
 * The absent features are the point: keyset paging returns no total,
 * so there are no page numbers and no "of 1,240". These tests assert that absence, because it is
 * the thing a well-meaning change would put back.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Pager } from '../src/components/Pager';

const props = {
  count: 50,
  limit: 50,
  hasPrevious: false,
  hasNext: true,
  onPrevious: vi.fn(),
  onNext: vi.fn(),
};

describe('Pager', () => {
  it('states the range of the page in hand', () => {
    render(<Pager {...props} from={51} />);

    expect(screen.getByRole('status')).toHaveTextContent('Showing 51–100');
  });

  it('groups the digits the way the reader is configured to read them, not the way JS defaults', () => {
    render(<Pager {...props} from={100001} count={50} />);

    // Indian grouping is the platform default, so this is 1,00,001.
    expect(screen.getByRole('status')).toHaveTextContent('Showing 1,00,001–1,00,050');
  });

  it('never states a total, because a keyset list has no count to state', () => {
    render(<Pager {...props} from={51} />);

    const range = screen.getByRole('status').textContent ?? '';
    expect(range).not.toMatch(/of\s/);
    // And no page numbers: "Page 2" would need the count as well.
    expect(screen.queryByRole('button', { name: /page 2/i })).not.toBeInTheDocument();
  });

  it('states the count alone when the position in the walk is unknown', () => {
    // A page reached from a cursor handed over in a URL: the rows are real, the offset is not known.
    render(<Pager {...props} from={null} count={7} noun="event" />);

    expect(screen.getByRole('status')).toHaveTextContent('Showing 7 events');
  });

  it('says so when the page is empty rather than showing a range of nothing', () => {
    render(<Pager {...props} count={0} from={1} hasNext={false} />);

    expect(screen.getByRole('status')).toHaveTextContent('No rows');
  });

  it('announces the range politely — the reader asked for the page', () => {
    render(<Pager {...props} from={1} />);

    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
  });

  it('holds the step back on the first page and the step forward on the last', () => {
    const { rerender } = render(<Pager {...props} from={1} />);

    expect(screen.getByRole('button', { name: 'Previous page of rows' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page of rows' })).toBeEnabled();

    rerender(<Pager {...props} from={51} hasPrevious hasNext={false} />);

    expect(screen.getByRole('button', { name: 'Previous page of rows' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Next page of rows' })).toBeDisabled();
  });

  it('names the steps by what is being paged', () => {
    render(<Pager {...props} from={1} noun="invoice" />);

    expect(screen.getByRole('button', { name: 'Next page of invoices' })).toBeInTheDocument();
  });

  it('reports each step', async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    const onPrevious = vi.fn();
    render(<Pager {...props} from={51} hasPrevious onNext={onNext} onPrevious={onPrevious} />);

    await user.click(screen.getByRole('button', { name: 'Next page of rows' }));
    await user.click(screen.getByRole('button', { name: 'Previous page of rows' }));

    expect(onNext).toHaveBeenCalledTimes(1);
    expect(onPrevious).toHaveBeenCalledTimes(1);
  });

  it('holds both directions while a page is in flight, so a double press cannot skip one', () => {
    render(<Pager {...props} from={51} hasPrevious busy />);

    expect(screen.getByRole('button', { name: 'Previous page of rows' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page of rows' })).toBeDisabled();
  });

  it('offers a page size only when the screen accepts one', async () => {
    const user = userEvent.setup();
    const onLimitChange = vi.fn();
    const { rerender } = render(<Pager {...props} from={1} />);

    expect(screen.queryByLabelText('Rows per page')).not.toBeInTheDocument();

    rerender(<Pager {...props} from={1} onLimitChange={onLimitChange} />);
    await user.selectOptions(screen.getByLabelText('Rows per page'), '100');

    expect(onLimitChange).toHaveBeenCalledWith(100);
  });

  it('inflects the noun in every sentence it writes, not just the count', () => {
    /* Four strings carry the noun here — the range, the empty range and both button labels — and
     * each one had its own `${noun}s`. `company` is enough to prove the rule is shared (`lib/text`). */
    render(<Pager {...props} count={0} noun="company" from={null} />);

    expect(screen.getByRole('status')).toHaveTextContent('No companies');
    expect(screen.getByRole('button', { name: 'Previous page of companies' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next page of companies' })).toBeInTheDocument();
  });

  it('agrees with a count of one, and takes an explicit plural where no rule fits', () => {
    const { rerender } = render(<Pager {...props} count={1} noun="company" from={null} />);
    expect(screen.getByRole('status')).toHaveTextContent('1 company');

    // An invoice series pluralises to itself; the rule would say "serieses".
    rerender(<Pager {...props} count={4} noun="series" nounPlural="series" from={null} />);
    expect(screen.getByRole('status')).toHaveTextContent('4 series');
    expect(screen.getByRole('button', { name: 'Next page of series' })).toBeInTheDocument();
  });

  it('cannot be made to offer a page past the server ceiling', () => {
    render(<Pager {...props} from={1} onLimitChange={vi.fn()} limitOptions={[50, 500]} />);

    // 500 would be a 422 on the first request, not a bigger page.
    expect(screen.getByLabelText('Rows per page')).not.toHaveTextContent('500');
    expect(screen.getByRole('option', { name: '50 per page' })).toBeInTheDocument();
  });
});
