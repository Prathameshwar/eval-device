/**
 * What each role sees in the rail.
 *
 * Declared per role rather than derived from permissions alone, because two roles can hold the
 * same grant and still want different navigation: `org_admin` and `org_user` both hold
 * `org.devices.read`, but one manages a fleet and the other checks the device in front of them,
 * and no permission key expresses that difference.
 *
 * Every item still carries the permission the server will enforce, and the shell filters the
 * table through `useGranted()` before drawing it. So the table decides *shape* and the
 * permission set decides *visibility* — an item whose grant is missing disappears even if it is
 * listed here. `tests/navigation.test.ts` asserts the two can never drift: every permission named
 * below must be one the role actually holds in the catalogue.
 *
 * Drawing a menu item is not authorization. The server authorizes; this only decides what is
 * worth showing someone.
 */

import type { ComponentType } from 'react';
import { ActivityIcon, AuditIcon, CustomersIcon, DashboardIcon, ReportsIcon, SettingsIcon } from '@pms/ui';
import { DeviceIcon, SessionIcon, TenantIcon } from '@/components/icons-product';
import type { RoleCode } from './roles';
import { SETTINGS_PERMISSION } from './settings';

export type NavIcon = ComponentType<{ size?: number }>;

export type NavItem = {
  id: string;
  label: string;
  href: string;
  icon: NavIcon;
  /** The catalogue key the server enforces for this destination. */
  permission: string;
  anyPermissions?: readonly string[];
};

export type NavSection = {
  id: string;
  /** Names the `<nav>` through `aria-labelledby` — a real group label, not decoration. */
  label: string;
  items: NavItem[];
};

export type Navigation = {
  home: NavItem;
  sections: NavSection[];
  /** The rail's pinned base. Logout is not here: it is an action, not a destination. */
  settings: NavItem;
};

/* Home is the same destination for everyone; only the dashboard behind it differs. The
 * permission is one every role in the catalogue holds, so it is never filtered away. */
const HOME_PERMISSION: Record<RoleCode, string> = {
  platform_admin: 'platform.health.read',
  org_admin: 'org.devices.summary.read',
  org_user: 'org.devices.summary.read',
};

function home(role: RoleCode): NavItem {
  return {
    id: 'home',
    label: 'Home',
    href: '/home',
    icon: DashboardIcon,
    permission: HOME_PERMISSION[role],
  };
}

export const NAVIGATION: Record<RoleCode, Navigation> = {
  platform_admin: {
    home: home('platform_admin'),
    sections: [
      {
        id: 'manage',
        label: 'Manage',
        items: [
          {
            id: 'tenants',
            label: 'Tenants',
            href: '/tenants',
            icon: TenantIcon,
            permission: 'platform.organizations.read',
          },
          {
            id: 'devices',
            label: 'Devices',
            href: '/devices',
            icon: DeviceIcon,
            permission: 'platform.health.read',
          },
          {
            id: 'logs',
            label: 'Logs',
            href: '/logs',
            icon: AuditIcon,
            permission: 'platform.audit.read',
          },
        ],
      },
    ],
    settings: {
      id: 'settings',
      label: 'Settings',
      href: '/settings',
      icon: SettingsIcon,
      permission: SETTINGS_PERMISSION.platform_admin,
    },
  },

  org_admin: {
    home: home('org_admin'),
    sections: [
      {
        id: 'manage',
        label: 'Manage',
        items: [
          {
            id: 'members',
            label: 'Members',
            href: '/members',
            icon: CustomersIcon,
            permission: 'org.members.manage',
          },
          {
            id: 'devices',
            label: 'Devices',
            href: '/devices',
            icon: DeviceIcon,
            permission: 'org.devices.manage',
          },
        ],
      },
      {
        id: 'clinical',
        label: 'Clinical content',
        items: [
          { id: 'scenarios', label: 'Scenarios', href: '/scenarios',
            icon: ReportsIcon, permission: 'org.status.read',
            anyPermissions: ['org.clinical.author', 'org.clinical.review'] },
        ],
      },
      {
        id: 'activity',
        label: 'Activity',
        items: [
          {
            id: 'sessions',
            label: 'Sessions',
            href: '/sessions',
            icon: SessionIcon,
            permission: 'org.results.read',
          },
          {
            id: 'reports',
            label: 'Reports',
            href: '/reports',
            icon: ReportsIcon,
            permission: 'org.activity.read',
          },
          {
            id: 'recordings',
            label: 'Recordings',
            href: '/recordings',
            icon: ActivityIcon,
            permission: 'org.media.read',
          },
          {
            id: 'logs',
            label: 'Logs',
            href: '/logs',
            icon: AuditIcon,
            permission: 'org.audit.read',
          },
        ],
      },
    ],
    settings: {
      id: 'settings',
      label: 'Settings',
      href: '/settings',
      icon: SettingsIcon,
      permission: SETTINGS_PERMISSION.org_admin,
    },
  },

  org_user: {
    home: home('org_user'),
    sections: [
      {
        id: 'clinical',
        label: 'Clinical content',
        items: [
          { id: 'scenarios', label: 'Scenarios', href: '/scenarios',
            icon: ReportsIcon, permission: 'org.status.read',
            anyPermissions: ['org.clinical.author', 'org.clinical.review'] },
        ],
      },
      {
        id: 'training',
        label: 'Training',
        items: [
          {
            id: 'sessions',
            label: 'My sessions',
            href: '/sessions',
            icon: SessionIcon,
            permission: 'org.results.read',
          },
          {
            id: 'recordings',
            label: 'Recordings',
            href: '/recordings',
            icon: ActivityIcon,
            permission: 'org.media.read',
          },
          {
            id: 'devices',
            label: 'Devices',
            href: '/devices',
            icon: DeviceIcon,
            permission: 'org.devices.summary.read',
          },
          {
            id: 'logs',
            label: 'Logs',
            href: '/logs',
            icon: AuditIcon,
            permission: 'org.activity.read',
          },
        ],
      },
    ],
    /* A tenant user has no `org.settings.manage`; their settings page is their own profile, so
     * it is gated on something they do hold. */
    settings: {
      id: 'settings',
      label: 'Settings',
      href: '/settings',
      icon: SettingsIcon,
      permission: SETTINGS_PERMISSION.org_user,
    },
  },
};

/** True when `href` is the current page, or its parent section. */
export function isActive(href: string, pathname: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
