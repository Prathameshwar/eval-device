/**
 * `Notice` — the inline banner.
 *
 * What matters here is that a tone is never *only* a colour, and that how loudly a notice reaches
 * a screen reader is a decision the caller makes rather than an accident of the tone.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Notice } from '../src/components/Notice';
import { Button } from '../src/components/Button';

describe('Notice', () => {
  it('states its tone as data, and carries an icon so colour is not the only signal', () => {
    const { container } = render(<Notice tone="warning">The export is capped at 5,000 rows.</Notice>);

    const notice = container.querySelector('.pms-notice');
    expect(notice).toHaveAttribute('data-tone', 'warning');
    expect(notice?.querySelector('.pms-notice__icon svg')).toBeInTheDocument();
  });

  it('defaults to info', () => {
    const { container } = render(<Notice>Nothing was changed.</Notice>);

    expect(container.querySelector('.pms-notice')).toHaveAttribute('data-tone', 'info');
  });

  it('renders the title above the body', () => {
    render(<Notice title="Your page was reset">The list moved on while you were away.</Notice>);

    expect(screen.getByText('Your page was reset')).toBeInTheDocument();
    expect(screen.getByText('The list moved on while you were away.')).toBeInTheDocument();
  });

  it('interrupts for a danger notice — it has invalidated what the reader was doing', () => {
    render(<Notice tone="danger">Your session ended.</Notice>);

    expect(screen.getByRole('alert')).toHaveTextContent('Your session ended.');
  });

  it('waits its turn for anything else', () => {
    render(<Notice tone="success">Two invoices were posted.</Notice>);

    expect(screen.getByRole('status')).toHaveTextContent('Two invoices were posted.');
  });

  it('announces nothing when told not to — a notice that was there before the reader arrived', () => {
    render(
      <Notice tone="warning" live="off">
        This period is closed.
      </Notice>,
    );

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('This period is closed.')).toBeInTheDocument();
  });

  it('can be made assertive for a tone that is not danger', () => {
    render(
      <Notice tone="warning" live="assertive">
        Permissions changed.
      </Notice>,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Permissions changed.');
  });

  it('renders the way forward as an action', () => {
    render(
      <Notice tone="warning" action={<Button variant="ghost">Start again</Button>}>
        The page you were on expired.
      </Notice>,
    );

    expect(screen.getByRole('button', { name: 'Start again' })).toBeInTheDocument();
  });

  it('is dismissible only when it can be dismissed', async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    const { rerender } = render(<Notice>Nothing to do.</Notice>);

    expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument();

    rerender(<Notice onDismiss={onDismiss}>Nothing to do.</Notice>);
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
