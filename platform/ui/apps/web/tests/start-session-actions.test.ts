import { beforeEach, expect, it, vi } from 'vitest';
const { currentUser, sessionToken, apiRequest } = vi.hoisted(() => ({ currentUser: vi.fn(), sessionToken: vi.fn(), apiRequest: vi.fn() }));
vi.mock('server-only', () => ({}));
vi.mock('../src/lib/session', () => ({ currentUser, sessionToken }));
vi.mock('../src/lib/api', async () => ({ ...await vi.importActual('../src/lib/api'), apiRequest }));
import { createSession, historyOptions, stopHistory, sessionRubric, saveFeedback } from '../src/lib/history-actions';
const org = '00000000-0000-4000-8000-000000000001';
const permissions = ['org.results.read', 'org.processing.execute', 'org.playback.execute', 'org.training.instruct'];
beforeEach(() => {
  vi.resetAllMocks();
  currentUser.mockResolvedValue({ id: 'instructor', name: 'Instructor', contextId: org, permissions });
  sessionToken.mockResolvedValue('test-only-token');
});
it('filters unenrolled devices and unsupported or inactive scenarios', async () => {
  apiRequest.mockImplementation(async (path: string) => ({ items: path.includes('/devices?') ? [
    { id: 'ready', name: 'Ready', enrollment_state: 'enrolled' },
    { id: 'pending', name: 'Pending', enrollment_state: 'pending' },
    { id: 'retired', name: 'Retired', enrollment_state: 'retired' },
  ] : [
    { id: 'available', execution_supported: true, approved: true, is_active: true, languages: ['en'] },
    { id: 'inactive', execution_supported: true, approved: true, is_active: false, languages: ['en'] },
    { id: 'untranslated', execution_supported: true, approved: true, is_active: true, languages: [] },
  ] }));
  const result = await historyOptions(org);
  expect(result.value?.devices.map(row => row.id)).toEqual(['ready']);
  expect(result.value?.scenarios.map(row => row.id)).toEqual(['available']);
  expect(result.value?.learners).toEqual([{ id: 'instructor', name: 'Instructor' }]);
});
it.each(['org.training.instruct', 'org.playback.execute'])('blocks a caller without %s before loading or creating', async missing => {
  currentUser.mockResolvedValue({ contextId: org, permissions: permissions.filter(p => p !== missing) });
  expect((await historyOptions(org)).error).toBeTruthy();
  expect((await createSession(org, { request_key: org, device_id: org, learner_id: org, scenario_id: org, language: 'en', duration_seconds: 300 })).error).toBeTruthy();
  expect((await stopHistory(org, org, 'sessions')).error).toBeTruthy();
  expect((await sessionRubric(org, org)).error).toBeTruthy();
  expect((await saveFeedback(org, { id: org, device_id: org, status: 'completed', created_at: '' }, {}, '')).error).toBeTruthy();
  expect(apiRequest).not.toHaveBeenCalled();
});
it('rejects a changed tenant context before submitting', async () => {
  const result = await createSession('00000000-0000-4000-8000-000000000002', {
    request_key: org, device_id: org, learner_id: org, scenario_id: org, language: 'en', duration_seconds: 300,
  });
  expect(result.error).toBeTruthy();
  expect(apiRequest).not.toHaveBeenCalled();
});
