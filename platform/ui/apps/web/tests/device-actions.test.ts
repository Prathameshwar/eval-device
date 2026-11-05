import { beforeEach, expect, it, vi } from 'vitest';
import { apiRequest } from '../src/lib/api';
import { currentUser, sessionToken } from '../src/lib/session';
import { saveDevice, issueEnrollment, readDeviceConfiguration, readDevice, listDevices, changeDeviceLifecycle, transferDevice } from '../src/lib/device-actions';
import { DEFAULT_DEVICE_QUERY } from '../src/lib/device-directory';
import { deviceDraft } from '../src/lib/device-editor';
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }));
vi.mock('../src/lib/session', () => ({ currentUser: vi.fn(), sessionToken: vi.fn() }));
vi.mock('../src/lib/api', async importOriginal => ({ ...await importOriginal<typeof import('../src/lib/api')>(), apiRequest: vi.fn() }));
const id = '12345678-1234-4234-8234-123456789012';
beforeEach(() => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'User', email: 'u@example.com', role: 'org_admin', contextId: id, permissions: ['org.devices.manage', 'org.devices.summary.read'] });
  vi.mocked(sessionToken).mockResolvedValue('web_private'); vi.mocked(apiRequest).mockReset();
});
it('denies tenant device creation and keeps private edits inside the verified context', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ id, name: 'Device' });
  expect((await saveDevice(id, { ...deviceDraft(null), name: 'Blocked' })).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
  await saveDevice(id, { ...deviceDraft(null), name: 'Device', enrollment_state: 'enrolled', description: 'Notes' }, id, 'a'.repeat(64));
  expect(apiRequest).toHaveBeenCalledWith('/organizations/' + id + '/devices/' + id, expect.objectContaining({ method: 'PATCH', token: 'web_private', body: expect.objectContaining({ details: { notes: 'Notes' } }) }));
  expect(vi.mocked(apiRequest).mock.calls[0]?.[1]?.body).not.toHaveProperty('enrollment_state');
  expect(vi.mocked(apiRequest).mock.calls[0]?.[1]?.body).not.toHaveProperty('device_unique_id');
  expect(vi.mocked(apiRequest).mock.calls[0]?.[1]?.body).not.toHaveProperty('profile_id');
});
it('blocks platform device writes even when the account manages tenants', async () => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'User', email: 'u@example.com', role: 'platform_admin', contextId: 'platform', permissions: ['platform.organizations.manage', 'platform.health.read'] });
  expect((await issueEnrollment('platform', id)).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
  vi.mocked(apiRequest).mockResolvedValue({ id, summary_only: true });
  await readDevice('platform', id);
  expect(apiRequest).toHaveBeenCalledWith('/platform/devices/' + id, expect.anything());
});
it('forwards the stable etag for edits and enrollment', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ id });
  await saveDevice(id, deviceDraft(null), id, 'a'.repeat(64));
  expect(apiRequest).toHaveBeenLastCalledWith(expect.anything(), expect.objectContaining({ body: expect.objectContaining({ expected_etag: 'a'.repeat(64) }) }));
  await issueEnrollment(id, id, 'b'.repeat(64));
  expect(apiRequest).toHaveBeenLastCalledWith(expect.stringContaining('expected_etag=' + 'b'.repeat(64)), expect.anything());
});
it('loads server-paginated records without exposing server credentials', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ items: [{ id, details: { notes: 'Saved note' } }], total: 1, next_cursor: null, has_more: false });
  const result = await listDevices(id, DEFAULT_DEVICE_QUERY, 'cursor');
  expect(result.value?.items[0]?.description).toBe('Saved note');
  expect(JSON.stringify(result)).not.toContain('web_private');
});

it('rejects an old tenant tab and missing mutation versions before reaching the API', async () => {
  expect((await saveDevice('different', deviceDraft(null))).error).toMatch(/tenant changed/);
  expect((await issueEnrollment('different', id, 'a'.repeat(64))).error).toMatch(/tenant changed/);
  expect((await issueEnrollment(id, id)).error).toMatch(/Refresh/);
  expect(apiRequest).not.toHaveBeenCalled();
});

it('returns the one-time enrollment token to a tenant admin without requiring platform permissions', async () => {
  const result = { enrollment_token: 'enr_fixture_only_for_tests', expires_at: '2099-01-01T00:00:00Z' };
  vi.mocked(apiRequest).mockResolvedValue(result);
  expect(await issueEnrollment(id, id, 'a'.repeat(64))).toEqual({ value: result });
  expect(apiRequest).toHaveBeenCalledWith('/organizations/' + id + '/devices/' + id + '/enrollment?expected_etag=' + 'a'.repeat(64), { token: 'web_private', method: 'POST' });
});

it('blocks enrollment issuance for a tenant user without device management permission', async () => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'User', email: 'u@example.com', role: 'org_user', contextId: id, permissions: ['org.devices.summary.read'] });
  expect((await issueEnrollment(id, id, 'a'.repeat(64))).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('allows limited platform registration and activation, without forwarding tenant-private fields', async () => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'Admin', email: 'u@example.com', role: 'platform_admin', contextId: 'platform', permissions: ['platform.organizations.manage', 'platform.health.read'] });
  vi.mocked(apiRequest).mockResolvedValue({ id, summary_only: true });
  await saveDevice('platform', { ...deviceDraft(null), device_unique_id: ' SIM-01 ', organization_id: id, name: 'Fleet device', description: 'Private', contact_name: 'Private' });
  expect(apiRequest).toHaveBeenLastCalledWith('/platform/devices', expect.objectContaining({ body: { device_unique_id: 'SIM-01', organization_id: id, name: 'Fleet device', device_type: 'laptop', preferred_language: null, is_active: true } }));
  await saveDevice('platform', { ...deviceDraft(null), name: 'Renamed', device_unique_id: 'attempted-change' }, id, 'a'.repeat(64));
  expect(vi.mocked(apiRequest).mock.lastCall?.[1]?.body).not.toHaveProperty('device_unique_id');
  await changeDeviceLifecycle('platform', id, 'deactivate', 'a'.repeat(64));
  expect(apiRequest).toHaveBeenLastCalledWith('/platform/devices/' + id, expect.objectContaining({ method: 'PATCH', body: { expected_etag: 'a'.repeat(64), is_active: false } }));
});
it('uses DELETE-as-retirement and enforces platform-only tenant transfers', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ id });
  await changeDeviceLifecycle(id, id, 'retire', 'a'.repeat(64));
  expect(apiRequest).toHaveBeenCalledWith(expect.stringContaining('expected_etag='), expect.objectContaining({ method: 'DELETE' }));
  vi.mocked(apiRequest).mockClear();
  expect((await transferDevice(id, id, id, 'Destination', false, 'a'.repeat(64))).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
});

it.each([false, true])('reports models assigned only when an operation is enabled (%s)', async enabled => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'User', email: 'u@example.com', role: 'org_admin', contextId: id, permissions: ['org.devices.summary.read', 'org.configuration.read'] });
  vi.mocked(apiRequest).mockResolvedValueOnce({ effective_language: 'en', is_active: true, configuration_hash: 'hash', settings: { conversation: { enabled }, audio_input: { enabled: false } } })
    .mockResolvedValueOnce({ applied_configuration_hash: 'hash' });
  const result = await readDeviceConfiguration(id, id);
  expect(result.value).toMatchObject({ modelsAssigned: enabled, applied: true });
});
