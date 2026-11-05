import type { SessionUser } from './session-user';

export function canDownload(user: SessionUser): boolean {
  if (user.needsAccess) return false;
  if (user.contexts) return user.contexts.some((context) => context.role === 'platform_admin' ||
    (context.role === 'org_admin' && context.department_id === null));
  return user.role === 'platform_admin' || user.role === 'org_admin';
}
