import { describe, expect, it } from 'vitest';
import { NAVIGATION, isActive } from '../src/lib/navigation';
import { ROLE_CODES, ROLE_PERMISSIONS, isTenantScoped } from '../src/lib/roles';

/**
 * The navigation table and the permission catalogue have to agree.
 *
 * They are written apart — the table by whoever designs the console, the catalogue by whoever
 * owns the database — so the failure mode is a menu item gated on a permission its own role does
 * not hold. It disappears silently, because the shell filters on exactly that key, and the bug
 * looks like "the menu is missing an item" rather than "the key is wrong".
 */

describe('navigation', () => {
  it('gates every item on a permission the role actually holds', () => {
    for (const role of ROLE_CODES) {
      const held = new Set(ROLE_PERMISSIONS[role]);
      const navigation = NAVIGATION[role];
      const items = [
        navigation.home,
        navigation.settings,
        ...navigation.sections.flatMap((section) => section.items),
      ];

      for (const item of items) {
        expect(held.has(item.permission), `${role} → ${item.label} (${item.permission})`).toBe(
          true,
        );
      }
    }
  });

  it('gives every role a home, a settings destination and at least one section', () => {
    for (const role of ROLE_CODES) {
      const navigation = NAVIGATION[role];
      expect(navigation.home.href).toBe('/home');
      expect(navigation.settings.href).toBe('/settings');
      expect(navigation.sections.length).toBeGreaterThan(0);
      for (const section of navigation.sections) {
        expect(section.items.length).toBeGreaterThan(0);
        expect(section.label).not.toBe('');
      }
    }
  });

  it('uses one route per destination id across roles', () => {
    /* Two roles may both offer "Devices"; they must not disagree about where it lives, or a
     * shared component would have to know who is looking at it. */
    const routes = new Map<string, string>();
    for (const role of ROLE_CODES) {
      for (const item of NAVIGATION[role].sections.flatMap((section) => section.items)) {
        const known = routes.get(item.id);
        if (known) expect(item.href, item.id).toBe(known);
        else routes.set(item.id, item.href);
      }
    }
    expect(routes.get('devices')).toBe('/devices');
  });

  it('offers the platform administrator the tenant-wide destinations only', () => {
    const items = NAVIGATION.platform_admin.sections.flatMap((section) => section.items);
    const ids = items.map((item) => item.id);

    expect(ids).toContain('tenants');
    expect(ids).not.toContain('models');
    expect(ids).not.toContain('users');
    expect(ids).not.toContain('licenses');
    expect(ids).toContain('logs');
    expect(ids).not.toContain('categories');
    expect(ids).not.toContain('patients');
    expect(ids).not.toContain('cases');
    expect(ids).not.toContain('scenarios');
    /* A platform administrator has no tenant of their own, so no member list and no practice. */
    expect(ids).not.toContain('members');
    expect(ids).not.toContain('sessions');
    expect(isTenantScoped('platform_admin')).toBe(false);
  });

  it('separates a tenant administrator from a tenant user', () => {
    const adminIds = NAVIGATION.org_admin.sections.flatMap((s) => s.items).map((i) => i.id);
    const userIds = NAVIGATION.org_user.sections.flatMap((s) => s.items).map((i) => i.id);

    expect(adminIds).toEqual(
      expect.arrayContaining(['members', 'devices', 'sessions', 'logs']),
    );
    expect(adminIds).not.toContain('models');
    expect(adminIds).not.toContain('departments');
    /* The user sees their own practice and the devices they use — nothing that manages people. */
    expect(userIds).toEqual(expect.arrayContaining(['sessions', 'recordings', 'devices']));
    expect(userIds).not.toContain('members');
    expect(userIds).not.toContain('departments');
    expect(userIds).toContain('logs');
    expect(NAVIGATION.org_user.sections.some((section) => section.label === 'Training')).toBe(true);
    expect(userIds).toEqual(expect.arrayContaining(['scenarios', 'sessions']));
    expect(userIds).not.toContain('practice');
  });

  it('marks a destination active for itself and its children only', () => {
    expect(isActive('/devices', '/devices')).toBe(true);
    expect(isActive('/devices', '/devices/42')).toBe(true);
    expect(isActive('/devices', '/devices-archive')).toBe(false);
    expect(isActive('/home', '/devices')).toBe(false);
  });
});
