/**
 * AppShell, AppFooter and Avatar.
 *
 * jsdom does no layout, so nothing here asserts a pixel: the shell's contract that is
 * actually testable is its structure, its landmarks, the `data-` attributes the grid keys
 * off, and the drawer's state machine.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { AppFooter } from '../src/components/AppFooter';
import { AppShell } from '../src/components/AppShell';
import { Avatar } from '../src/components/Avatar';
import { CollapseToggle } from '../src/components/CollapseToggle';
import { Rail, RailItem, RailSection } from '../src/components/Rail';
import { TopBar } from '../src/components/TopBar';
import { DashboardIcon, DocumentIcon } from '../src/components/icons-console';

const SHELL_CSS = readFileSync(
  join(__dirname, '..', 'src', 'styles', 'shell.css'),
  'utf8',
);

function shell(props: Partial<Parameters<typeof AppShell>[0]> = {}) {
  return (
    <AppShell
      rail={
        <Rail brand={<span>PMS</span>}>
          <RailSection label="Ledger">
            <RailItem icon={<DashboardIcon />} label="Dashboard" href="/" active />
            <RailItem icon={<DocumentIcon />} label="Invoices" href="/invoices" />
          </RailSection>
        </Rail>
      }
      topBar={<TopBar left={<span>collapse</span>} right={<span>cluster</span>} />}
      footer={<AppFooter links={[{ label: 'Status', href: '/status' }]} copyright="© PMS" />}
      {...props}
    >
      <h1>Overview</h1>
    </AppShell>
  );
}

describe('AppShell', () => {
  it('renders the rail, the top bar, one main landmark and the footer', () => {
    const { container } = render(shell());

    expect(container.querySelector('.pms-shell')).toBeInTheDocument();
    expect(container.querySelector('.pms-rail')).toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();

    // There is exactly one `main`, and it sits inside the single scroll container — which is
    // the grid cell, so the page footer can be a sibling of `main` rather than a descendant.
    const mains = screen.getAllByRole('main');
    expect(mains).toHaveLength(1);
    const scroller = container.querySelector('.pms-main');
    expect(container.querySelectorAll('.pms-main')).toHaveLength(1);
    expect(scroller).toContainElement(mains[0] ?? null);

    // Content lives inside `main`; the footer lives inside the same scroller but outside
    // `main`, because a `<footer>` nested in `main` maps to `generic`, not `contentinfo`.
    expect(mains[0]).toContainElement(screen.getByRole('heading', { name: 'Overview' }));
    const footer = screen.getByRole('contentinfo');
    expect(mains[0]).not.toContainElement(footer);
    expect(footer).toContainElement(screen.getByRole('link', { name: 'Status' }));
    expect(container.querySelector('.pms-main')).toContainElement(footer);
    expect(screen.getByText('© PMS')).toBeInTheDocument();
  });

  it('offers a skip link as the first focusable element, targeting main', async () => {
    const user = userEvent.setup();
    const { container } = render(shell());

    const skip = screen.getByRole('link', { name: /skip to main content/i });
    const main = screen.getByRole('main');

    // WCAG 2.4.1: the rail precedes `main` with a dozen links and no bypass mechanism.
    expect(main.id).not.toBe('');
    expect(skip).toHaveAttribute('href', `#${main.id}`);
    expect(container.querySelector('.pms-shell')?.firstElementChild).toBe(skip);

    // First tab stop. Hiding and revealing is the stylesheet's job, not a JS class swap —
    // so assert the class it wears and that the sheet reveals it on focus, rather than
    // asserting a mechanism that would break the moment the CSS improved.
    expect(skip).toHaveClass('pms-skip-link');
    expect(SHELL_CSS).toMatch(/\.pms-skip-link \{[^}]*clip: rect\(0 0 0 0\)/);
    expect(SHELL_CSS).toContain('.pms-skip-link:focus');
    await user.tab();
    expect(skip).toHaveFocus();

    // The target takes focus programmatically, so the next Tab continues inside the content.
    expect(main).toHaveAttribute('tabindex', '-1');

    // …and it goes back out of sight once focus moves on, which the `:focus` rule handles
    // on its own — the element keeps its one class throughout.
    await user.tab();
    expect(skip).not.toHaveFocus();
    expect(skip).toHaveClass('pms-skip-link');
  });

  it('closes the drawer from the same control that opened it', async () => {
    const user = userEvent.setup();
    const { container } = render(shell());

    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    await user.click(screen.getByRole('button', { name: 'Close navigation' }));

    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'closed');
    // The control was the focused element, so it keeps focus rather than being re-focused.
    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveFocus();
  });

  it('closes on route changes and restores focus from the hidden rail', async () => {
    const user = userEvent.setup();
    const { container, rerender } = render(shell({ navigationKey: '/home' }));
    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    screen.getByRole('link', { name: 'Invoices' }).focus();

    rerender(shell({ navigationKey: '/invoices' }));

    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'closed');
    expect(container.querySelector('.pms-shell__scrim')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveFocus();
  });

  it('keeps the drawer open across updates without a route change', async () => {
    const user = userEvent.setup();
    const { container, rerender } = render(shell({ navigationKey: '/home' }));
    await user.click(screen.getByRole('button', { name: 'Open navigation' }));

    rerender(shell({ navigationKey: '/home', topBar: <span>Updated notification</span> }));

    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'open');
  });

  it('preserves destination focus when navigation has already moved it outside the rail', async () => {
    const user = userEvent.setup();
    const { container, rerender } = render(shell({ navigationKey: '/home' }));
    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    screen.getByRole('main').focus();

    rerender(shell({ navigationKey: '/invoices' }));

    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'closed');
    expect(screen.getByRole('main')).toHaveFocus();
  });

  it('does not move desktop navigation focus to the hidden drawer trigger', () => {
    const { rerender } = render(shell({ navigationKey: '/home' }));
    const link = screen.getByRole('link', { name: 'Invoices' });
    link.focus();

    rerender(shell({ navigationKey: '/invoices' }));

    expect(link).toHaveFocus();
  });

  it('places the rail across both rows and gives only main the scroll', () => {
    // The grid itself is CSS; assert the declarations the contract (§4.1) names.
    expect(SHELL_CSS).toContain('grid-template-columns: var(--pms-rail-w) 1fr');
    expect(SHELL_CSS).toContain('grid-template-rows: var(--pms-topbar-h) minmax(0, 1fr)');
    expect(SHELL_CSS).toMatch(/\.pms-shell__rail\s*\{[^}]*grid-row: 1 \/ 3/);
    expect(SHELL_CSS).toMatch(/\.pms-main\s*\{[^}]*overflow-y: auto/);
    expect(SHELL_CSS).toContain(
      ".pms-shell[data-collapsed='true'] {\n  grid-template-columns: var(--pms-rail-w-collapsed) 1fr;",
    );
  });

  it('omits data-collapsed when expanded and sets it when collapsed', () => {
    const { container, unmount } = render(shell({ collapsed: false }));
    expect(container.querySelector('.pms-shell')).not.toHaveAttribute('data-collapsed');
    unmount();

    const collapsed = render(shell({ collapsed: true }));
    expect(collapsed.container.querySelector('.pms-shell')).toHaveAttribute(
      'data-collapsed',
      'true',
    );
  });

  it('keeps every rail label as an accessible name while collapsed', () => {
    render(shell({ collapsed: true }));

    // The label text is hidden by CSS, never by `display:none` on the name itself.
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Invoices' })).toHaveAttribute('title', 'Invoices');
  });

  it('opens the drawer from the menu control and names it by state', async () => {
    const user = userEvent.setup();
    const { container } = render(shell());

    const menu = screen.getByRole('button', { name: 'Open navigation' });
    expect(menu).toHaveAttribute('aria-expanded', 'false');
    expect(menu).toHaveAttribute(
      'aria-controls',
      container.querySelector('.pms-shell__rail')?.getAttribute('id') ?? '',
    );
    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'closed');

    await user.click(menu);

    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'open');
    expect(screen.getByRole('button', { name: 'Close navigation' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('expands a collapsed rail when the drawer opens, since a drawer shows labels', async () => {
    const user = userEvent.setup();
    const onToggleCollapsed = vi.fn();
    render(shell({ collapsed: true, onToggleCollapsed }));

    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });

  it('leaves the caller alone when the drawer opens on an already expanded rail', async () => {
    const user = userEvent.setup();
    const onToggleCollapsed = vi.fn();
    render(shell({ collapsed: false, onToggleCollapsed }));

    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    expect(onToggleCollapsed).not.toHaveBeenCalled();
  });

  it('dismisses the drawer with Escape', async () => {
    const user = userEvent.setup();
    const { container } = render(shell());

    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    await user.keyboard('{Escape}');

    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'closed');
    expect(container.querySelector('.pms-shell__scrim')).not.toBeInTheDocument();
  });

  it('returns focus to the drawer trigger when Escape closes it from inside the rail', async () => {
    const user = userEvent.setup();
    render(shell());

    const trigger = screen.getByRole('button', { name: 'Open navigation' });
    await user.click(trigger);

    // A user who tabbed into the drawer and pressed Escape landed on `<body>`: closing hides
    // the rail with `visibility: hidden`, which drops the focused element out of the document.
    screen.getByRole('link', { name: 'Invoices' }).focus();
    await user.keyboard('{Escape}');

    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveFocus();
    expect(document.body).not.toHaveFocus();
  });

  it('leaves focus alone when Escape is pressed from outside the rail', async () => {
    const user = userEvent.setup();
    const { container } = render(shell());

    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    const skip = screen.getByRole('link', { name: /skip to main content/i });
    skip.focus();
    await user.keyboard('{Escape}');

    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'closed');
    expect(skip).toHaveFocus();
  });

  it('dismisses the drawer on a scrim click, and the scrim is never a tab stop', async () => {
    const user = userEvent.setup();
    const { container } = render(shell());

    await user.click(screen.getByRole('button', { name: 'Open navigation' }));

    const scrim = container.querySelector('.pms-shell__scrim');
    expect(scrim).toBeInTheDocument();
    expect(scrim).toHaveAttribute('aria-hidden', 'true');
    expect(scrim).not.toHaveAttribute('tabindex');

    await user.click(scrim as Element);
    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'closed');
  });

  it('takes the rail off the grid below the documented breakpoint', () => {
    expect(SHELL_CSS).toContain('@media (max-width: 960px)');
    expect(SHELL_CSS).toMatch(/@media \(max-width: 960px\)[\s\S]*position: fixed/);
    expect(SHELL_CSS).toMatch(/@media \(max-width: 960px\)[\s\S]*translateX\(-100%\)/);
    expect(SHELL_CSS).toContain('background: var(--pms-scrim)');
    expect(SHELL_CSS).toContain('@media (prefers-reduced-motion: reduce)');
  });
});

describe('client boundary', () => {
  it("marks every component that calls a React hook with 'use client'", () => {
    // These work today only because every importer happens to be a client component; a
    // Server Component importing one directly fails at build.
    const dir = join(__dirname, '..', 'src', 'components');
    const missing = readdirSync(dir)
      .filter((file) => file.endsWith('.tsx'))
      .filter((file) => {
        const source = readFileSync(join(dir, file), 'utf8');
        const usesHook = /\buse(Id|State|Effect|Ref|Callback|Memo|Context)\s*\(/.test(source);
        return usesHook && !source.trimStart().startsWith("'use client';");
      });

    expect(missing).toEqual([]);
  });
});

describe('AppFooter', () => {
  it('renders each icon link and the copyright', () => {
    render(
      <AppFooter
        links={[
          { label: 'Status', href: '/status', icon: <DashboardIcon /> },
          { label: 'Docs', href: '/docs' },
        ]}
        copyright="© 2026 PMS"
      />,
    );

    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Status' })).toHaveAttribute('href', '/status');
    expect(screen.getByRole('link', { name: 'Docs' })).toHaveAttribute('href', '/docs');
    expect(screen.getByText('© 2026 PMS')).toHaveClass('pms-app-footer__copy');

    // A decorative icon must not be read as part of the link's name.
    expect(screen.getByRole('link', { name: 'Status' }).querySelector('svg')).toBeInTheDocument();
  });

  it('wraps to a column on narrow widths rather than overflowing', () => {
    expect(SHELL_CSS).toMatch(/\.pms-app-footer\s*\{[^}]*flex-wrap: wrap/);
  });
});

describe('Avatar', () => {
  it.each([
    ['Northwind', 'NO'],
    ['Acme Corp', 'AC'],
    ['Northwind Trading Co', 'NC'],
    ['  spaced   out  ', 'SO'],
  ])('derives up to two initials from %s', (name, initials) => {
    render(<Avatar name={name} />);
    expect(screen.getByText(initials)).toBeInTheDocument();
  });

  it('renders nothing readable for an empty name rather than throwing', () => {
    const { container } = render(<Avatar name="   " />);
    expect(container.querySelector('.pms-avatar')?.textContent).toBe('');
  });

  it('is square for an organisation and round for a person', () => {
    const { container, unmount } = render(<Avatar name="Acme Corp" shape="square" />);
    expect(container.querySelector('.pms-avatar')).toHaveClass('pms-avatar--square');
    unmount();

    const person = render(<Avatar name="Priya Sharma" shape="round" size="lg" />);
    const el = person.container.querySelector('.pms-avatar');
    expect(el).toHaveClass('pms-avatar--round');
    expect(el).toHaveClass('pms-avatar--lg');
  });

  it('is decorative beside a visible name and named when it stands alone', () => {
    const { container, unmount } = render(<Avatar name="Priya Sharma" />);
    expect(container.querySelector('.pms-avatar')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    unmount();

    render(<Avatar name="Priya Sharma" label="Priya Sharma" />);
    expect(screen.getByRole('img', { name: 'Priya Sharma' })).toBeInTheDocument();
  });
});

describe('AppShell — the collapsed rail treatment', () => {
  /*
   * `data-collapsed`, the accessible names and the toggle's own labelling are covered above and
   * in topbar.test.tsx. What is left to pin is the presentation the attribute switches on: the
   * rules that hide the text and re-centre what remains, and the scope that keeps them away
   * from the drawer. jsdom computes no layout, so the stylesheet is the assertion.
   */
  it('keeps the icon itself, not only the accessible name, while collapsed', () => {
    render(shell({ collapsed: true }));

    // A collapsed rail whose icons were hidden along with the labels would be an empty column.
    const link = screen.getByRole('link', { name: 'Dashboard' });
    expect(link.querySelector('.pms-rail-item__icon svg')).toBeInTheDocument();
  });

  it('hides the text and re-centres every remaining row', () => {
    for (const hidden of [
      '.pms-rail-item__label',
      '.pms-rail-section__label',
      '.pms-org__text',
      '.pms-usermenu__text',
    ]) {
      expect(SHELL_CSS).toContain(`.pms-shell[data-collapsed='true'] ${hidden}`);
    }
    // Including the two rows that are not rail items — the lockup and the pinned footer, which
    // otherwise sat flush-left with a hole beside them.
    for (const centred of [
      '.pms-rail-item',
      '.pms-rail__brand',
      '.pms-rail-footer',
      '.pms-org',
    ]) {
      expect(SHELL_CSS).toContain(`.pms-shell[data-collapsed='true'] ${centred}`);
    }
  });

  it('scopes the collapsed treatment above the drawer breakpoint', () => {
    // Below it the rail is a full-width drawer, where icon-only would be a bug. The rules are
    // scoped rather than overridden, so nothing has to fight them off.
    const block = SHELL_CSS.slice(SHELL_CSS.indexOf('---------- collapsed rail'));
    expect(block).toMatch(/@media \(min-width: 960\.02px\)/);
  });
});
