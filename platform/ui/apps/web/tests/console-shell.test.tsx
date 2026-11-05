import { PermissionProvider, ThemeProvider } from '@pms/ui';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ConsoleShell } from '../src/components/ConsoleShell';
import { DEMO_USERS } from './fixtures/accounts';
import type { DemoUser } from './fixtures/accounts';
import type { RoleCode } from '../src/lib/roles';
import { sessionUser } from '../src/lib/session-user';
import catalog from '../../../../api/src/pms_api/security/default-roles.json';

/**
 * The rail is the product's whole permission story in this build: what each role is offered, and
 * that nothing is offered on a grant the actor does not hold.
 *
 * `usePathname` is stubbed rather than wrapped in a router — the shell uses exactly one thing
 * from Next's router, and a fake app-router context would be more machinery than the assertion.
 */
let pathname = '/home';
afterEach(() => {
  pathname = '/home';
});
vi.mock('next/navigation', () => ({ usePathname: () => pathname }));

function userFor(role: RoleCode): DemoUser {
  const user = DEMO_USERS.find((candidate) => candidate.role === role);
  if (!user) throw new Error(`no demo user for ${role}`);
  return user;
}

function renderShell(
  role: RoleCode,
  options: { permissions?: readonly string[] } = {},
) {
  const user = userFor(role);
  return render(
    <ThemeProvider>
      <PermissionProvider permissions={options.permissions ?? user.permissions}>
        <ConsoleShell user={user} notifications={3}>
          <p>page content</p>
        </ConsoleShell>
      </PermissionProvider>
    </ThemeProvider>,
  );
}

/** The rail's links, in order, by their accessible names. */
function railLinks(): string[] {
  const rail = document.querySelector('.pms-rail') as HTMLElement;
  /* `queryAll`, not `getAll`: with an empty permission set the correct answer is no links at
   * all, and `getAllByRole` throws rather than returning that. */
  return within(rail)
    .queryAllByRole('link')
    .map((link) => link.getAttribute('aria-label') ?? '');
}

