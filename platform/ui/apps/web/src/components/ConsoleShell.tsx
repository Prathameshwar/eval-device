'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useId, useRef, useState, type ReactNode } from 'react';
import {
  AppShell,
  Button,
  CollapseToggle,
  ContextChip,
  DownloadIcon,
  LockIcon,
  LogoutIcon,
  NotificationBell,
  OrgSwitcher,
  Rail,
  RailFooter,
  RailItem,
  RailSection,
  RoleChip,
  ThemeSwitcher,
  ToastProvider,
  TopBar,
  UserMenu,
  useGranted,
  useToast,
  type UserMenuItem,
} from '@pms/ui';
import { BrandLockup } from '@/components/BrandMark';
import { ChangePasswordDialog } from '@/components/ChangePasswordDialog';
import { ChangeEmailDialog } from '@/components/ChangeEmailDialog';
import { switchContext } from '@/lib/actions';
import type { SessionUser } from '@/lib/session-user';
import { NAVIGATION, isActive, type NavItem } from '@/lib/navigation';
import { ROLE_LABELS, isTenantScoped } from '@/lib/roles';
import { canOpenSettings, settingsFor } from '@/lib/settings';
import { canDownload } from '@/lib/download-access';

/**
 * The console frame: `AppShell`'s grid, the rail on the left, the context cluster top right.
 *
 * Three rules it follows from the package's own documentation:
 *
 * - **Permission gating happens here, not in `RailItem`.** The rail is a layout component; it
 *   renders what it is handed. `useGranted` reads the `PermissionProvider` the server layout
 *   seeded from the role's catalogue grants, and an item whose grant is missing is not drawn.
 *   Deny by default: with no provider, whole sections disappear rather than rendering links the
 *   server would refuse.
 * - **Logout sits beside `RailFooter`, not inside it.** That component's children are
 *   `RailItem`s, which render `<li>`; a button in there would be a list item with no list, and
 *   `RailFooter`'s own comment says as much.
 * - **The chips go in the top bar's middle slot.** The package hides that slot below 720px and
 *   folds the identity into the account menu, which is why the menu carries the role too.
 *
 * And one of its own: **no control here does nothing.** The bell and the tenant switcher are
 * real affordances with nothing behind them yet, so they say so through a toast rather than
 * swallowing the click — the same answer the sign-in screen gives for Google and Microsoft.
 *
 * `collapsed` is component state, as the package intends: persisting it needs the same pre-paint
 * treatment as the theme, or the rail renders at 288px and snaps to 72px after hydration, which
 * looks like a bug rather than a restored preference.
 */

export function ConsoleShell({
  user,
  notifications,
  children,
}: {
  user: SessionUser;
  /** A static count in this build; the bell is presentation until there is something to open. */
  notifications: number;
  children: ReactNode;
}) {
  return (
    <ToastProvider>
      <ConsoleFrame user={user} notifications={notifications}>
        {children}
      </ConsoleFrame>
    </ToastProvider>
  );
}

