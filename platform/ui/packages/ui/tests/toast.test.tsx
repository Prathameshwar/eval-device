/**
 * `Toast` — transient status messages floated over the page, driven by `useToast()`.
 *
 * The behaviours worth testing are the ones a reader depends on: every tone renders with its own
 * icon and the right politeness, an error stays until dismissed while a success fades, hovering
 * freezes the countdown, the stack is capped, and the hook refuses to run without a provider.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider, useToast } from '../src/components/Toast';

const OVERLAY_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'overlay.css'), 'utf8');
const TOKENS_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'tokens.css'), 'utf8');

/** A button per API method, so a test drives the hook the way a screen would. */
function Trigger() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast.success('Saved')}>success</button>
      <button onClick={() => toast.error('Payment failed', { title: 'Error' })}>error</button>
      <button onClick={() => toast.warning('Session ends soon')}>warning</button>
      <button onClick={() => toast.info('New rate applied')}>info</button>
      <button onClick={() => toast.info('Quick', { duration: 1000 })}>quick</button>
      <button onClick={() => toast.clear()}>clear</button>
    </>
  );
}

function renderWith(children?: ReactNode) {
  return render(<ToastProvider>{children ?? <Trigger />}</ToastProvider>);
}

const clickButton = (name: string) => fireEvent.click(screen.getByRole('button', { name }));

describe('useToast contract', () => {
  it('throws when used without a provider', () => {
    function Orphan() {
      useToast();
      return null;
    }
    // Silence the boundary's console noise for the expected throw.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Orphan />)).toThrow(/ToastProvider/);
    spy.mockRestore();
  });
});

describe('Toast rendering', () => {
  it('renders each tone with its politeness and floats them in a labelled region', () => {
    renderWith();

    clickButton('success');
    clickButton('error');

    // A confirmation waits its turn; a failure interrupts.
    const success = screen.getByRole('status');
    expect(success).toHaveTextContent('Saved');
    expect(success).toHaveAttribute('data-tone', 'success');

    const error = screen.getByRole('alert');
    expect(error).toHaveTextContent('Payment failed');
    expect(error).toHaveTextContent('Error');
    expect(error).toHaveAttribute('data-tone', 'danger');

    expect(screen.getByRole('region', { name: 'Notifications' })).toBeInTheDocument();
  });

  it('warning interrupts like an error, info waits like a success', () => {
    renderWith();
    clickButton('warning');
    expect(screen.getByRole('alert')).toHaveAttribute('data-tone', 'warning');

    clickButton('info');
    expect(screen.getByRole('status')).toHaveAttribute('data-tone', 'info');
  });

  it('portals the stack to the body, so no ancestor overflow clips it', () => {
    const { container } = renderWith();
    clickButton('info');
    expect(container.querySelector('.pms-toasts')).toBeNull();
    expect(document.body.querySelector('.pms-toasts')).toBeInTheDocument();
  });

  it('carries a dismiss control that removes just that toast', async () => {
    const user = userEvent.setup();
    renderWith();
    clickButton('success');
    clickButton('warning');
    expect(screen.getAllByRole('alert').length + screen.getAllByRole('status').length).toBe(2);

    await user.click(screen.getAllByRole('button', { name: 'Dismiss' })[0] as HTMLElement);
    expect(screen.queryByText('Saved')).not.toBeInTheDocument();
    expect(screen.getByText('Session ends soon')).toBeInTheDocument();
  });

  it('caps the stack and drops the oldest', () => {
    renderWith();
    // The provider default cap is 4.
    clickButton('info');
    clickButton('info');
    clickButton('info');
    clickButton('info');
    clickButton('warning'); // fifth — the first info should be gone
    expect(screen.getAllByText('New rate applied')).toHaveLength(3);
    expect(screen.getByText('Session ends soon')).toBeInTheDocument();
  });

  it('clears every toast at once', () => {
    renderWith();
    clickButton('info');
    clickButton('warning');
    clickButton('clear');
    expect(screen.queryByText('New rate applied')).not.toBeInTheDocument();
    expect(screen.queryByText('Session ends soon')).not.toBeInTheDocument();
  });
});

describe('Toast lifetime', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('auto-dismisses a transient toast after its duration', () => {
    renderWith();
    act(() => clickButton('quick')); // duration: 1000
    expect(screen.getByText('Quick')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(999));
    expect(screen.getByText('Quick')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByText('Quick')).not.toBeInTheDocument();
  });

  it('keeps an error on screen until it is dismissed', () => {
    renderWith();
    act(() => clickButton('error')); // danger → duration null
    act(() => vi.advanceTimersByTime(60_000));
    expect(screen.getByText('Payment failed')).toBeInTheDocument();
  });

  it('freezes the countdown while the pointer is over the toast', () => {
    renderWith();
    act(() => clickButton('quick'));
    const toast = screen.getByRole('status');

    act(() => fireEvent.mouseEnter(toast));
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText('Quick')).toBeInTheDocument();

    // Leaving restarts the clock; the toast then dismisses on the next full duration.
    act(() => fireEvent.mouseLeave(toast));
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.queryByText('Quick')).not.toBeInTheDocument();
  });
});

describe('Toast styling contract', () => {
  it('sits above every other layer on its own token', () => {
    expect(TOKENS_CSS).toMatch(/--pms-z-toast:\s*80/);
    expect(OVERLAY_CSS).toMatch(/\.pms-toasts\s*\{[^}]*z-index: var\(--pms-z-toast\)/);
  });

  it('reuses the tone triple per tone, so a toast and a notice agree on each colour', () => {
    for (const [tone, ink] of [
      ['success', '--pms-success-ink'],
      ['warning', '--pms-warn-ink'],
      ['danger', '--pms-danger-ink'],
    ] as const) {
      expect(OVERLAY_CSS).toMatch(
        new RegExp(`\\.pms-toast\\[data-tone='${tone}'\\][^}]*border-inline-start-color: var\\(${ink}\\)`),
      );
    }
  });

  it('drops the entrance animation under reduced motion', () => {
    expect(OVERLAY_CSS).toMatch(
      /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.pms-toast\s*\{[^}]*animation: none/,
    );
  });
});
