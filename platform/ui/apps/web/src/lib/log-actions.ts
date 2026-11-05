'use server';
import { ApiError, apiRequest } from './api';
import { queryString, resourceId } from './console-api';
import { consoleError } from './console-errors';
import { currentUser, sessionToken } from './session';
import { logCategories, logDate, type ActivityEvent, type LogCategory, type LogQuery } from './log-directory';
import type { ApiResult, DirectoryPage } from './directory-api';

async function access(contextId: string, category?: LogCategory) {
  const user = await currentUser();
  if (!user) throw new ApiError(401, 'authentication_required');
  const categories = logCategories(user);
  if (!categories.length || category !== undefined && !categories.includes(category)) throw new ApiError(403, 'permission_denied');
  if (user.contextId !== contextId) throw new ApiError(409, 'context_changed');
  return { token: await sessionToken(), base: contextId === 'platform' ? '/platform/audit' : '/organizations/' + resourceId(contextId) + '/activities' };
}
export async function listLogs(contextId: string, query: LogQuery, cursor?: string): Promise<ApiResult<DirectoryPage<ActivityEvent>>> {
  try {
    const { base, token } = await access(contextId, query.category);
    let since: string | undefined; let until: string | undefined;
    try { since = logDate(query.since); until = logDate(query.until, true); }
    catch { throw new ApiError(422, 'invalid_date_range'); }
    if (since && until && since >= until) throw new ApiError(422, 'invalid_date_range');
    const params = { ...query, since, until, cursor, include_total: true,
      organization_id: contextId === 'platform' && query.organization_id ? resourceId(query.organization_id) : undefined,
      device_id: query.device_id ? resourceId(query.device_id) : undefined,
    };
    return { value: await apiRequest<DirectoryPage<ActivityEvent>>(base + '?' + queryString(params), { token }) };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function readLog(contextId: string, id: string): Promise<ApiResult<ActivityEvent>> {
  try {
    const { base, token } = await access(contextId);
    return { value: await apiRequest<ActivityEvent>(base + '/' + resourceId(id), { token }) };
  } catch (error) { return { error: consoleError(error) }; }
}
