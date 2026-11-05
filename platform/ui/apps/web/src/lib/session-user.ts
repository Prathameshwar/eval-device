import type { RoleCode } from './roles';

export type AccessContext = {
  id: string;
  name: string;
  role: string;
  department_id: string | null;
  permissions: readonly string[];
};

/** Identity and permissions originate from the API, never from a cookie's role claims. */
export type SessionUser = {
  id: string;
  name: string;
  email: string;
  role: RoleCode;
  roleLabel?: string;
  tenant?: { name: string; code: string };
  permissions: readonly string[];
  passwordManagement?: boolean;
  contexts?: readonly AccessContext[];
  contextId?: string;
  needsAccess?: boolean;
};

export type IdentityContext = {
  user: { id: string; display_name: string; email: string; password_management: boolean };
  contexts: AccessContext[];
};

export function sessionUser(identity: IdentityContext, selected?: string): SessionUser {
  const context = identity.contexts.find((item) => item.id === selected) ?? identity.contexts[0];
  const actualRole = context?.role;
  const role: RoleCode = actualRole === 'platform_admin' || actualRole === 'org_admin' ? actualRole : 'org_user';
  const labels: Record<string, string> = {
    platform_admin: 'Platform Admin', org_admin: 'Tenant Admin', org_user: 'Tenant User',
    org_read_only: 'Read only', org_trainee: 'Trainee',
  };
  return {
    id: identity.user.id, name: identity.user.display_name, email: identity.user.email,
    role, roleLabel: actualRole ? labels[actualRole] ?? 'Member' : 'Account',
    permissions: context?.permissions ?? [], passwordManagement: identity.user.password_management,
    contexts: identity.contexts, contextId: context?.id, needsAccess: !context,
    tenant: context && context.id !== 'platform' ? { name: context.name, code: context.name.slice(0, 3).toUpperCase() } : undefined,
  };
}
