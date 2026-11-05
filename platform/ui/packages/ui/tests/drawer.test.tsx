/**
 * `Drawer` — the inline-end side sheet. It shares `Modal`'s mechanism (portal, focus trap, scroll
 * lock) through the same `Overlay`, so these tests cover what is drawer-specific: it renders as its
 * own frame, dismisses the three ways, and its panel hangs off the leading edge.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { Drawer } from '../src/components/Overlay';

const OVERLAY_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'overlay.css'), 'utf8');

function setup(overrides: Partial<Parameters<typeof Drawer>[0]> = {}) {
  const onClose = vi.fn();
  const view = render(
    <Drawer open title="Filters" onClose={onClose} {...overrides}>
      <p>Refine the list.</p>
    </Drawer>,
  );
  return { ...view, onClose };
}

describe('Drawer', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <Drawer open={false} title="Filters" onClose={vi.fn()}>
        <p>body</p>
      </Drawer>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('is a modal dialog in its own frame, portalled to the body', () => {
    const { container } = setup();
    const dialog = screen.getByRole('dialog', { name: 'Filters' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(container.contains(dialog)).toBe(false);
    expect(document.body.querySelector('.pms-drawer__panel')).toBeInTheDocument();
  });

  it('closes from the header button, the scrim and Escape', async () => {
    const user = userEvent.setup();

    const a = setup();
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(a.onClose).toHaveBeenCalledTimes(1);
    a.unmount();

    const b = setup();
    await user.click(document.querySelector('.pms-drawer__scrim') as Element);
    expect(b.onClose).toHaveBeenCalledTimes(1);
    b.unmount();

    const c = setup();
    await user.keyboard('{Escape}');
    expect(c.onClose).toHaveBeenCalledTimes(1);
  });

  it('does not dismiss while busy', async () => {
    const user = userEvent.setup();
    const { onClose } = setup({ busy: true });
    await user.keyboard('{Escape}');
    await user.click(document.querySelector('.pms-drawer__scrim') as Element);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('hangs the panel off the leading edge and slides in', () => {
    expect(OVERLAY_CSS).toMatch(
      /\.pms-drawer__panel\s*\{[^}]*border-inline-start: 1px solid var\(--pms-line-strong\)/,
    );
    expect(OVERLAY_CSS).toMatch(/\.pms-drawer__panel\s*\{[^}]*animation: pms-drawer-in/);
  });
});
