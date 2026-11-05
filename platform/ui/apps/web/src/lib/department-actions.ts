'use server';
import { ApiError, apiRequest } from './api';
import { consoleSession, resourceId, queryString } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult, DirectoryPage } from './directory-api';
export type ManagedDepartment = {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  archived_at: string | null;
  management_version: number;
};
async function access(contextId: string) {
  const s = await consoleSession('org.departments.manage');
  if (s.user.contextId !== contextId) throw new ApiError(409, 'context_changed');
  return {
    token: s.token,
    base: '/organizations/' + resourceId(contextId) + '/departments',
  };
}
export async function listDepartments(
  contextId: string,
  query: { q: string; archived: string; limit: number },
  cursor?: string,
): Promise<ApiResult<DirectoryPage<ManagedDepartment>>> {
  try {
    const { base, token } = await access(contextId);
    return {
      value: await apiRequest<DirectoryPage<ManagedDepartment>>(
        base +
          '?' +
          queryString({
            ...query,
            cursor,
            include_total: true,
            sort_by: 'name',
          }),
        { token },
      ),
    };
  } catch (e) {
    return { error: consoleError(e) };
  }
}
export async function readDepartment(contextId: string, id: string): Promise<ApiResult<ManagedDepartment>> {
  try {
    const { base, token } = await access(contextId);
    return {
      value: await apiRequest<ManagedDepartment>(base + '/' + resourceId(id), {
        token,
      }),
    };
  } catch (e) {
    return { error: consoleError(e) };
  }
}
export async function saveDepartment(
  contextId: string,
  row: ManagedDepartment,
): Promise<ApiResult<ManagedDepartment>> {
  try {
    const { base, token } = await access(contextId);
    if (!row.name.trim()) return { error: 'Enter a department name.' };
    return {
      value: await apiRequest<ManagedDepartment>(base + (row.id ? '/' + resourceId(row.id) : ''), {
        token,
        method: row.id ? 'PATCH' : 'POST',
        body: {
          name: row.name.trim(),
          description: row.description?.trim() || null,
          ...(row.id
            ? {
                expected_version: row.management_version,
                is_active: row.is_active,
              }
            : {}),
        },
      }),
    };
  } catch (e) {
    return { error: consoleError(e) };
  }
}
export async function changeDepartmentState(
  contextId: string,
  row: ManagedDepartment,
): Promise<ApiResult<ManagedDepartment>> {
  try {
    const { base, token } = await access(contextId);
    return {
      value: await apiRequest<ManagedDepartment>(
        base +
          '/' +
          resourceId(row.id) +
          (row.archived_at ? '/restore' : '?expected_version=' + row.management_version),
        {
          token,
          method: row.archived_at ? 'POST' : 'DELETE',
          ...(row.archived_at ? { body: { expected_version: row.management_version } } : {}),
        },
      ),
    };
  } catch (e) {
    return { error: consoleError(e) };
  }
}
