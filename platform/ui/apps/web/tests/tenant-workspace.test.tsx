import type { ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { TenantDirectoryProvider, useTenantDirectory } from '../src/components/TenantDirectoryProvider';
import { listTenants, saveTenant, tenantLifecycle } from '../src/lib/tenant-actions';
import { tenantDraft } from '../src/lib/tenant-editor';
import { DEMO_TENANTS, TENANT_PLANS } from '../src/data/tenants';
vi.mock('../src/lib/tenant-actions', () => ({ listTenants: vi.fn(), saveTenant: vi.fn(), tenantLifecycle: vi.fn() }));
const original = DEMO_TENANTS[0]!;
beforeEach(() => {
  vi.mocked(listTenants).mockResolvedValue({ value: { items: [original], total: 1, next_cursor: null, has_more: false } });
  vi.mocked(saveTenant).mockReset(); vi.mocked(tenantLifecycle).mockReset();
});
function workspace() {
  return renderHook(useTenantDirectory, { wrapper: ({ children }: { children: ReactNode }) =>
    <TenantDirectoryProvider initialRows={[original]} plans={TENANT_PLANS}>{children}</TenantDirectoryProvider> });
}
it('keeps the record unchanged when the API rejects a stale edit', async () => {
  const { result } = workspace();
  vi.mocked(saveTenant).mockResolvedValue({ error: 'This record changed. Refresh.' });
  await act(async () => {
    expect((await result.current.save({ ...tenantDraft(original), name: 'Stale' }, original)).error).toContain('changed');
  });
  expect(saveTenant).toHaveBeenCalledWith(expect.objectContaining({ name: 'Stale' }), original.id, original.management_version);
  expect(result.current.rows[0]).toEqual(original);
});
it('uses server-returned identities and versions after persistence succeeds', async () => {
  const { result } = workspace();
  const persisted = { ...original, id: 'server-id', name: 'Persisted', management_version: 3 };
  vi.mocked(saveTenant).mockResolvedValue({ value: persisted });
  await act(async () => { await result.current.save({ ...tenantDraft(null), name: 'Persisted', subscription_plan_id: original.subscription_plan_id }, null); });
  expect(result.current.rows[0]).toEqual(persisted);
  expect(result.current.savedTenant?.id).toBe('server-id');
  await waitFor(() => expect(result.current.loading).toBe(false));
});
it('preserves the record and exposes failed archive requests', async () => {
  const { result } = workspace();
  vi.mocked(tenantLifecycle).mockResolvedValue({ error: 'Permission denied' });
  await act(async () => { expect(await result.current.archive(original)).toBe('Permission denied'); });
  expect(result.current.rows[0]?.archived_at).toBeNull();
});
