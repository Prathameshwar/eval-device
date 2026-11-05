import { beforeEach, expect, it, vi } from 'vitest';
import { apiRequest } from '../src/lib/api';
import { currentUser, sessionToken } from '../src/lib/session';
import { deviceModels, testModel } from '../src/lib/direct-model-actions';
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }));
vi.mock('../src/lib/session', () => ({ currentUser: vi.fn(), sessionToken: vi.fn() }));
vi.mock('../src/lib/api', async original => ({ ...await original<typeof import('../src/lib/api')>(), apiRequest: vi.fn() }));
const deviceId = '22222222-2222-4222-8222-222222222222';
const org = '11111111-1111-4111-8111-111111111111';
beforeEach(() => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'User', email: 'test@example.com', role: 'platform_admin', contextId: 'platform', permissions: ['platform.organizations.manage'] });
  vi.mocked(sessionToken).mockResolvedValue('test-private-token');
  vi.mocked(apiRequest).mockReset();
});
it('loads the current device and all choices through one scoped request', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ device: { id: deviceId, organization_id: org }, selection: { version: 2 }, models: [] });
  expect((await deviceModels(deviceId)).value?.device.organization_id).toBe(org);
  expect(apiRequest).toHaveBeenCalledTimes(1);
  expect(apiRequest).toHaveBeenCalledWith('/platform/devices/' + deviceId + '/models', expect.anything());
});
it('denies non-platform or non-managing sessions before fetching model choices', async () => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'User', email: 'test@example.com', role: 'org_admin', contextId: org, permissions: ['platform.organizations.manage'] });
  expect((await deviceModels(deviceId)).error).toMatch(/permission/i);
  expect(apiRequest).not.toHaveBeenCalled();
});

it('tests only in the platform context and passes the reviewed model revision', async () => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'user', name: 'User', email: 'test@example.com', role: 'platform_admin', contextId: 'platform', permissions: ['platform.settings.manage'] });
  vi.mocked(apiRequest).mockResolvedValue({ status: 'passed', revision: 3, inference_verified: false });
  expect((await testModel(deviceId, 3)).value?.inference_verified).toBe(false);
  expect(apiRequest).toHaveBeenCalledWith(`/platform/runtime-models/${deviceId}/test`, expect.objectContaining({ method: 'POST', body: { expected_revision: 3 }, timeoutMs: 40000 }));
});
it('denies model tests before making requests without settings permission', async () => {
  expect((await testModel(deviceId, 3)).error).toMatch(/permission/i);
  expect(apiRequest).not.toHaveBeenCalled();
});
