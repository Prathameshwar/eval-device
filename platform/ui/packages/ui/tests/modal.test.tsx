/**
 * `Modal` — the centred overlay container for a focused task, on the shared `useDialogA11y`
 * mechanism. The behaviours worth testing are the accessible-dialog contract, the three dismissal
 * paths and when each is blocked, the focus trap and restore, and the body scroll lock.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { useState, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { Modal } from '../src/components/Overlay';
import { Button } from '../src/components/Button';

const OVERLAY_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'overlay.css'), 'utf8');

type Overrides = Partial<Parameters<typeof Modal>[0]>;

function setup(overrides: Overrides = {}) {
  const onClose = vi.fn();
  const view = render(
    <Modal open title="New customer" onClose={onClose} {...overrides}>
      <p>Enter the customer's details.</p>
    </Modal>,
  );
  return { ...view, onClose };
}

const closeButton = () => screen.getByRole('button', { name: 'Close' });
const scrim = () => document.querySelector('.pms-modal__scrim') as Element;

describe('Modal rendering', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <Modal open={false} title="New customer" onClose={vi.fn()}>
        <p>body</p>
      </Modal>,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('is a modal dialog named by its title and described by its body', () => {
    setup();
    const dialog = screen.getByRole('dialog', { name: 'New customer' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    const describedBy = dialog.getAttribute('aria-describedby');
    expect(document.getElementById(describedBy as string)).toHaveTextContent(
      /Enter the customer's details/,
    );
  });

  it('portals to the body, so no ancestor overflow clips it', () => {
    const { container } = setup();
    expect(container.contains(screen.getByRole('dialog'))).toBe(false);
    expect(document.body.querySelector('.pms-modal')).toBeInTheDocument();
  });

  it('renders a footer and reflects the size', () => {
    setup({ size: 'lg', footer: <Button>Save</Button> });
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(document.querySelector('.pms-modal__panel')).toHaveAttribute('data-size', 'lg');
  });
});

describe('Modal dismissal', () => {
  it('closes from the header button, the scrim and Escape', async () => {
    const user = userEvent.setup();

    const a = setup();
    await user.click(closeButton());
    expect(a.onClose).toHaveBeenCalledTimes(1);
    a.unmount();

    const b = setup();
    await user.click(scrim());
    expect(b.onClose).toHaveBeenCalledTimes(1);
    b.unmount();

    const c = setup();
    await user.keyboard('{Escape}');
    expect(c.onClose).toHaveBeenCalledTimes(1);
  });

  it('is non-dismissible when asked: no close button, and scrim and Escape do nothing', async () => {
    const user = userEvent.setup();
    const { onClose } = setup({ dismissible: false });

    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
    await user.click(scrim());
    await user.keyboard('{Escape}');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('blocks every dismissal while busy, and disables the close button', async () => {
    const user = userEvent.setup();
    const { onClose } = setup({ busy: true });

    expect(closeButton()).toBeDisabled();
    await user.click(scrim());
    await user.keyboard('{Escape}');
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('Modal focus', () => {
  it('traps Tab inside the panel and cycles', async () => {
    const user = userEvent.setup();
    setup({ footer: <Button>Save</Button> });
    // Close (first focusable) → Save (last). Tab past the end wraps back to Close.
    const close = closeButton();
    const save = screen.getByRole('button', { name: 'Save' });

    close.focus();
    await user.tab();
    expect(save).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(save).toHaveFocus();
  });

  it('returns focus to whatever opened it', async () => {
    const user = userEvent.setup();

    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Open
          </button>
          <Modal open={open} title="New customer" onClose={() => setOpen(false)}>
            <p>body</p>
          </Modal>
        </>
      );
    }

    render(<Host />);
    const opener = screen.getByRole('button', { name: 'Open' });
    await user.click(opener);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.click(closeButton());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});

describe('Modal scroll lock', () => {
  it('locks body scroll while open and restores it on close', () => {
    function Host({ open }: { open: boolean }) {
      return (
        <Modal open={open} title="New customer" onClose={vi.fn()}>
          <p>body</p>
        </Modal>
      );
    }
    const { rerender } = render(<Host open={false} />);
    expect(document.body.style.overflow).toBe('');

    rerender(<Host open />);
    expect(document.body.style.overflow).toBe('hidden');

    rerender(<Host open={false} />);
    expect(document.body.style.overflow).toBe('');
  });
});

describe('Modal styling contract', () => {
  it('sits below a popover so a Select inside it opens over it', () => {
    expect(OVERLAY_CSS).toMatch(
      /\.pms-modal,\s*\.pms-drawer\s*\{[^}]*z-index: var\(--pms-z-drawer\)/,
    );
  });

  it('scrolls the body while pinning the header and footer', () => {
    expect(OVERLAY_CSS).toMatch(/\.pms-overlay-body\s*\{[^}]*overflow-y: auto/);
  });

  it('drops the entrance animation under reduced motion', () => {
    expect(OVERLAY_CSS).toMatch(
      /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.pms-modal__panel[\s\S]*animation: none/,
    );
  });
});