describe('ConsoleShell', () => {
  it.each(['platform_admin', 'org_admin', 'org_user'] as const)(
    'offers Downloads in the account menu only for administrators (%s)', async (role) => {
      renderShell(role);
      await userEvent.setup().click(screen.getByRole('button', { name: userFor(role).name }));
      const downloads = screen.queryByRole('menuitem', { name: 'Downloads' });
      if (role === 'org_user') expect(downloads).not.toBeInTheDocument();
      else {
        expect(downloads).toHaveAttribute('href', '/downloads');
        expect(downloads?.previousElementSibling).toHaveAttribute('role', 'separator');
        expect(downloads?.nextElementSibling).toHaveAttribute('role', 'separator');
      }
    },
  );
  it.each(['org_read_only', 'org_trainee'])('keeps permitted navigation reachable for %s', role => {
    const permissions = catalog.roles.find(row => row.code === role)!.permissions;
    const user = sessionUser({ user: { id: 'reader', display_name: 'Reader', email: 'reader@example.com', password_management: true },
      contexts: [{ id: 'tenant', name: 'Tenant', role, department_id: null, permissions }] });
    render(<ThemeProvider><PermissionProvider permissions={permissions}>
      <ConsoleShell user={user} notifications={0}><p>page</p></ConsoleShell>
    </PermissionProvider></ThemeProvider>);
    expect(railLinks()).toEqual(expect.arrayContaining(['Home', 'My sessions', 'Recordings', 'Devices', 'Settings']));
    expect(railLinks()).not.toContain('Members');
    expect(railLinks()).not.toContain('Scenarios');
    if (role === 'org_trainee') expect(railLinks()).not.toContain('Logs');
  });
  it.each(['/models', '/models/example', '/licenses', '/users', '/users/example'])(
    'keeps Settings active on %s',
    (path) => {
      pathname = path;
      renderShell('platform_admin');
      expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('aria-current', 'page');
      expect(document.querySelectorAll('a[aria-current="page"]')).toHaveLength(1);
    },
  );

  it('does not highlight Settings for a similar route prefix', () => {
    pathname = '/models-archive';
    renderShell('platform_admin');
    expect(screen.getByRole('link', { name: 'Settings' })).not.toHaveAttribute('aria-current');
  });

  it('keeps platform settings reachable without clinical access', () => {
    renderShell('platform_admin', { permissions: ['platform.settings.read'] });
    expect(railLinks()).toEqual(['Settings']);
  });

  it('closes mobile navigation when the router reaches Settings', async () => {
    const user = userEvent.setup();
    const account = userFor('platform_admin');
    const frame = () => (
      <ThemeProvider>
        <PermissionProvider permissions={account.permissions}>
          <ConsoleShell user={account} notifications={3}>
            <p>page content</p>
          </ConsoleShell>
        </PermissionProvider>
      </ThemeProvider>
    );
    const { container, rerender } = render(frame());
    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    screen.getByRole('link', { name: 'Settings' }).focus();
    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'open');

    pathname = '/settings';
    rerender(frame());

    expect(container.querySelector('.pms-shell')).toHaveAttribute('data-drawer', 'closed');
    expect(container.querySelector('.pms-shell__scrim')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveFocus();
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('aria-current', 'page');
  });

  it('offers the platform administrator the platform destinations', () => {
    renderShell('platform_admin');

    expect(railLinks()).toEqual([
      'Home',
      'Tenants',
      'Devices',
      'Logs',
      'Settings',
    ]);
    /* No tenant of their own: no switcher, and no tenant chip in the bar. */
    expect(screen.queryByRole('button', { name: /Switch organisation/ })).not.toBeInTheDocument();
  });

  it('offers a tenant administrator their tenant, and names it', () => {
    renderShell('org_admin');

    expect(railLinks()).toEqual([
      'Home',
      'Members',
      'Devices',
      'Scenarios',
      'Sessions',
      'Reports',
      'Recordings',
      'Logs',
      'Settings',
    ]);
    expect(screen.getByRole('button', { name: /Switch organisation/ })).toBeInTheDocument();
    expect(screen.getAllByText('Northside Medical College').length).toBeGreaterThan(0);
  });

  it('shows tenant clinical content only with an effective capability', () => {
    const base = userFor('org_user').permissions;
    renderShell('org_user', { permissions: [...base, 'org.clinical.author'] });
    expect(railLinks()).toEqual(expect.arrayContaining([
      'Scenarios',
    ]));
  });

  it('offers a tenant user practice destinations and nothing administrative', () => {
    renderShell('org_user');

    const links = railLinks();
    expect(links).toEqual(['Home', 'My sessions', 'Recordings', 'Devices', 'Logs', 'Settings']);
    expect(links).not.toContain('Members');
    expect(links).toContain('Logs');
  });

  /*
   * Deny by default is the package's rule for `useCan`/`useGranted`, and the shell has to honour
   * it: an unknown permission set must not draw a menu of links the server would refuse.
   */
  it('draws no gated destination when the permission set is empty', () => {
    const user = userFor('org_admin');
    render(
      <ThemeProvider>
        <PermissionProvider permissions={[]}>
          <ConsoleShell user={user} notifications={0}>
            <p>page content</p>
          </ConsoleShell>
        </PermissionProvider>
      </ThemeProvider>,
    );

    expect(railLinks()).toEqual([]);
  });

  it('marks the current destination, and only that one', () => {
    pathname = '/devices';
    renderShell('org_admin');
    pathname = '/home';

    const current = screen.getAllByRole('link', { name: 'Devices' })[0];
    expect(current).toHaveAttribute('aria-current', 'page');
    expect(screen.getAllByRole('link', { name: 'Home' })[0]).not.toHaveAttribute('aria-current');
  });

  it('states who is signed in, with their role and address in the account menu', async () => {
    const user = userEvent.setup();
    renderShell('org_admin');

    const trigger = screen.getByRole('button', { name: 'Dr Rahul Iyer' });
    await user.click(trigger);

    const menu = screen.getByRole('menu');
    expect(menu).toHaveTextContent('tenantadmin@example.com');
    expect(menu).toHaveTextContent('Tenant Admin');
    expect(within(menu).getByRole('menuitem', { name: /Change password/ })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: /Sign out/ })).toBeInTheDocument();
  });

  it.each(['account menu', 'rail'])('posts sign-out from the %s without a server action', async (source) => {
    const user = userEvent.setup();
    renderShell('org_user');
    const form = document.querySelector<HTMLFormElement>('form[action="/logout"]')!;
    expect(form).toHaveAttribute('method', 'post');
    const submitted = vi.fn((event: Event) => event.preventDefault());
    form.addEventListener('submit', submitted);
    if (source === 'account menu') {
      await user.click(screen.getByRole('button', { name: 'Priya Nair' }));
      await user.click(screen.getByRole('menuitem', { name: /Sign out/ }));
    } else await user.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(submitted).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'Signing out…' })).toBeDisabled();
  });

  it('opens the change-password dialog from the account menu', async () => {
    const user = userEvent.setup();
    renderShell('platform_admin');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Asha Menon' }));
    await user.click(screen.getByRole('menuitem', { name: /Change password/ }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Change password' })).toBeInTheDocument();
  });

  it('announces the notification count rather than showing a coloured dot alone', () => {
    renderShell('platform_admin');

    expect(screen.getByRole('button', { name: 'Notifications, 3 unread' })).toBeInTheDocument();
  });

  /*
   * Two affordances with nothing behind them yet. Swallowing the click is the failure mode worth
   * testing for: it is indistinguishable from a broken build, and it is what these were doing
   * before the review.
   */
  it('says why the bell opens nothing instead of swallowing the click', async () => {
    const user = userEvent.setup();
    renderShell('platform_admin');

    await user.click(screen.getByRole('button', { name: 'Notifications, 3 unread' }));

    expect(await screen.findByText(/Notifications are not connected/)).toBeInTheDocument();
  });

  it('says why there is nothing to switch to', async () => {
    const user = userEvent.setup();
    renderShell('org_admin');

    await user.click(screen.getByRole('button', { name: /Switch organisation/ }));

    expect(await screen.findByText(/Nothing to switch to/)).toBeInTheDocument();
  });

  it('does not label session history as preview data', () => {
    pathname = '/sessions';
    renderShell('org_user');

    expect(screen.queryByText(/Preview data/)).not.toBeInTheDocument();
  });

  it.each([
    '/home',
    '/tenants',
    '/tenants/id',
    '/devices',
    '/devices/id',
    '/users',
    '/users/id',
    '/members',
    '/members/id',
    '/logs',
    '/logs/id',
  ])('does not label API-bound %s as preview data', (path) => {
    pathname = path;
    renderShell('platform_admin');
    expect(screen.queryByText(/Preview data/)).not.toBeInTheDocument();
  });

  it('collapses and expands the rail', async () => {
    const user = userEvent.setup();
    const { container } = renderShell('org_admin');
    const shell = container.querySelector('.pms-shell') as HTMLElement;

    expect(shell).not.toHaveAttribute('data-collapsed');
    await user.click(screen.getByRole('button', { name: /Collapse|Expand/ }));
    expect(shell).toHaveAttribute('data-collapsed', 'true');
  });
});
