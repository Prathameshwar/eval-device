import 'server-only';
import { ApiError, apiRequest } from './api';
import { currentUser, sessionToken } from './session';
export async function consoleSession(permission: string) {
  const user = await currentUser();
  if (!user) throw new ApiError(401, 'authentication_required');
  if (!user.permissions.includes(permission)) throw new ApiError(403, 'permission_denied');
  const token = await sessionToken();
  return { user, token };
}
export function resourceId(id: string) {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) throw new ApiError(404, 'not_found');
  return id;
}
export function queryString(query: object) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (value !== undefined && value !== '' && value !== null) params.set(key, String(value));
  return params.toString();
}
export async function allOptions<T>(path: string, token?: string): Promise<T[]> {
  const rows: T[] = [];
  let cursor: string | null = null;
  do {
    const result: { items: T[]; next_cursor?: string | null } = await apiRequest(path + (path.includes('?') ? '&' : '?') + queryString({ limit: 100, cursor }), { token });
    rows.push(...result.items);
    cursor = result.next_cursor ?? null;
  } while (cursor);
  return rows;
}
