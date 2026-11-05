/**
 * `Menu` — the row kebab and the toolbar overflow.
 *
 * Three things here are load-bearing and each has a test that would fail loudly if it regressed:
 * the keyboard contract (a `role="menu"` that does not cycle or return focus is worse than a
 * plain list), the portal (an in-flow panel is clipped by the table's horizontal scroller), and
 * permission filtering (a menu is where a row's conditional verbs live).
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { Menu, type MenuItem } from '../src/components/Menu';
import { PermissionProvider } from '../src/lib/permissions';
import { ColumnsIcon, EditIcon, TrashIcon } from '../src/components/icons-table';

const OVERLAY_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'overlay.css'), 'utf8');

const ITEMS: readonly MenuItem[] = [
  { id: 'view', label: 'View' },
  { id: 'edit', label: 'Edit', icon: <EditIcon size={16} /> },
  { id: 'delete', label: 'Delete', icon: <TrashIcon size={16} />, destructive: true },
];

function open(items: readonly MenuItem[] = ITEMS, extra: Partial<Parameters<typeof Menu>[0]> = {}) {
  const onSelect = vi.fn();
  const view = render(<Menu label="Row actions" items={items} onSelect={onSelect} {...extra} />);
  return { ...view, onSelect, trigger: screen.getByRole('button', { name: 'Row actions' }) };
}

const items = () => screen.getAllByRole('menuitem');

describe('Menu trigger', () => {
  it('is a named icon button that advertises its popup', () => {
    const { trigger } = open();
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('opens on click with focus on the first item', async () => {
    const user = userEvent.setup();
    const { trigger } = open();

    await user.click(trigger);

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('menu', { name: 'Row actions' })).toBeInTheDocument();
    expect(items()[0]).toHaveFocus();
  });

  it('opens on ArrowDown at the first item and on ArrowUp at the last', async () => {
    const user = userEvent.setup();
    const { trigger } = open();

    trigger.focus();
    await user.keyboard('{ArrowDown}');
    expect(items()[0]).toHaveFocus();

    await user.keyboard('{Escape}');
    await user.keyboard('{ArrowUp}');
    expect(items()[2]).toHaveFocus();
  });

  it('closes again when clicked while open', async () => {
    const user = userEvent.setup();
    const { trigger } = open();

    await user.click(trigger);
    await user.click(trigger);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('renders a labelled trigger with a caret when given trigger text', async () => {
    const user = userEvent.setup();
    render(
      <Menu
        label="Choose columns"
        triggerLabel="Columns"
        icon={<ColumnsIcon size={16} />}
        items={ITEMS}
        onSelect={vi.fn()}
      />,
    );

    const trigger = screen.getByRole('button', { name: /Columns/ });
    expect(trigger).toHaveClass('pms-menu__trigger');
    await user.click(trigger);
    expect(screen.getByRole('menu', { name: 'Choose columns' })).toBeInTheDocument();
  });
});

describe('Menu keyboard model', () => {
  it('keeps one tab stop — only the active item is reachable by Tab', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    expect(items().map((item) => item.getAttribute('tabindex'))).toEqual(['0', '-1', '-1']);
  });

  it('cycles with the arrow keys in both directions', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    await user.keyboard('{ArrowDown}');
    expect(items()[1]).toHaveFocus();
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(items()[0]).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(items()[2]).toHaveFocus();
  });

  it('jumps to the ends with Home and End', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    await user.keyboard('{End}');
    expect(items()[2]).toHaveFocus();
    await user.keyboard('{Home}');
    expect(items()[0]).toHaveFocus();
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('closes on Tab and hands focus back to the trigger, not to the end of the body', async () => {
    const user = userEvent.setup();
    render(
      <>
        <Menu label="Row actions" items={ITEMS} onSelect={vi.fn()} />
        <button type="button">After</button>
      </>,
    );
    const trigger = screen.getByRole('button', { name: 'Row actions' });
    await user.click(trigger);

    await user.tab();

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    // The panel is portalled to the end of the body; without the synchronous focus restore the
    // next tab stop would have been computed from there and this would be `body`.
    expect(screen.getByRole('button', { name: 'After' })).toHaveFocus();
  });

  it('closes on an outside press without stealing focus back', async () => {
    const user = userEvent.setup();
    render(
      <>
        <Menu label="Row actions" items={ITEMS} onSelect={vi.fn()} />
        <button type="button">Elsewhere</button>
      </>,
    );
    const trigger = screen.getByRole('button', { name: 'Row actions' });
    await user.click(trigger);

    await user.click(screen.getByRole('button', { name: 'Elsewhere' }));

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).not.toHaveFocus();
  });

  it('does not close when its own item is pressed down on', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open();
    await user.click(trigger);

    // The panel is outside the trigger in the DOM, so the outside-press guard has to test it too.
    await user.click(screen.getByRole('menuitem', { name: 'Edit' }));

    expect(onSelect).toHaveBeenCalledWith('edit');
  });
});

describe('Menu selection', () => {
  it('reports the chosen id, closes, and restores focus', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open();
    await user.click(trigger);

    await user.click(screen.getByRole('menuitem', { name: 'View' }));

    expect(onSelect).toHaveBeenCalledWith('view');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('activates by keyboard as well as by pointer', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open();
    await user.click(trigger);

    await user.keyboard('{ArrowDown}{Enter}');

    expect(onSelect).toHaveBeenCalledWith('edit');
  });
});

describe('Menu checkbox items', () => {
  const toggles: readonly MenuItem[] = [
    { id: 'number', label: 'Number', checked: true },
    { id: 'customer', label: 'Customer', checked: false },
    { id: 'reset', label: 'Reset columns' },
  ];

  it('is a menuitemcheckbox carrying its own state', async () => {
    const user = userEvent.setup();
    const { trigger } = open(toggles);
    await user.click(trigger);

    expect(screen.getByRole('menuitemcheckbox', { name: 'Number' })).toBeChecked();
    expect(screen.getByRole('menuitemcheckbox', { name: 'Customer' })).not.toBeChecked();
    // A verb in the same menu stays a verb.
    expect(screen.getByRole('menuitem', { name: 'Reset columns' })).toBeInTheDocument();
  });

  it('stays open when one is chosen, because the reader is setting a set', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open(toggles);
    await user.click(trigger);

    await user.click(screen.getByRole('menuitemcheckbox', { name: 'Customer' }));

    expect(onSelect).toHaveBeenCalledWith('customer');
    expect(screen.getByRole('menu')).toBeInTheDocument();

    // …and a second one can be set without reopening the panel.
    await user.click(screen.getByRole('menuitemcheckbox', { name: 'Number' }));
    expect(onSelect).toHaveBeenCalledWith('number');
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  it('closes on a verb in the same menu', async () => {
    const user = userEvent.setup();
    const { trigger } = open(toggles);
    await user.click(trigger);

    await user.click(screen.getByRole('menuitem', { name: 'Reset columns' }));

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('shows the state, so it is not `aria-checked` alone', async () => {
    const user = userEvent.setup();
    const { trigger } = open(toggles);
    await user.click(trigger);

    const on = screen.getByRole('menuitemcheckbox', { name: 'Number' });
    const off = screen.getByRole('menuitemcheckbox', { name: 'Customer' });

    expect(on.querySelector('.pms-menu__item-check svg')).toBeInTheDocument();
    // The slot stays, empty, so the labels of a toggle list do not shift as they are set.
    expect(off.querySelector('.pms-menu__item-check')).toBeInTheDocument();
    expect(off.querySelector('.pms-menu__item-check svg')).toBeNull();
  });

  it('reserves the same width for a checked and an unchecked item', () => {
    expect(OVERLAY_CSS).toMatch(/\.pms-menu__item-check\s*\{[^}]*width: 1\.15rem/);
  });
});

describe('Menu disabled items', () => {
  const withReason: readonly MenuItem[] = [
    { id: 'edit', label: 'Edit', disabledReason: 'Posted documents cannot be edited' },
    { id: 'view', label: 'View' },
  ];

  it('shows the reason and marks the item aria-disabled rather than removing it', async () => {
    const user = userEvent.setup();
    const { trigger } = open(withReason);
    await user.click(trigger);

    const edit = screen.getByRole('menuitem', { name: /Edit/ });
    expect(edit).toHaveAttribute('aria-disabled', 'true');
    expect(edit).not.toBeDisabled();
    expect(within(edit).getByText('Posted documents cannot be edited')).toBeInTheDocument();
  });

  it('keeps the disabled item in the roving order so its reason is discoverable', async () => {
    const user = userEvent.setup();
    const { trigger } = open(withReason);
    await user.click(trigger);

    expect(screen.getByRole('menuitem', { name: /Edit/ })).toHaveFocus();
  });

  it('ignores activation of a disabled item and stays open', async () => {
    const user = userEvent.setup();
    const { trigger, onSelect } = open(withReason);
    await user.click(trigger);

    await user.click(screen.getByRole('menuitem', { name: /Edit/ }));

    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });
});

describe('Menu permission gating', () => {
  const gated: readonly MenuItem[] = [
    { id: 'view', label: 'View', permission: 'invoice.read' },
    { id: 'post', label: 'Post', permission: 'invoice.post' },
    { id: 'note', label: 'Add note' },
  ];

  const withPermissions = (permissions: readonly string[]) =>
    render(
      <PermissionProvider permissions={permissions}>
        <Menu label="Row actions" items={gated} onSelect={vi.fn()} />
      </PermissionProvider>,
    );

  it('omits an item the actor cannot use — absent, not disabled', async () => {
    const user = userEvent.setup();
    withPermissions(['invoice.read']);

    await user.click(screen.getByRole('button', { name: 'Row actions' }));

    expect(items().map((item) => item.textContent)).toEqual(['View', 'Add note']);
  });

  it('accepts a wildcard grant', async () => {
    const user = userEvent.setup();
    withPermissions(['invoice.*']);

    await user.click(screen.getByRole('button', { name: 'Row actions' }));

    expect(items()).toHaveLength(3);
  });

  it('keeps an ungated item, which the server still authorizes', async () => {
    const user = userEvent.setup();
    withPermissions([]);

    await user.click(screen.getByRole('button', { name: 'Row actions' }));

    expect(items().map((item) => item.textContent)).toEqual(['Add note']);
  });

  it('stops claiming a popup, and does not open, when nothing survives filtering', async () => {
    const user = userEvent.setup();
    render(
      <PermissionProvider permissions={[]}>
        <Menu
          label="Row actions"
          items={[{ id: 'post', label: 'Post', permission: 'invoice.post' }]}
          onSelect={vi.fn()}
        />
      </PermissionProvider>,
    );

    const trigger = screen.getByRole('button', { name: 'Row actions' });
    expect(trigger).not.toHaveAttribute('aria-haspopup');
    expect(trigger).not.toHaveAttribute('aria-expanded');

    await user.click(trigger);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('does not open when disabled', async () => {
    const user = userEvent.setup();
    const { trigger } = open(ITEMS, { disabled: true });

    await user.click(trigger);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });
});

describe('Menu structure', () => {
  it('separates the destructive verbs from the ordinary ones', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    const separators = screen.getAllByRole('separator');
    expect(separators).toHaveLength(1);
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toHaveAttribute('data-tone', 'danger');
  });

  it('renders no separator when the destructive item is the only one', async () => {
    const user = userEvent.setup();
    const { trigger } = open([{ id: 'delete', label: 'Delete', destructive: true }]);
    await user.click(trigger);

    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
  });

  it('portals the panel to the body, out of any clipping ancestor', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <div style={{ overflowX: 'auto' }}>
        <Menu label="Row actions" items={ITEMS} onSelect={vi.fn()} />
      </div>,
    );

    await user.click(screen.getByRole('button', { name: 'Row actions' }));

    const panel = screen.getByRole('menu');
    expect(container.contains(panel)).toBe(false);
    expect(panel.parentElement).toBe(document.body);
    // Fixed positioning is what makes the portal correct — an absolute panel would scroll away.
    expect(panel).toHaveStyle({ position: 'fixed' });
  });

  it('links the trigger to the panel it controls', async () => {
    const user = userEvent.setup();
    const { trigger } = open();
    await user.click(trigger);

    expect(trigger.getAttribute('aria-controls')).toBe(screen.getByRole('menu').id);
  });

  it('sits at the documented popover stacking level, above the dialog', () => {
    expect(OVERLAY_CSS).toMatch(
      /\.pms-menu__panel\s*\{[^}]*z-index: var\(--pms-z-popover\)/,
    );
  });

  it('lets a disabled item wrap its reason rather than truncating it', () => {
    expect(OVERLAY_CSS).toMatch(/\.pms-menu__item-note\s*\{[^}]*white-space: normal/);
  });
});
