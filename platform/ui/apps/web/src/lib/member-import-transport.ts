import 'server-only';
import { ApiError, apiBaseUrl } from './api';
import { consoleSession, resourceId } from './console-api';

export async function importAccess(contextId: string) {
  const { user, token } = await consoleSession('org.members.manage');
  if (user.contextId !== contextId || contextId === 'platform') throw new ApiError(409, 'context_changed');
  return { token, base: '/organizations/' + resourceId(contextId) + '/member-imports' };
}
export async function importRequest(contextId: string, suffix: string, init: RequestInit = {}) {
  const { token, base } = await importAccess(contextId);
  try {
    const response = await fetch(apiBaseUrl() + base + suffix, { ...init, cache: 'no-store', redirect: 'error',
      signal: AbortSignal.timeout(120000), headers: { ...init.headers, Authorization: 'Bearer ' + token } });
    if (!response.ok) {
      const data = await response.json();
      throw new ApiError(response.status, typeof data?.error?.code === 'string' ? data.error.code : 'unavailable');
    }
    return response;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(503, 'unavailable');
  }
}
