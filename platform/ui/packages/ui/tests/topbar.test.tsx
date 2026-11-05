/**
 * TopBar, ContextChip, RoleChip, NotificationBell, CollapseToggle and UserMenu.
 *
 * The menu's keyboard contract is the substance of these tests: a `role="menu"` that does
 * not cycle, does not return focus on Escape and does not close on Tab is a worse control
 * than a plain list, so each of those is asserted rather than assumed.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { CollapseToggle } from '../src/components/CollapseToggle';
import { ContextChip, RoleChip } from '../src/components/Chips';
import { NotificationBell } from '../src/components/NotificationBell';
import { TopBar } from '../src/components/TopBar';
import { UserMenu, type UserMenuItem } from '../src/components/UserMenu';
import { LogoutIcon, SettingsIcon } from '../src/components/icons-console';
import { UserIcon } from '../src/components/icons';

const SHELL_CSS = readFileSync(
  join(__dirname, '..', 'src', 'styles', 'shell.css'),
  'utf8',
);

describe('TopBar', () => {
  it('renders the left and right clusters as a banner', () => {
    const { container } = render(
      <TopBar left={<span>collapse</span>} right={<span>cluster</span>}>
        <span>middle</span>
      </TopBar>,
    );

    expect(screen.getByRole('banner')).toHaveClass('pms-topbar');
    expect(container.querySelector('.pms-topbar__left')).toHaveTextContent('collapse');
    expect(container.querySelector('.pms-topbar__mid')).toHaveTextContent('middle');
    expect(container.querySelector('.pms-topbar__right')).toHaveTextContent('cluster');
  });

  it('renders no empty slot wrappers', () => {
    const { container, unmount } = render(<TopBar right={<span>cluster</span>} />);

    expect(container.querySelector('.pms-topbar__left')).not.toBeInTheDocument();
    expect(container.querySelector('.pms-topbar__mid')).not.toBeInTheDocument();
    expect(container.querySelector('.pms-topbar__right')).toBeInTheDocument();
    unmount();

    const leftOnly = render(<TopBar left={<span>collapse</span>} />);
    expect(leftOnly.container.querySelector('.pms-topbar__left')).toBeInTheDocument();
    expect(leftOnly.container.querySelector('.pms-topbar__right')).not.toBeInTheDocument();
  });

  it('sticks at the documented stacking order with a hairline bottom border', () => {
    expect(SHELL_CSS).toMatch(/\.pms-shell__topbar\s*\{[^}]*position: sticky/);
    expect(SHELL_CSS).toMatch(/\.pms-shell__topbar\s*\{[^}]*z-index: var\(--pms-z-topbar\)/);
    expect(SHELL_CSS).toMatch(
      /\.pms-shell__topbar\s*\{[^}]*border-bottom: 1px solid var\(--pms-line\)/,
    );
  });
});

describe('ContextChip', () => {
  it('renders the label with a decorative dot', () => {
    const { container } = render(<ContextChip label="FY 2026-27" />);

    expect(screen.getByText('FY 2026-27')).toHaveClass('pms-chip__label');
    expect(container.querySelector('.pms-chip__dot')).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector('.pms-chip')).toHaveAttribute('data-tone', 'neutral');
  });

  it.each([
    ['neutral', 'no status'],
    ['brand', 'active'],
    ['success', 'healthy'],
    ['warn', 'needs attention'],
    ['danger', 'critical'],
    ['info', 'for information'],
  ] as const)('states the %s tone in words, never colour alone', (tone, description) => {
    const { container } = render(<ContextChip label="Period" tone={tone} />);
    const chip = container.querySelector('.pms-chip');

    expect(chip).toHaveAttribute('data-tone', tone);
    expect(chip).toHaveTextContent(`Period (${description})`);
  });

  it('carries each tone on the border and the accent, not as a tinted fill', () => {
    for (const tone of ['brand', 'success', 'warn', 'danger', 'info']) {
      expect(SHELL_CSS).toContain(`.pms-chip[data-tone='${tone}']`);
      expect(SHELL_CSS).toContain(`border-color: var(--pms-${tone}-line)`);
      expect(SHELL_CSS).toContain(`--pms-chip-accent: var(--pms-${tone}-ink)`);
    }
    // The pill itself stays a quiet surface: a chip states context, and two saturated pills
    // side by side in the top bar read as two alerts instead.
    expect(SHELL_CSS).toMatch(/\.pms-chip \{[^}]*background: var\(--pms-surface\)/);
    expect(SHELL_CSS).toMatch(/\.pms-chip__dot \{[^}]*background: var\(--pms-chip-accent\)/);
  });
});

describe('RoleChip', () => {
  it('renders the role behind a default shield', () => {
    const { container } = render(<RoleChip label="Accountant" />);

    expect(screen.getByText('Accountant')).toHaveClass('pms-chip__label');
    const icon = container.querySelector('.pms-chip__icon');
    expect(icon).toHaveAttribute('aria-hidden', 'true');
    expect(icon?.querySelector('svg')).toBeInTheDocument();
  });

  it('accepts a caller icon', () => {
    const { container } = render(<RoleChip label="Owner" icon={<UserIcon size={14} />} />);
    expect(container.querySelectorAll('.pms-chip__icon svg')).toHaveLength(1);
  });
});

describe('NotificationBell', () => {
  it('puts the unread count in the accessible name and shows the dot', () => {
    const { container } = render(<NotificationBell count={3} />);

    expect(screen.getByRole('button', { name: 'Notifications, 3 unread' })).toBeInTheDocument();
    expect(container.querySelector('.pms-btn__dot')).toBeInTheDocument();
  });

  it('renders no dot and a plain name at zero', () => {
    const { container } = render(<NotificationBell count={0} />);

    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
    expect(container.querySelector('.pms-btn__dot')).not.toBeInTheDocument();
  });

  it('calls onOpen when activated', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<NotificationBell count={1} onOpen={onOpen} />);

    await user.click(screen.getByRole('button', { name: 'Notifications, 1 unread' }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});

describe('CollapseToggle', () => {
  it('names the action and carries the state on an expanded rail', () => {
    render(<CollapseToggle collapsed={false} onToggle={() => undefined} />);

    const button = screen.getByRole('button', { name: 'Collapse sidebar' });
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(button).toHaveAttribute('title', 'Collapse sidebar');
  });

  it('flips the name and the state when collapsed', () => {
    render(<CollapseToggle collapsed onToggle={() => undefined} />);

    const button = screen.getByRole('button', { name: 'Expand sidebar' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).toHaveClass('pms-collapse--collapsed');
  });

  it('calls onToggle when activated', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<CollapseToggle collapsed={false} onToggle={onToggle} />);

    await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});

const MENU_ITEMS: UserMenuItem[] = [
  { id: 'profile', label: 'Your profile', icon: <UserIcon size={16} /> },
  { id: 'settings', label: 'Preferences', icon: <SettingsIcon size={16} /> },
  { id: 'signout', label: 'Sign out', icon: <LogoutIcon size={16} /> },
];

function renderMenu(onSelect?: (id: string) => void) {
  return render(
    <UserMenu
      name="Priya Sharma"
      secondary="Finance manager"
      items={MENU_ITEMS}
      onSelect={onSelect}
    />,
  );
}

describe('UserMenu', () => {
  it('renders a closed trigger showing the name and the secondary line', () => {
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).not.toHaveAttribute('aria-controls');
    expect(screen.getByText('Finance manager')).toBeInTheDocument();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('opens on click, focusing the first item', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(trigger).toHaveAttribute('aria-controls', screen.getByRole('menu').id);

    const items = screen.getAllByRole('menuitem');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveFocus();
    // One tab stop for the whole menu; the arrows move within it.
    expect(items[1]).toHaveAttribute('tabindex', '-1');
  });

  it('opens with ArrowDown on the first item and with ArrowUp on the last', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    trigger.focus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();

    await user.keyboard('{Escape}');
    trigger.focus();
    await user.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();
  });

  it('cycles with the arrow keys in both directions', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));

    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[1]).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();
    // past the end, back to the top
    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
    // and off the top, round to the end
    await user.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();

    await user.keyboard('{Home}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();
    // and step back through the middle, not just around the ends
    await user.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('menuitem')[1]).toHaveFocus();
  });

  it('ignores a key it does not own, leaving the menu open on the same item', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));
    await user.keyboard('x');

    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);
    await user.keyboard('{Escape}');

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('closes on Tab, because a menu is not a dialog', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));
    await user.tab();

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('closes on an outside click without stealing focus back', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);
    await user.click(document.body);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).not.toHaveFocus();
  });

  it('closes again when the trigger is clicked a second time', async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);
    await user.click(trigger);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('reports the chosen item once and closes back onto the trigger', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderMenu(onSelect);

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    await user.click(trigger);
    await user.click(screen.getByRole('menuitem', { name: 'Sign out' }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('signout');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('does not read a decorative item icon as part of the item name', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));
    const item = screen.getByRole('menuitem', { name: 'Preferences' });
    expect(item.querySelector('.pms-usermenu__item-icon')).toHaveAttribute(
      'aria-hidden',
      'true',
    );
  });

  it('renders the popup on the overlay surface at the popover layer', () => {
    expect(SHELL_CSS).toMatch(
      /\.pms-usermenu__menu\s*\{[^}]*z-index: var\(--pms-z-popover\)/,
    );
    expect(SHELL_CSS).toMatch(/\.pms-usermenu__menu\s*\{[^}]*background: var\(--pms-overlay\)/);
    expect(SHELL_CSS).toMatch(
      /\.pms-usermenu__menu\s*\{[^}]*box-shadow: var\(--pms-shadow-popover\)/,
    );
    expect(SHELL_CSS).toMatch(
      /\.pms-usermenu__menu\s*\{[^}]*border-radius: var\(--pms-radius-md\)/,
    );
  });

  it('renders without a secondary line when none is given', () => {
    render(<UserMenu name="Priya Sharma" items={MENU_ITEMS} />);
    expect(screen.queryByText('Finance manager')).not.toBeInTheDocument();
  });

  /*
   * The identity block: which account am I about to act as? A console user with an administrator
   * login and an ordinary one needs that answerable without leaving the menu.
   */
  it('heads the open menu with the identity when an address is given', async () => {
    const user = userEvent.setup();
    render(
      <UserMenu
        name="Priya Sharma"
        secondary="Finance manager"
        email="priya@example.com"
        items={MENU_ITEMS}
      />,
    );

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));

    const menu = screen.getByRole('menu');
    expect(menu).toHaveTextContent('priya@example.com');
    /* The role appears in the trigger and again in the block; the menu holds its own copy. */
    expect(menu).toHaveTextContent('Finance manager');
    /* Presentational: `role="menu"` admits menu items, not arbitrary blocks, so the header must
     * not add a fourth thing the arrow keys can land on. */
    expect(screen.getAllByRole('menuitem')).toHaveLength(MENU_ITEMS.length);
    expect(menu.querySelector('.pms-usermenu__header')).toHaveAttribute('role', 'presentation');
  });

  it('omits the identity block when no address is given', async () => {
    const user = userEvent.setup();
    render(<UserMenu name="Priya Sharma" secondary="Finance manager" items={MENU_ITEMS} />);

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));

    expect(screen.getByRole('menu').querySelector('.pms-usermenu__header')).toBeNull();
  });

  it('never opens an empty menu', async () => {
    const user = userEvent.setup();
    render(<UserMenu name="Priya Sharma" items={[]} />);

    const trigger = screen.getByRole('button', { name: /Priya Sharma/ });
    // `items.length - 1` is -1 with no items: the menu opened empty, with nothing focusable
    // and an active index pointing outside the list.
    expect(trigger).not.toHaveAttribute('aria-haspopup');
    expect(trigger).not.toHaveAttribute('aria-expanded');

    await user.click(trigger);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    trigger.focus();
    await user.keyboard('{ArrowUp}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    await user.keyboard('{ArrowDown}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('renders items without icons', async () => {
    const user = userEvent.setup();
    render(<UserMenu name="Priya Sharma" items={[{ id: 'only', label: 'Only item' }]} />);

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }));
    const item = screen.getByRole('menuitem', { name: 'Only item' });
    expect(item.querySelector('.pms-usermenu__item-icon')).not.toBeInTheDocument();

    // A single item still cycles — onto itself.
    await user.keyboard('{ArrowDown}');
    expect(item).toHaveFocus();
  });
});

