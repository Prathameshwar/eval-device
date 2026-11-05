import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { SettingsHub } from '../src/components/SettingsHub';
import { canOpenSettings, canOpenSettingsRoute, settingsFor } from '../src/lib/settings';
import { ROLE_PERMISSIONS, type RoleCode } from '../src/lib/roles';

const sectionsFor = (role: RoleCode, permissions: readonly string[] = ROLE_PERMISSIONS[role]) =>
  settingsFor(role, (key) => permissions.includes(key));

describe('Settings access', () => {
  it('keeps the platform categories out of tenant settings', () => {
    expect(sectionsFor('platform_admin').map((s) => s.id)).toEqual([
      'models',
      'platform-options',
      'licenses',
      'users',
    ]);
    expect(sectionsFor('org_admin').map((s) => s.id)).toEqual([
      'departments',
      'scenarios',
    ]);
    expect(sectionsFor('org_user')).toEqual([]);
    expect(sectionsFor('org_admin', ROLE_PERMISSIONS.platform_admin)).toEqual([]);
    expect(sectionsFor('org_user', ROLE_PERMISSIONS.platform_admin)).toEqual([]);
  });

  it.each([
    ['platform.settings.read', 'platform-options'],
    ['platform.organizations.read', 'licenses'],
    ['platform.users.read', 'users'],
  ])('lets a %s reader reach only their card', (permission, id) => {
    const granted = (key: string) => key === permission;
    expect(canOpenSettings('platform_admin', granted)).toBe(true);
    expect(settingsFor('platform_admin', granted).map((s) => s.id)).toEqual(
      [id],
    );
  });

  it('does not turn settings-manage into access to every category', () => {
    const granted = (key: string) => key === 'platform.settings.manage';
    expect(canOpenSettings('platform_admin', granted)).toBe(true);
    expect(settingsFor('platform_admin', granted).map(section => section.id)).toEqual(['models']);
  });

  it('denies a missing permission set for every role', () => {
    for (const role of ['platform_admin', 'org_admin', 'org_user'] as const) {
      expect(canOpenSettings(role, () => false)).toBe(false);
      expect(settingsFor(role, () => false)).toEqual([]);
    }
  });

  it('restricts model and LLM management to the platform role', () => {
    const grants = (permission: string) => ROLE_PERMISSIONS.org_admin.includes(permission);
    expect(canOpenSettingsRoute('org_admin', 'models', grants)).toBe(false);
    expect(canOpenSettingsRoute('org_admin', 'llm-connections', grants)).toBe(false);
    expect(canOpenSettingsRoute('org_user', 'llm-connections', grants)).toBe(false);
    expect(canOpenSettingsRoute('platform_admin', 'llm-connections', grants)).toBe(false);
    expect(canOpenSettingsRoute('platform_admin', 'llm-connections', permission => ROLE_PERMISSIONS.platform_admin.includes(permission))).toBe(false);
    expect(canOpenSettingsRoute('platform_admin', 'models', permission => ROLE_PERMISSIONS.platform_admin.includes(permission))).toBe(true);
  });
});

describe('Settings cards', () => {
  it('offers one named keyboard link per card in visual order', async () => {
    const user = userEvent.setup();
    render(<SettingsHub sections={sectionsFor('platform_admin')} tenantScoped={false} />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Settings');
    const cards = screen.getByRole('region', { name: 'Settings sections' });
    const links = within(cards).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/models',
      '/platform-options',
      '/licenses',
      '/users',
    ]);
    expect(within(cards).queryByRole('button')).not.toBeInTheDocument();
    await user.tab();
    expect(screen.getByRole('link', { name: 'Back to home' })).toHaveFocus();
    for (const title of ['Models', 'Platform options', 'Subscriptions', 'Users & administrators']) {
      await user.tab();
      const link = screen.getByRole('link', { name: title });
      expect(link).toHaveFocus();
      expect(link).toHaveAccessibleDescription(/manage/i);
      expect(within(link).getByRole('heading', { level: 2 })).toHaveTextContent(title);
    }
  });

  it('shows the two clinical destinations and links departments from tenant settings', () => {
    render(<SettingsHub sections={sectionsFor('org_admin')} tenantScoped />);
    const cards = screen.getByRole('region', { name: 'Settings sections' });
    expect(within(cards).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual([
      '/scenarios',
    ]);
    expect(within(screen.getByRole('navigation', { name: 'Tenant administration' })).getByRole('link', { name: 'Departments' })).toHaveAttribute('href', '/departments');
    expect(within(cards).queryByRole('link', { name: 'LLM connections' })).not.toBeInTheDocument();
    expect(within(cards).queryByRole('link', { name: 'Models' })).not.toBeInTheDocument();
  });

  it('handles a settings account without accessible categories', () => {
    render(<SettingsHub sections={[]} tenantScoped={false} />);
    expect(screen.getByText('No settings sections available')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to home' })).toHaveAttribute('href', '/home');
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });
});
