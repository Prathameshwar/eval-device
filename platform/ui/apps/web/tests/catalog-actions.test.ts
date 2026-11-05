import { beforeEach, expect, it, vi } from 'vitest';
const { request, user, token } = vi.hoisted(() => ({
  request: vi.fn(),
  user: vi.fn(),
  token: vi.fn(),
}));
vi.mock('server-only', () => ({}));
vi.mock('@/lib/session', () => ({ currentUser: user, sessionToken: token }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('../src/lib/api')>('../src/lib/api');
  return { ...actual, apiRequest: request };
});
import { saveCatalog, setCatalogActive, listCatalog } from '../src/lib/catalog-actions';
import { savePlatformOptions } from '../src/lib/platform-options-actions';
import { createScenario } from '../src/lib/scenario-actions';
import { ApiError } from '../src/lib/api';
import { newCatalogRecord } from '../src/lib/patient-catalog';
const org = '00000000-0000-0000-0000-000000000001',
  id = '00000000-0000-0000-0000-000000000002';
beforeEach(() => {
  vi.resetAllMocks();
  user.mockResolvedValue({
    contextId: org,
    permissions: ['org.status.read', 'org.clinical.author', 'org.processing.execute'],
  });
  token.mockResolvedValue('server-only-test-token');
});
it('sends only editable fields and the stored version for catalog edits', async () => {
  const row = {
    ...newCatalogRecord('categories'),
    id,
    version: 4,
    code: 'category',
    name: ' Category ',
    names: { en: 'Category' },
    description: 'Description',
  };
  request.mockResolvedValue({ ...row, version: 5 });
  expect((await saveCatalog('categories', row)).value?.version).toBe(5);
  expect(request).toHaveBeenCalledWith('/organizations/' + org + '/clinical-catalog/specialties/' + id, {
    token: 'server-only-test-token',
    method: 'PATCH',
    body: {
      expected_version: 4,
      data: {
        code: 'category',
        name: 'Category',
        names: { en: 'Category' },
        description: 'Description',
        sort_order: 0,
        is_active: true,
      },
    },
  });
});
it('blocks platform context catalog requests before the API call', async () => {
  user.mockResolvedValue({
    contextId: 'platform',
    permissions: ['platform.settings.read', 'platform.settings.manage'],
  });
  expect((await listCatalog('patients', { q: '', state: 'all', limit: 25 })).error).toMatch(/permission/);
  expect(request).not.toHaveBeenCalled();
});
it('guards activation with the observed version', async () => {
  request.mockResolvedValue({ id });
  await setCatalogActive('patients', id, 3, true);
  expect(request).toHaveBeenCalledWith(
    '/organizations/' + org + '/clinical-catalog/patients/' + id + '/restore',
    expect.objectContaining({ body: { expected_version: 3 } }),
  );
});
it('returns case validation paths without discarded input values', async () => {
  request.mockRejectedValue(
    new ApiError(422, 'case_incomplete', [
      {
        path: ['dialogue', 'greeting'],
        message: 'Required',
        input: 'never include this',
      },
    ]),
  );
  const r = await setCatalogActive('cases', id, 1, true);
  expect(r.error).toContain('dialogue.greeting: Required');
  expect(r.error).not.toContain('never include');
});
it('explains catalog parent lifecycle conflicts from the API', async () => {
  request.mockRejectedValueOnce(new ApiError(409, 'catalog_in_use'));
  expect((await setCatalogActive('patients', id, 1, false)).error).toMatch(/Deactivate active cases/);
  request.mockRejectedValueOnce(new ApiError(409, 'catalog_parent_inactive'));
  expect((await setCatalogActive('cases', id, 1, true)).error).toMatch(/Activate the clinical specialty/);
});
it('rejects a changed selected tenant for practice and authoring', async () => {
  user.mockResolvedValue({
    contextId: id,
    permissions: ['org.clinical.author', 'org.processing.execute'],
  });
  const r = await createScenario(org, 'draft', id);
  expect(r.error).toMatch(/tenant changed/);
  expect(request).not.toHaveBeenCalled();
});
it('uses the actual platform configuration version', async () => {
  user.mockResolvedValue({ contextId: 'platform',
    permissions: ['platform.settings.read', 'platform.settings.manage'] });
  request.mockResolvedValue({ configuration_version: 10 });
  await savePlatformOptions({
    configuration_version: 9,
    display_name: 'Evaluator',
    registration_mode: 'invite_only',
    languages: [{ code: 'en', name: 'English', speech_locale: 'en-IN', is_active: true }],
    enabled_providers: [],
    maintenance_mode: false,
  });
  expect(request).toHaveBeenCalledWith(
    '/platform/settings',
    expect.objectContaining({
      body: expect.objectContaining({ expected_version: 9 }),
    }),
  );
});