describe('the top bar as a popover host', () => {
  /*
   * The bar contains the one popover in the shell, and it opens *below* the 60px band. That
   * makes "does the bar clip its own children" a real contract, not a styling detail: an
   * `overflow` other than `visible` turns the bar into a scroll container, which clips
   * descendants and shows the menu as a sliver with a scrollbar instead of a popover.
   *
   * This is asserted against the stylesheet because jsdom computes no layout and would report
   * the menu as perfectly visible either way — which is exactly why the bug shipped.
   */
  it('never becomes a scroll container, or it would clip the menu it hosts', () => {
    const bar = SHELL_CSS.slice(SHELL_CSS.indexOf('.pms-topbar {'));
    const rule = bar.slice(0, bar.indexOf('}'));

    expect(rule).not.toMatch(/overflow/);
  });

  it('sheds content as it narrows instead of scrolling', () => {
    // Reflow to 320px without a scrollbar (WCAG 1.4.10) has to come from dropping controls:
    // the collapse toggle, then the chips, then the user's name — leaving the avatar.
    expect(SHELL_CSS).toMatch(/@media \(max-width: 960px\)[\s\S]*?\.pms-topbar__left \{\n    display: none/);
    expect(SHELL_CSS).toMatch(/@media \(max-width: 720px\)[\s\S]*?\.pms-topbar__mid/);
    expect(SHELL_CSS).toMatch(/@media \(max-width: 640px\)[\s\S]*?\.pms-usermenu__text/);
  });

  it('names the trigger independently of the text it may hide', () => {
    // Two places hide `.pms-usermenu__text`: a collapsed rail and a narrow bar. Before the
    // `aria-label`, the control lost its accessible name along with its label in both.
    render(
      <UserMenu name="Priya Sharma" secondary="Sharma Traders" items={MENU_ITEMS} />,
    );

    const trigger = screen.getByRole('button', { name: 'Priya Sharma' });
    expect(trigger).toHaveAttribute('aria-label', 'Priya Sharma');
    // `secondary` is context, not identity, so it stays out of the name.
    expect(trigger.getAttribute('aria-label')).not.toContain('Sharma Traders');
  });
});
