/**
 * `ConfirmDialog` — the step in front of a destructive or irreversible action.
 *
 * The safety behaviours are the ones worth testing: focus starts on Cancel for a destructive
 * action, the typed phrase actually gates Confirm, a busy dialog cannot be dismissed out from
 * under an in-flight request, and a reopened dialog does not still hold the last phrase.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { ConfirmDialog } from '../src/components/ConfirmDialog';

const OVERLAY_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'overlay.css'), 'utf8');

type Overrides = Partial<Parameters<typeof ConfirmDialog>[0]>;

function setup(overrides: Overrides = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <ConfirmDialog
      open
      title="Delete 3 customers?"
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...overrides}
    >
      <p>They will no longer appear in lists. Posted documents keep their reference.</p>
    </ConfirmDialog>,
  );
  return { ...view, onConfirm, onCancel };
}

const confirmButton = () => screen.getByRole('button', { name: 'Confirm' });
const cancelButton = () => screen.getByRole('button', { name: 'Cancel' });

describe('ConfirmDialog rendering', () => {
  it('renders nothing at all when closed', () => {
    const { container } = render(
      <ConfirmDialog open={false} title="Delete?" onConfirm={vi.fn()} onCancel={vi.fn()}>
        <p>body</p>
      </ConfirmDialog>,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('is a modal dialog named by its title and described by its body', () => {
    setup();
    const dialog = screen.getByRole('dialog', { name: 'Delete 3 customers?' });

    expect(dialog).toHaveAttribute('aria-modal', 'true');
    const describedBy = dialog.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)).toHaveTextContent(
      /Posted documents keep their reference/,
    );
  });

  it('portals to the body, so no ancestor overflow can clip it', () => {
    const { container } = setup();
    expect(container.contains(screen.getByRole('dialog'))).toBe(false);
  });

  it('takes the supplied action labels', () => {
    setup({ confirmLabel: 'Delete', cancelLabel: 'Keep them' });
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Keep them' })).toBeInTheDocument();
  });

  it('marks a destructive dialog with a danger badge an ordinary one does not have', () => {
    const { unmount } = setup();
    expect(document.querySelector('.pms-dialog__icon')).toBeNull();
    expect(document.querySelector('.pms-dialog[data-tone="danger"]')).toBeNull();
    unmount();

    setup({ tone: 'danger' });
    const dialog = document.querySelector('.pms-dialog[data-tone="danger"]');
    expect(dialog).toBeInTheDocument();
    // Decorative — the tone is already carried by the copy and the confirm button.
    expect(document.querySelector('.pms-dialog__icon')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('ConfirmDialog focus', () => {
  it('starts on Confirm for an ordinary action', () => {
    setup();
    expect(confirmButton()).toHaveFocus();
  });

  it('starts on Cancel for a destructive one, so a stray Enter dismisses', () => {
    setup({ tone: 'danger' });
    expect(cancelButton()).toHaveFocus();
    expect(confirmButton()).toHaveClass('pms-btn--danger');
  });

  it('starts in the input when a phrase must be typed', () => {
    setup({ confirmPhrase: 'DELETE' });
    expect(screen.getByLabelText(/DELETE/)).toHaveFocus();
  });

  it('traps Tab inside the panel and cycles', async () => {
    const user = userEvent.setup();
    setup();

    // Confirm holds focus and is last in the panel, so Tab wraps to Cancel rather than leaving.
    await user.tab();
    expect(cancelButton()).toHaveFocus();
    await user.tab();
    expect(confirmButton()).toHaveFocus();
    await user.tab({ shift: true });
    expect(cancelButton()).toHaveFocus();
    await user.tab({ shift: true });
    expect(confirmButton()).toHaveFocus();
  });

  it('returns focus to whatever opened it', async () => {
    const user = userEvent.setup();

    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Delete
          </button>
          <ConfirmDialog
            open={open}
            title="Delete?"
            onConfirm={() => setOpen(false)}
            onCancel={() => setOpen(false)}
          >
            <p>body</p>
          </ConfirmDialog>
        </>
      );
    }

    render(<Host />);
    const opener = screen.getByRole('button', { name: 'Delete' });
    await user.click(opener);
    expect(confirmButton()).toHaveFocus();

    await user.click(cancelButton());

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});

describe('ConfirmDialog dismissal', () => {
  it('cancels on Escape', async () => {
    const user = userEvent.setup();
    const { onCancel } = setup();

    await user.keyboard('{Escape}');

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('cancels on a press outside the panel', async () => {
    const user = userEvent.setup();
    const { onCancel } = setup();

    const scrim = document.querySelector('.pms-dialog__scrim');
    await user.click(scrim as Element);

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('cannot be dismissed while the action is in flight', async () => {
    const user = userEvent.setup();
    const { onCancel } = setup({ busy: true });

    await user.keyboard('{Escape}');
    await user.click(document.querySelector('.pms-dialog__scrim') as Element);

    expect(onCancel).not.toHaveBeenCalled();
    expect(cancelButton()).toBeDisabled();
  });
});

describe('ConfirmDialog confirmation', () => {
  it('confirms on click', async () => {
    const user = userEvent.setup();
    const { onConfirm } = setup();

    await user.click(confirmButton());

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('shows a spinner and blocks a second submit while busy', () => {
    setup({ busy: true });
    const confirm = screen.getByRole('button', { name: /Working/ });
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAttribute('aria-busy', 'true');
  });

  it('gates Confirm on the phrase, trimmed and case-insensitively', async () => {
    const user = userEvent.setup();
    const { onConfirm } = setup({ confirmPhrase: 'LOCK FY2026', confirmLabel: 'Lock' });
    const confirm = screen.getByRole('button', { name: 'Lock' });
    const input = screen.getByLabelText(/LOCK FY2026/);

    expect(confirm).toBeDisabled();

    // A partial phrase never enables — the whole thing is the proof of intent.
    await user.type(input, 'LOCK');
    expect(confirm).toBeDisabled();

    // Case and surrounding whitespace do not matter: a caps-lock blocking the right words is only
    // friction, not safety.
    await user.clear(input);
    await user.type(input, '  lock fy2026  ');
    expect(confirm).toBeEnabled();

    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('takes a lowercase delete phrase and enables however it is typed', async () => {
    const user = userEvent.setup();
    const { onConfirm } = setup({
      tone: 'danger',
      confirmPhrase: 'delete',
      confirmLabel: 'Delete',
    });
    const confirm = screen.getByRole('button', { name: 'Delete' });

    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/to confirm/i), 'DELETE');
    expect(confirm).toBeEnabled();

    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('clears the phrase when the dialog closes, so the next one starts locked', async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <ConfirmDialog
        open
        title="Lock FY2026?"
        confirmPhrase="LOCK"
        confirmLabel="Lock"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      >
        <p>body</p>
      </ConfirmDialog>,
    );
    await user.type(screen.getByLabelText(/LOCK/), 'LOCK');
    expect(screen.getByRole('button', { name: 'Lock' })).toBeEnabled();

    const dialog = (open: boolean) => (
      <ConfirmDialog
        open={open}
        title="Lock FY2026?"
        confirmPhrase="LOCK"
        confirmLabel="Lock"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      >
        <p>body</p>
      </ConfirmDialog>
    );
    rerender(dialog(false));
    rerender(dialog(true));

    expect(screen.getByLabelText(/LOCK/)).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Lock' })).toBeDisabled();
  });

  it('keeps the dialog open and announces a failed attempt', () => {
    setup({ error: 'The period is already closed' });

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('The period is already closed');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(confirmButton()).toBeEnabled();
  });
});

describe('ConfirmDialog styling contract', () => {
  it('renders above the scrim but below a popover, so a Select inside it still opens over it', () => {
    expect(OVERLAY_CSS).toMatch(/\.pms-dialog\s*\{[^}]*z-index: var\(--pms-z-drawer\)/);
    expect(OVERLAY_CSS).toMatch(/\.pms-dialog__scrim\s*\{[^}]*background: var\(--pms-scrim\)/);
  });

  it('stacks its actions on a narrow screen rather than splitting them 50/50', () => {
    expect(OVERLAY_CSS).toMatch(
      /@media \(max-width: 30rem\)[\s\S]*\.pms-dialog__actions\s*\{[^}]*flex-direction: column-reverse/,
    );
  });

  it('gives the destructive tone a real treatment, so data-tone is never a dead attribute again', () => {
    expect(OVERLAY_CSS).toMatch(/\.pms-dialog\[data-tone='danger'\]/);
    expect(OVERLAY_CSS).toMatch(
      /\.pms-dialog__icon\s*\{[^}]*background: var\(--pms-danger-tint\)/,
    );
  });
});
