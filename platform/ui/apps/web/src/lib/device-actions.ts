'use server';
import { revalidatePath } from 'next/cache';
import { ApiError, apiRequest } from './api';
import { currentUser, sessionToken } from './session';
import { allOptions, queryString, resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult, DirectoryPage } from './directory-api';
import type { Device, DeviceQuery } from './device-directory';
import type { DeviceDraft } from './device-editor';

type DeviceResponse = Omit<Device, 'description' | 'location' | 'contact_name' | 'contact_email' | 'contact_phone'> & {
  details?: Record<string, string | null>; location?: string | null;
  contact_name?: string | null; contact_email?: string | null; contact_phone?: string | null;
};
function device(row: DeviceResponse): Device {
  return { ...row, description: row.details?.notes ?? null, location: row.location ?? null,
    contact_name: row.contact_name ?? null, contact_email: row.contact_email ?? null, contact_phone: row.contact_phone ?? null };
}
async function access(contextId: string, manage = false, tenantOnly = false) {
  const user = await currentUser();
  if (!user) throw new ApiError(401, 'authentication_required');
  const platform = user.contextId === 'platform';
  const permission = manage ? (platform ? 'platform.organizations.manage' : 'org.devices.manage') : platform ? 'platform.health.read' : 'org.devices.summary.read';
  if (!user.permissions.includes(permission) || tenantOnly && platform) throw new ApiError(403, 'permission_denied');
  if (user.contextId !== contextId) throw new ApiError(409, 'context_changed');
  return { user, platform, base: platform ? '/platform/devices' : '/organizations/' + resourceId(contextId) + '/devices', token: await sessionToken() };
}
function etag(value?: string) {
  if (!value || !/^[0-9a-f]{64}$/.test(value)) throw new ApiError(422, 'device_version_required');
  return value;
}
function changed() { revalidatePath('/home'); revalidatePath('/devices'); }
export async function deviceOptions(contextId: string) {
  const { user, token, platform } = await access(contextId);
  const org = platform ? '' : '/organizations/' + resourceId(contextId);
  const [departments, tenants, languages] = await Promise.all([
    !platform && user.permissions.includes('org.departments.manage') ? allOptions<{ id: string; name: string }>(org + '/departments?is_active=true&archived=false', token) : [],
    platform && user.permissions.includes('platform.organizations.read') ? allOptions<{ id: string; name: string; is_active: boolean }>('/platform/organizations?archived=false', token) : [],
    apiRequest<{ items: { code: string; name: string }[] }>('/languages', { token }),
  ]);
  const names = (rows: { id: string; name: string }[]) => Object.fromEntries(rows.map(row => [row.id, row.name]));
  const targets = platform ? tenants.filter(row => row.is_active) : [];
  return { departments: names(departments), tenants: names(tenants), associationTargets: names(targets),
    languages: Object.fromEntries(languages.items.map(row => [row.code, row.name])), platform, scopeName: platform ? 'Platform fleet' : user.tenant?.name ?? 'Tenant', contextId };
}
export async function listDevices(contextId: string, query: DeviceQuery, cursor?: string): Promise<ApiResult<DirectoryPage<Device>>> {
  try {
    const { token, base } = await access(contextId);
    const result = await apiRequest<DirectoryPage<DeviceResponse>>(base + '?' + queryString({ ...query, cursor, include_total: true }), { token });
    return { value: { ...result, items: result.items.map(device) } };
  } catch (error) { return { error: consoleError(error) }; }
}

