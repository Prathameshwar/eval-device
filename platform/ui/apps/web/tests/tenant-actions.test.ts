import { beforeEach, expect, it, vi } from 'vitest';
import { apiRequest } from '../src/lib/api';
import { currentUser, sessionToken } from '../src/lib/session';
import { saveTenant, tenantLifecycle, listTenants } from '../src/lib/tenant-actions';
import { DEFAULT_TENANT_QUERY } from '../src/lib/tenant-directory';
import { tenantDraft } from '../src/lib/tenant-editor';
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }));
vi.mock('../src/lib/session', () => ({ currentUser: vi.fn(), sessionToken: vi.fn() }));
vi.mock('../src/lib/api', async importOriginal => {
  const original = await importOriginal<typeof import('../src/lib/api')>();
  return { ...original, apiRequest: vi.fn() };
});
const id = '12345678-1234-4234-8234-123456789012';
beforeEach(() => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'User', email: 'user@example.com', contextId: 'platform', role: 'platform_admin', permissions: ['platform.organizations.read', 'platform.organizations.manage'] });
  vi.mocked(sessionToken).mockResolvedValue('web_server-only');
  vi.mocked(apiRequest).mockReset();
});
it('checks current permissions before any write', async () => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'User', email: 'user@example.com', contextId: id, role: 'org_admin', permissions: ['org.settings.manage'] });
  expect((await saveTenant({ ...tenantDraft(null), name: 'Blocked' })).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('creates inactive tenants with no client-supplied identity or version', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ id });
  const result = await saveTenant({ ...tenantDraft(null), name: ' New tenant ', subscription_plan_id: id, is_active: true });
  expect(result.value?.id).toBe(id);
  expect(apiRequest).toHaveBeenCalledWith('/platform/organizations', expect.objectContaining({ method: 'POST', token: 'web_server-only', body: expect.objectContaining({ name: 'New tenant', subscription_plan_id: id }) }));
  expect(vi.mocked(apiRequest).mock.calls[0]?.[1]?.body).not.toHaveProperty('is_active');
});
it('carries record versions to edit and archive endpoints', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ id });
  await saveTenant(tenantDraft(null), id, 8);
  expect(apiRequest).toHaveBeenLastCalledWith('/platform/organizations/' + id, expect.objectContaining({ body: expect.objectContaining({ expected_version: 8 }) }));
  await tenantLifecycle(id, 8);
  expect(apiRequest).toHaveBeenLastCalledWith('/platform/organizations/' + id + '?expected_version=8', expect.objectContaining({ method: 'DELETE' }));
});
it('encodes directory searches and preserves signed cursor parameters', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ items: [], total: 0, has_more: false, next_cursor: null });
  await listTenants({ ...DEFAULT_TENANT_QUERY, q: 'A&B' }, 'signed+cursor');
  const url = new URL(String(vi.mocked(apiRequest).mock.calls[0]?.[0]), 'http://test');
  expect(url.searchParams.get('q')).toBe('A&B');
  expect(url.searchParams.get('cursor')).toBe('signed+cursor');
  expect(url.searchParams.get('include_total')).toBe('true');
});
it('rejects malformed resource IDs before making an API request', async () => {
  expect((await tenantLifecycle('../../users', 1)).error).toBeTruthy();
  expect(apiRequest).not.toHaveBeenCalled();
});
