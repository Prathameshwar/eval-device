'use server';
import { revalidatePath } from 'next/cache';
import { apiRequest } from './api';
import { allOptions, consoleSession, queryString, resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult, DirectoryPage } from './directory-api';
import type { Tenant, TenantQuery } from './tenant-directory';
import type { TenantDraft } from './tenant-editor';
export type TenantSupport = {
  subscription: { plan: { name: string }; usage: { users: number; devices: number }; remaining: { users: number; devices: number }; over_limit: boolean };
  administrators: { items: { id: string; display_name: string; email: string }[] };
};
export async function tenantPlans() {
  const { token } = await consoleSession('platform.organizations.read');
  const result = await apiRequest<{ items: { id: string; name: string; is_active: boolean }[] }>('/platform/subscription-plans', { token });
  return { plans: Object.fromEntries(result.items.map(p => [p.id, p.name])), activePlans: Object.fromEntries(result.items.filter(p => p.is_active).map(p => [p.id, p.name])) };
}
export async function listTenants(query: TenantQuery, cursor?: string): Promise<ApiResult<DirectoryPage<Tenant>>> {
  try {
    const { token } = await consoleSession('platform.organizations.read');
    return { value: await apiRequest<DirectoryPage<Tenant>>('/platform/organizations?' + queryString({ ...query, cursor, include_total: true }), { token }) };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function readTenant(id: string): Promise<ApiResult<Tenant>> {
  try {
    const { token } = await consoleSession('platform.organizations.read');
    return { value: await apiRequest<Tenant>('/platform/organizations/' + resourceId(id), { token }) };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function tenantSupport(id: string): Promise<ApiResult<TenantSupport>> {
  try {
    const { token } = await consoleSession('platform.organizations.read');
    const base = '/platform/organizations/' + resourceId(id);
    const [subscription, administrators] = await Promise.all([
      apiRequest<TenantSupport['subscription']>(base + '/subscription', { token }),
      apiRequest<TenantSupport['administrators']>(base + '/administrators', { token }),
    ]);
    return { value: { subscription, administrators } };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function saveTenant(draft: TenantDraft, id?: string, expectedVersion?: number): Promise<ApiResult<Tenant>> {
  try {
    const { token } = await consoleSession('platform.organizations.manage');
    const { subscription_plan_id, is_active, ...fields } = draft;
    const body = {
      name: fields.name.trim(), description: fields.description.trim() || null,
      contact_name: fields.contact_name.trim() || null, contact_email: fields.contact_email.trim() || null,
      contact_phone: fields.contact_phone.trim() || null,
      ...(id ? { is_active, expected_version: expectedVersion } : { subscription_plan_id }),
    };
    const value = await apiRequest<Tenant>('/platform/organizations' + (id ? '/' + resourceId(id) : ''), { method: id ? 'PATCH' : 'POST', body, token });
    revalidatePath('/home');
    return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function tenantLifecycle(id: string, version: number, restore = false): Promise<ApiResult<Tenant>> {
  try {
    const { token } = await consoleSession('platform.organizations.manage');
    const value = await apiRequest<Tenant>('/platform/organizations/' + resourceId(id) + (restore ? '/restore' : '?' + queryString({ expected_version: version })), {
      token, method: restore ? 'POST' : 'DELETE', ...(restore ? { body: { expected_version: version } } : {}),
    });
    revalidatePath('/home');
    return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function findAdministrators(q: string): Promise<ApiResult<{ id: string; display_name: string; email: string }[]>> {
  try {
    const { token } = await consoleSession('platform.users.read');
    const result = await apiRequest<{ items: { id: string; display_name: string; email: string; email_verified: boolean; setup_pending: boolean }[] }>('/platform/users?' + queryString({ q, is_active: true, archived: false, limit: 25 }), { token });
    return { value: result.items.filter(row => row.email_verified && !row.setup_pending) };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function activeTenantOptions(): Promise<{ id: string; name: string }[]> {
  const { token } = await consoleSession('platform.organizations.read');
  return allOptions<{ id: string; name: string }>('/platform/organizations?archived=false&is_active=true', token);
}
export type ProvisionDeviceChoice =
  | { kind: 'new'; name: string; device_unique_id: string; device_type: 'manikin' | 'laptop' }
  | { kind: 'existing'; device_id: string; expected_etag: string };
export type ProvisionAdminChoice =
  | { kind: 'new'; display_name: string; email: string; password: string }
  | { kind: 'existing'; user_id: string };
export async function provisionTenant(
  draft: TenantDraft, device: ProvisionDeviceChoice, administrator: ProvisionAdminChoice,
): Promise<ApiResult<{ tenant: Tenant; device: { id: string }; administrator: { id: string } }>> {
  try {
    const { token } = await consoleSession('platform.organizations.manage');
    const tenant = {
      name: draft.name.trim(), subscription_plan_id: resourceId(draft.subscription_plan_id),
      description: draft.description.trim() || null,
      contact_name: draft.contact_name.trim() || null,
      contact_email: draft.contact_email.trim() || null,
      contact_phone: draft.contact_phone.trim() || null,
    };
    const body = {
      tenant,
      device: device.kind === 'new'
        ? { kind: 'new', name: device.name.trim(), device_unique_id: device.device_unique_id.trim(), device_type: device.device_type }
        : { kind: 'existing', device_id: resourceId(device.device_id), expected_etag: device.expected_etag },
      administrator: administrator.kind === 'new'
        ? { kind: 'new', display_name: administrator.display_name.trim(), email: administrator.email.trim(), password: administrator.password }
        : { kind: 'existing', user_id: resourceId(administrator.user_id) },
    };
    const value = await apiRequest<{ tenant: Tenant; device: { id: string }; administrator: { id: string } }>(
      '/platform/organizations/provision', { token, method: 'POST', body },
    );
    revalidatePath('/tenants'); revalidatePath('/devices'); revalidatePath('/home');
    return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function assignTenantAdministrator(id: string, userId: string): Promise<ApiResult<true>> {
  try {
    const { token } = await consoleSession('platform.organization_admins.manage');
    await apiRequest('/platform/organizations/' + resourceId(id) + '/administrators', { token, method: 'POST', body: { user_id: resourceId(userId) } });
    revalidatePath('/home');
    return { value: true };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function assignTenantPlan(id: string, planId: string, version: number): Promise<ApiResult<Tenant>> {
  try {
    const { token } = await consoleSession('platform.organizations.manage');
    const base = '/platform/organizations/' + resourceId(id);
    await apiRequest(base + '/subscription', { token, method: 'PUT', body: { subscription_plan_id: resourceId(planId), expected_version: version } });
    revalidatePath('/home');
    return { value: await apiRequest<Tenant>(base, { token }) };
  } catch (error) { return { error: consoleError(error) }; }
}
