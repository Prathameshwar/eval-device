import { beforeEach, expect, it, vi } from 'vitest';

const { request, user, token } = vi.hoisted(() => ({
  request: vi.fn(), user: vi.fn(), token: vi.fn(),
}));
vi.mock('server-only', () => ({}));
vi.mock('@/lib/session', () => ({ currentUser: user, sessionToken: token }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('../src/lib/api')>('../src/lib/api');
  return { ...actual, apiRequest: request };
});
import { listScenarios } from '../src/lib/scenario-actions';

const org = '00000000-0000-0000-0000-000000000001';
beforeEach(() => {
  vi.resetAllMocks();
  user.mockResolvedValue({
    contextId: org, permissions: ['org.status.read', 'org.clinical.author'],
  });
  token.mockResolvedValue('server-only-test-token');
  request.mockResolvedValue({ items: [], next_cursor: null });
});

it.each([
  ['published', 'approved'],
  ['retired', 'retired'],
])('filters %s versions at the API while preserving search and pagination', async (view, status) => {
  const items = [{ id: 'scenario-a', is_active: view === 'published' }];
  request.mockResolvedValue({ items, next_cursor: 'next-page' });
  const result = await listScenarios(org, { q: 'Chest pain', limit: 25, view }, 'current-page');
  expect(request).toHaveBeenCalledOnce();
  const [path, options] = request.mock.calls[0]!;
  const url = new URL(path, 'https://example.test');
  expect(url.pathname).toBe('/organizations/' + org + '/training/scenarios');
  expect(Object.fromEntries(url.searchParams)).toEqual({
    q: 'Chest pain', limit: '25', cursor: 'current-page', schema_version: 'all', status,
  });
  expect(options).toEqual({ token: 'server-only-test-token' });
  expect(result.value).toEqual({ items, total: 1, next_cursor: 'next-page', has_more: true });
});

it.each(['drafts', 'archived'])('keeps %s on the draft endpoint', async (view) => {
  await listScenarios(org, { q: '', limit: 25, view });
  expect(request).toHaveBeenCalledOnce();
  const url = new URL(request.mock.calls[0]![0], 'https://example.test');
  expect(url.pathname).toBe('/organizations/' + org + '/training/scenario-drafts');
  expect(url.searchParams.get('archived')).toBe(String(view === 'archived'));
  expect(url.searchParams.has('status')).toBe(false);
});

it.each(['published', 'retired'])('keeps %s versions restricted to clinical authors and reviewers', async (view) => {
  user.mockResolvedValue({ contextId: org, permissions: ['org.status.read'] });
  expect((await listScenarios(org, { q: '', limit: 25, view })).error).toMatch(/permission/);
  expect(request).not.toHaveBeenCalled();
});
