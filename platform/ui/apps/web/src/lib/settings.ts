import type { ComponentType } from 'react';
import { CustomersIcon, ReportsIcon, RolesIcon } from '@pms/ui';
import { LicenseIcon, ModelIcon } from '@/components/icons-product';
import type { RoleCode } from './roles';

export type SettingsId =
  | 'models'
  | 'llm-connections'
  | 'licenses'
  | 'users'
  | 'platform-options'
  | 'connections'
  | 'profiles'
  | 'scenarios'
  | 'departments';
export type SettingsDestination = {
  id: SettingsId;
  title: string;
  description: string;
  action: string;
  href: string;
  icon: ComponentType<{ size?: number }>;
  permission: string;
};

/** The existing Settings entry also serves personal settings for a tenant user. */
export const SETTINGS_PERMISSION: Record<RoleCode, string> = {
  platform_admin: 'platform.settings.manage',
  org_admin: 'org.settings.manage',
  org_user: 'org.devices.summary.read',
};

const PLATFORM_MODELS: SettingsDestination = {
  id: 'models',
  title: 'Models',
  description: 'Create and manage local and cloud models for devices.',
  action: 'Manage models',
  href: '/models',
  icon: ModelIcon,
  permission: 'platform.settings.manage',
};

/** Role scope and permission are both required, even when roles share a grant. */
export const SETTINGS_DESTINATIONS: Record<RoleCode, readonly SettingsDestination[]> = {
  platform_admin: [
    PLATFORM_MODELS,
    {
      id: 'platform-options',
      title: 'Platform options',
      description: 'Manage language choices, registration and operating options.',
      action: 'Manage options',
      href: '/platform-options',
      icon: RolesIcon,
      permission: 'platform.settings.read',
    },
    {
      id: 'licenses',
      title: 'Subscriptions',
      description: 'Manage tenant subscriptions, validity and device allowances.',
      action: 'Manage subscriptions',
      href: '/licenses',
      icon: LicenseIcon,
      permission: 'platform.organizations.read',
    },
    {
      id: 'users',
      title: 'Users & administrators',
      description: 'Manage user accounts, administrator roles and account setup.',
      action: 'Manage users',
      href: '/users',
      icon: RolesIcon,
      permission: 'platform.users.read',
    },
  ],
  org_admin: [
    {
      id: 'departments',
      title: 'Departments',
      description: 'Manage departments and their availability for members and devices.',
      action: 'Manage departments',
      href: '/departments',
      icon: RolesIcon,
      permission: 'org.departments.manage',
    },
    {
      id: 'scenarios',
      title: 'Scenarios',
      description: 'Create scenarios with presentation, symptoms, history, and vitals, then submit them for clinical review.',
      action: 'Manage scenarios',
      href: '/scenarios',
      icon: ReportsIcon,
      permission: 'org.clinical.author',
    },
  ],
  org_user: [],
};

type Granted = (permission: string) => boolean;

export function settingsFor(role: RoleCode, granted: Granted): readonly SettingsDestination[] {
  return SETTINGS_DESTINATIONS[role].filter((section) => granted(section.permission));
}

/** A settings route is available only when its role has a visible, permitted destination. */
export function canOpenSettingsRoute(role: RoleCode, id: SettingsId, granted: Granted): boolean {
  return settingsFor(role, granted).some(section => section.id === id);
}

/** A reader must still reach their card when the separate settings-manage grant is absent. */
export function canOpenSettings(role: RoleCode, granted: Granted): boolean {
  return granted(SETTINGS_PERMISSION[role]) || settingsFor(role, granted).length > 0;
}
