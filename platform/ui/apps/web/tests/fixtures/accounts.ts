/** Fictional identities for presentation tests. Production never imports these fixtures. */

import { ROLE_PERMISSIONS } from '../../src/lib/roles';
import type { SessionUser } from '../../src/lib/session-user';

export type DemoUser = SessionUser;

export const DEMO_USERS: readonly DemoUser[] = [
  {
    id: 'platform-admin',
    name: 'Asha Menon',
    email: 'platformadmin@example.com',
    role: 'platform_admin',
    passwordManagement: true,
    permissions: ROLE_PERMISSIONS.platform_admin,
  },
  {
    id: 'platform-admin-evaluation',
    name: 'Platform Admin',
    email: 'platform.admin@evaluation.com',
    role: 'platform_admin',
    passwordManagement: true,
    permissions: ROLE_PERMISSIONS.platform_admin,
  },
  {
    id: 'tenant-admin',
    name: 'Dr Rahul Iyer',
    email: 'tenantadmin@example.com',
    role: 'org_admin',
    tenant: { name: 'Northside Medical College', code: 'NMC' },
    passwordManagement: true,
    permissions: ROLE_PERMISSIONS.org_admin,
  },
  {
    id: 'tenant-user',
    name: 'Priya Nair',
    email: 'user@example.com',
    role: 'org_user',
    tenant: { name: 'Northside Medical College', code: 'NMC' },
    passwordManagement: true,
    permissions: ROLE_PERMISSIONS.org_user,
  },
];

export function findDemoUser(id: string): DemoUser | undefined {
  return DEMO_USERS.find((user) => user.id === id);
}

/**
 * Case-insensitive: a domain is case-insensitive by RFC 1035 and every provider treats the local
 * part that way too. The password comparison, in `demo-auth.ts`, is exact — passwords are not.
 */
export function findDemoUserByEmail(email: string): DemoUser | undefined {
  const wanted = email.trim().toLowerCase();
  return DEMO_USERS.find((user) => user.email.toLowerCase() === wanted);
}