/** Inside the provider, so `useToast` has one to find. */
function ConsoleFrame({
  user,
  notifications,
  children,
}: {
  user: SessionUser;
  notifications: number;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const granted = useGranted();
  const toast = useToast();
  const [collapsed, setCollapsed] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [changingEmail, setChangingEmail] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const signOutFormId = useId();
  const signOutForm = useRef<HTMLFormElement>(null);
  const [switching, setSwitching] = useState(false);

  function logout() {
    if (signingOut) return;
    signOutForm.current?.requestSubmit();
  }

  async function selectContext(id: string) {
    setSwitching(true);
    try {
      const result = await switchContext(id);
      if (result?.error) toast.error(result.error, { title: 'Unable to switch organisation' });
    } catch {
      toast.error('Unable to connect. Please try again.');
    } finally {
      setSwitching(false);
    }
  }

  const navigation = NAVIGATION[user.role];
  const roleLabel = user.roleLabel ?? ROLE_LABELS[user.role];
  const settingsSections = settingsFor(user.role, granted);

  const item = (entry: NavItem) => (
    <RailItem
      key={entry.id}
      icon={<entry.icon size={18} />}
      label={entry.label}
      href={entry.href}
      active={
        isActive(entry.href, pathname) ||
        (entry.id === 'settings' && settingsSections.some((section) => isActive(section.href, pathname)))
      }
      /* `next/link`, so a menu click is a client navigation rather than a document reload. */
      as={Link}
    />
  );

  const menuItems: UserMenuItem[] = [
    ...(user.passwordManagement
      ? [
          {
            id: 'password',
            label: 'Change password',
            icon: <LockIcon size={16} />,
          },
          {
            id: 'email',
            label: 'Change email address',
            icon: <LockIcon size={16} />,
          },
        ]
      : []),
    ...(canDownload(user) ? [{ id: 'downloads', label: 'Downloads', href: '/downloads',
      icon: <DownloadIcon size={16} />, separated: true }] : []),
    { id: 'signout', label: 'Sign out', icon: <LogoutIcon size={16} /> },
  ];

  const rail = (
    <Rail
      brand={<BrandLockup size="compact" />}
      switcher={
        user.contexts && user.contexts.length > 1 ? (
          <label className="pms-fine">
            Organisation
            <select
              aria-label="Switch organisation"
              value={user.contextId}
              disabled={switching}
              onChange={(event) => void selectContext(event.target.value)}
            >
              {user.contexts.map((context) => (
                <option key={context.id} value={context.id}>
                  {context.name}
                </option>
              ))}
            </select>
          </label>
        ) : isTenantScoped(user.role) && user.tenant ? (
          <OrgSwitcher
            name={user.tenant.name}
            code={user.tenant.code}
            onOpen={() =>
              toast.info(
                `You belong to one tenant, ${user.tenant?.name}. Switching arrives with membership of more than one.`,
                { title: 'Nothing to switch to' },
              )
            }
          />
        ) : undefined
      }
      footer={
        <>
          {canOpenSettings(user.role, granted) ? (
            <RailFooter label="Settings">{item(navigation.settings)}</RailFooter>
          ) : null}
          <form id={signOutFormId} ref={signOutForm} className="pms-console__signout"
            action="/logout" method="post" onSubmit={() => setSigningOut(true)}>
            <Button
              type="submit"
              variant="ghost"
              block
              loading={signingOut}
              loadingLabel="Signing out…"
            >
              <LogoutIcon size={16} />
              <span className="pms-console__signout-label">Sign out</span>
            </Button>
          </form>
        </>
      }
    >
      {/* Home is gated like everything else. It looks like the one item that could be exempt —
          it is only a dashboard — but an exemption here is the shell deciding that one route is
          always safe to offer, which is exactly the judgement that belongs to the permission set. */}
      {granted(navigation.home.permission) ? (
        <RailSection label="Overview">{item(navigation.home)}</RailSection>
      ) : null}
      {navigation.sections.map((section) => {
        const visible = section.items.filter((entry) =>
          granted(entry.permission) &&
          (!entry.anyPermissions || entry.anyPermissions.some((permission) => granted(permission))));
        if (visible.length === 0) return null;
        return (
          <RailSection key={section.id} label={section.label}>
            {visible.map(item)}
          </RailSection>
        );
      })}
    </Rail>
  );

  const topBar = (
    <TopBar
      left={<CollapseToggle collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />}
      right={
        <>
          <ThemeSwitcher label="Colour theme" />
          <NotificationBell
            count={notifications}
            onOpen={() =>
              toast.info('Alerts and invitations will appear here once the API is connected.', {
                title: 'Notifications are not connected',
              })
            }
          />
          <UserMenu
            name={user.name}
            secondary={roleLabel}
            email={user.email}
            items={menuItems}
            onSelect={(id) => {
              if (id === 'password') setChangingPassword(true);
              if (id === 'email') setChangingEmail(true);
              if (id === 'signout') void logout();
            }}
          />
        </>
      }
    >
      {user.tenant ? <ContextChip label={user.tenant.name} tone="brand" /> : null}
      <RoleChip label={roleLabel} />
      {/* The build states its own limits where the user is, not only on the sign-in screen. */}
    </TopBar>
  );

  return (
    <>
      <AppShell
        rail={rail}
        topBar={topBar}
        navigationKey={pathname}
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((value) => !value)}
      >
        {children}
      </AppShell>
      <ChangePasswordDialog
        open={changingPassword}
        email={user.email}
        onClose={() => setChangingPassword(false)}
      />
      <ChangeEmailDialog open={changingEmail} onClose={() => setChangingEmail(false)} />
    </>
  );
}