export async function readDevice(contextId: string, id: string): Promise<ApiResult<Device>> {
  try {
    const { token, base } = await access(contextId);
    return { value: device(await apiRequest<DeviceResponse>(base + '/' + resourceId(id), { token })) };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function saveDevice(contextId: string, draft: DeviceDraft, id?: string, expectedEtag?: string): Promise<ApiResult<Device>> {
  try {
    const { token, base, platform } = await access(contextId, true);
    if (!platform && !id) throw new ApiError(403, 'permission_denied');
    const version = id ? etag(expectedEtag) : undefined;
    const body = platform ? { name: draft.name.trim(), is_active: draft.is_active,
      ...(id ? { expected_etag: version } : { device_unique_id: draft.device_unique_id.trim(), organization_id: resourceId(draft.organization_id), device_type: draft.device_type, preferred_language: draft.preferred_language || null }),
    } : {
      name: draft.name.trim(), location: draft.location.trim() || null, details: { notes: draft.description.trim() || null },
      department_id: draft.department_id || null,
      contact_name: draft.contact_name.trim() || null, contact_email: draft.contact_email.trim() || null,
      contact_phone: draft.contact_phone.trim() || null, preferred_language: draft.preferred_language || null, is_active: draft.is_active,
      ...(id ? { expected_etag: version } : { device_type: draft.device_type }),
    };
    const value = device(await apiRequest<DeviceResponse>(base + (id ? '/' + resourceId(id) : ''), { token, method: id ? 'PATCH' : 'POST', body }));
    changed(); return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function changeDeviceLifecycle(contextId: string, id: string, action: 'retire' | 'revoke' | 'activate' | 'deactivate', expectedEtag?: string): Promise<ApiResult<Device>> {
  try {
    const { token, base } = await access(contextId, true);
    const version = etag(expectedEtag);
    if (!['retire', 'revoke', 'activate', 'deactivate'].includes(action)) throw new ApiError(422, 'invalid_request');
    const path = base + '/' + resourceId(id);
    const status = action === 'activate' || action === 'deactivate';
    const value = device(await apiRequest<DeviceResponse>(path + (status ? '' : action === 'retire' ? '?' + queryString({ expected_etag: version }) : '/revoke?' + queryString({ expected_etag: version })), {
      token, method: status ? 'PATCH' : action === 'retire' ? 'DELETE' : 'POST',
      ...(status ? { body: { expected_etag: version, is_active: action === 'activate' } } : {}),
    }));
    changed(); return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function transferDevice(contextId: string, id: string, targetId: string, name: string, active: boolean, expectedEtag?: string): Promise<ApiResult<{ source: Device; device: Device }>> {
  try {
    const { token, base } = await access(contextId, true);
    if (contextId !== 'platform') throw new ApiError(403, 'permission_denied');
    const value = await apiRequest<{ source: DeviceResponse; device: DeviceResponse }>(base + '/' + resourceId(id) + '/transfer', {
      token, method: 'POST', body: { expected_etag: etag(expectedEtag), organization_id: resourceId(targetId), name: name.trim(), is_active: active },
    });
    changed(); return { value: { source: device(value.source), device: device(value.device) } };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function issueEnrollment(contextId: string, id: string, expectedEtag?: string): Promise<ApiResult<{ enrollment_token: string; expires_at: string }>> {
  try {
    const { token, base } = await access(contextId, true, true);
    const value = await apiRequest<{ enrollment_token: string; expires_at: string }>(base + '/' + resourceId(id) + '/enrollment?' + queryString({ expected_etag: etag(expectedEtag) }), { token, method: 'POST' });
    changed(); return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function readDeviceConfiguration(contextId: string, id: string): Promise<ApiResult<{ language: string; operational: boolean; applied: boolean; modelsAssigned: boolean }>> {
  try {
    const { user, token, base, platform } = await access(contextId);
    if (!user.permissions.includes('org.configuration.read') || platform) throw new ApiError(403, 'permission_denied');
    const path = base + '/' + resourceId(id);
    const [configuration, row] = await Promise.all([
      apiRequest<{ effective_language: string; is_active: boolean; configuration_hash: string; settings: Record<string, { enabled?: boolean }> }>(path + '/configuration', { token }),
      apiRequest<{ applied_configuration_hash: string | null }>(path, { token }),
    ]);
    return { value: { language: configuration.effective_language, operational: configuration.is_active, applied: configuration.configuration_hash === row.applied_configuration_hash, modelsAssigned: ['conversation', 'audio_input', 'audio_output', 'video'].some(section => configuration.settings[section]?.enabled === true) } };
  } catch (error) { return { error: consoleError(error) }; }
}
