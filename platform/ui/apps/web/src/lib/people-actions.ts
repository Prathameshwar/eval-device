'use server';
import { revalidatePath } from 'next/cache';
import { ApiError, apiRequest } from './api';
import { allOptions, consoleSession, queryString, resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult, DirectoryPage } from './directory-api';
import { personView, type DepartmentOption, type TenantOption, type PeopleQuery, type Person, type PersonAction, type PersonDraft, type PersonResult } from './people';

function peopleError(error: unknown) {
  return error instanceof ApiError && error.code === 'state_conflict'
    ? 'This change conflicts with the current record state. Keep an active administrator for the platform and each active tenant, then refresh and try again.'
    : consoleError(error);
}

async function access(contextId: string, write = false) {
  const platform = contextId === 'platform';
  const { user, token } = await consoleSession(platform ? `platform.users.${write ? 'manage' : 'read'}` : 'org.members.manage');
  if (user.contextId !== contextId) throw new ApiError(409, 'context_changed');
  return { user, token, platform, base: platform ? '/platform/users' : '/organizations/' + resourceId(contextId) };
}
function version(value?: number) {
  if (!Number.isInteger(value) || value! < 1) throw new ApiError(422, 'invalid_request');
  return value!;
}
export async function peopleDepartments(contextId: string): Promise<ApiResult<DepartmentOption[]>> {
  try {
    const { base, token, platform } = await access(contextId);
    return { value: platform ? [] : await allOptions<DepartmentOption>(base + '/departments', token) };
  } catch (error) { return { error: peopleError(error) }; }
}
export async function peopleTenants(): Promise<ApiResult<TenantOption[]>> {
  try {
    const { user, token } = await consoleSession('platform.organization_admins.manage');
    if (user.contextId !== 'platform' || !user.permissions.includes('platform.organizations.read')) throw new ApiError(403, 'permission_denied');
    return { value: await allOptions<TenantOption>('/platform/organizations?archived=false', token) };
  } catch (error) { return { error: peopleError(error) }; }
}
export async function listPeople(contextId: string, query: PeopleQuery, cursor?: string): Promise<ApiResult<DirectoryPage<Person>>> {
  try {
    const { base, token, platform } = await access(contextId);
    const archived = query.state === 'all' ? undefined : query.state === 'archived';
    const is_active = query.state === 'enabled' ? true : query.state === 'disabled' ? false : undefined;
    const invitation_status = ['pending', 'expired', 'revoked', 'accepted'].includes(query.state) ? query.state : is_active !== undefined ? 'accepted' : undefined;
    const params = { q: query.q, limit: query.limit, cursor, include_total: true, sort_by: query.sort_by, sort_order: query.sort_order,
      archived, is_active, ...(platform ? { platform_role: query.role, auth_method: query.auth_method } : { role: query.role, department_id: query.department_id, invitation_status }) };
    const page = await apiRequest<DirectoryPage<Person>>(base + (platform ? '' : '/members') + '?' + queryString(params), { token });
    return { value: { ...page, items: page.items.map(row => personView(row, platform)) } };
  } catch (error) { return { error: peopleError(error) }; }
}
export async function readPerson(contextId: string, id: string): Promise<ApiResult<Person>> {
  try {
    const { base, token, platform } = await access(contextId);
    return { value: personView(await apiRequest<Person>(base + (platform ? '/' : '/members/') + resourceId(id), { token }), platform) };
  } catch (error) { return { error: peopleError(error) }; }
}
export async function savePerson(contextId: string, draft: PersonDraft, id?: string, expectedVersion?: number): Promise<ApiResult<PersonResult>> {
  try {
    const { base, token, platform, user } = await access(contextId, true);
    if (id) version(expectedVersion);
    if (platform && draft.role === 'platform_admin' && !user.permissions.includes('platform.administrators.manage')) throw new ApiError(403, 'permission_denied');
    if (platform && !id && !['platform_admin', 'org_admin'].includes(draft.role)) return { error: 'Choose Platform administrator or Tenant administrator.' };
    if (platform && id && !['', 'platform_admin'].includes(draft.role)) throw new ApiError(422, 'invalid_request');
    if (platform && !id && draft.role === 'org_admin' && !user.permissions.includes('platform.organization_admins.manage')) throw new ApiError(403, 'permission_denied');
    if (platform && !id && draft.role === 'org_admin' && !draft.organization_id) return { error: 'Select a tenant for this administrator.' };
    let result: PersonResult;
    if (platform) {
      // Identity provider profiles are read-only; email changes use the verified account flow.
      const body = { ...(draft.auth_method === 'local' ? { display_name: draft.display_name.trim(), phone: draft.phone.trim() || null } : {}),
        ...(user.permissions.includes('platform.administrators.manage') ? { platform_role: draft.role === 'platform_admin' ? 'platform_admin' : null } : {}),
        ...(id ? { expected_version: expectedVersion, is_active: draft.is_active, status_reason: draft.status_reason.trim() || null } : {
          email: draft.email.trim(), ...(draft.role === 'org_admin' ? { organization_id: resourceId(draft.organization_id!) } : {}),
        }) };
      if (id === user.id && draft.is_active === false) throw new ApiError(403, 'self_account_action');
      if (id) result = { person: await apiRequest<Person>(base + '/' + resourceId(id), { token, method: 'PATCH', body }) };
      else {
        const created = await apiRequest<{ user: Person; email_delivered?: boolean; invitation_token?: string | null; setup_token?: string | null }>(base, { token, method: 'POST', body });
        result = { person: created.user, setup_queued: true, email_delivered: created.email_delivered, invitation_token: created.invitation_token, setup_token: created.setup_token };
      }
    } else if (id) {
      const person = await apiRequest<Person>(base + '/members/' + resourceId(id), { token, method: 'PATCH', body: {
        expected_version: expectedVersion, role: draft.role, department_id: draft.department_id || null,
        status_reason: draft.status_reason.trim() || null,
      } });
      result = { person: personView(person, false) };
    } else {
      const created = await apiRequest<{ membership: Person; email_delivered: boolean; invitation_token: string | null; setup_token?: string | null }>(base + '/invitations', { token, method: 'POST', body: {
        email: draft.email.trim(), auth_method: draft.auth_method, local_display_name: draft.auth_method === 'local' ? draft.display_name.trim() : null,
        role: draft.role, department_id: draft.department_id || null,
      } });
      result = { person: personView(created.membership, false), email_delivered: created.email_delivered, invitation_token: created.invitation_token, setup_token: created.setup_token };
    }
    revalidatePath(platform ? '/users' : '/members');
    return { value: result };
  } catch (error) { return { error: peopleError(error) }; }
}
export async function managePerson(contextId: string, id: string, action: PersonAction, expectedVersion: number): Promise<ApiResult<PersonResult>> {
  try {
    const { base, token, platform, user } = await access(contextId, true);
    version(expectedVersion);
    if (platform && id === user.id && ['disable', 'archive'].includes(action)) throw new ApiError(403, 'self_account_action');
    if (!(platform ? ['archive', 'restore', 'enable', 'disable', 'setup'] : ['archive', 'restore', 'enable', 'disable', 'resend', 'revoke']).includes(action)) throw new ApiError(422, 'invalid_request');
    const path = base + (platform ? '/' : '/members/') + resourceId(id);
    const fence = '?' + queryString({ expected_version: expectedVersion });
    let result: PersonResult;
    if (action === 'resend') {
      const response = await apiRequest<{ membership: Person; email_delivered: boolean; invitation_token: string | null }>(base + '/invitations/' + resourceId(id) + '/resend' + fence, { token, method: 'POST' });
      result = { person: personView(response.membership, false), email_delivered: response.email_delivered, invitation_token: response.invitation_token };
    } else if (action === 'setup') {
      const response = await apiRequest<{ user: Person; setup_token?: string | null }>(path + '/setup/resend' + fence, { token, method: 'POST' });
      result = { person: response.user, setup_queued: true, setup_token: response.setup_token };
    } else {
      const target = action === 'revoke' ? base + '/invitations/' + resourceId(id) + fence : path + (action === 'restore' ? '/restore' : action === 'archive' ? fence : '');
      const response = await apiRequest<Person>(target, { token,
        method: action === 'archive' || action === 'revoke' ? 'DELETE' : action === 'restore' ? 'POST' : 'PATCH',
        ...(['restore', 'enable', 'disable'].includes(action) ? { body: { expected_version: expectedVersion, ...(action !== 'restore' ? { is_active: action === 'enable' } : {}) } } : {}),
      });
      result = { person: personView(response, platform) };
    }
    revalidatePath(platform ? '/users' : '/members');
    return { value: result };
  } catch (error) { return { error: peopleError(error) }; }
}
