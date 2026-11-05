'use server';

import { ApiError, apiRequest } from './api';
import { allOptions, consoleSession, resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult } from './directory-api';
import type { Archive } from './session-archive-actions';

export type Assignment = { learner_id: string; scenario_id: string; language: string; duration_seconds: number };
export type QueuedSession = Assignment & {
  id: string; device_id: string; learner_name: string; scenario_title: string; status: string;
  created_at: string; expires_at: string; started_at: string | null; ended_at: string | null;
};
export type SessionQueue = { revision: number; paused: boolean; connected: boolean; runtime_state: string;
  items: QueuedSession[]; history: QueuedSession[] };
export type SessionResult = { session: QueuedSession; messages: { role: string; content: string }[];
  history_available: boolean; provenance: string; archive_id?: string | null };
export type SessionHistoryEntry = { id: string; kind: 'assigned' | 'standalone'; session: QueuedSession | null; archive: Archive | null };

async function access(contextId: string, permission = 'org.training.instruct') {
  const session = await consoleSession(permission);
  if (session.user.contextId !== contextId) throw new ApiError(409, 'context_changed');
  return { token: session.token, base: '/organizations/' + resourceId(contextId) };
}
function errorMessage(error: unknown) {
  const messages: Record<string, string> = {
    queue_changed: 'The queue changed on another screen or device. Refresh the queue and reopen any edit panel before trying again.',
    queue_full: 'This device has reached its limit of 100 waiting sessions.',
    participant_unavailable: 'Choose an active trainee in the device department.',
    session_duration_limit: 'The duration exceeds this device’s limit. Choose a shorter session.',
    scenario_language_unavailable: 'This case is not available in the selected language.',
    model_selection_required: 'Assign the device’s practice models before planning sessions.',
    model_language_unavailable: 'This language is not enabled for practice.',
    device_busy: 'The device is already running a session. Finish it before beginning another.',
  };
  return error instanceof ApiError ? messages[error.code] ?? consoleError(error) : consoleError(error);
}
export async function readQueue(contextId: string, deviceId: string): Promise<ApiResult<SessionQueue>> {
  try {
    const { token, base } = await access(contextId);
    return { value: await apiRequest<SessionQueue>(base + '/devices/' + resourceId(deviceId) + '/session-queue', { token }) };
  } catch (error) { return { error: errorMessage(error) }; }
}
export async function queueLearners(contextId: string, deviceId: string): Promise<ApiResult<{ id: string; name: string }[]>> {
  try {
    const { token, base } = await access(contextId);
    return { value: await allOptions(base + '/session-queue/learners?device_id=' + resourceId(deviceId), token) };
  } catch (error) { return { error: errorMessage(error) }; }
}
export async function planSessions(contextId: string, deviceId: string, body: { request_key: string; items: Assignment[] }): Promise<ApiResult<SessionQueue>> {
  try {
    const { token, base } = await access(contextId);
    return { value: await apiRequest<SessionQueue>(base + '/devices/' + resourceId(deviceId) + '/session-queue', { token, method: 'POST', body }) };
  } catch (error) { return { error: errorMessage(error) }; }
}
export async function changeQueue(contextId: string, deviceId: string, body: { expected_revision: number; order: string[]; paused: boolean }): Promise<ApiResult<SessionQueue>> {
  try {
    const { token, base } = await access(contextId);
    return { value: await apiRequest<SessionQueue>(base + '/devices/' + resourceId(deviceId) + '/session-queue', { token, method: 'PUT', body }) };
  } catch (error) { return { error: errorMessage(error) }; }
}
export async function editQueuedSession(contextId: string, deviceId: string, id: string, body: Assignment & { expected_revision: number }): Promise<ApiResult<SessionQueue>> {
  try {
    const { token, base } = await access(contextId);
    return { value: await apiRequest<SessionQueue>(base + '/devices/' + resourceId(deviceId) + '/session-queue/' + resourceId(id), { token, method: 'PUT', body }) };
  } catch (error) { return { error: errorMessage(error) }; }
}
export async function endQueuedSession(contextId: string, deviceId: string, id: string): Promise<ApiResult<SessionQueue>> {
  try {
    const { token, base } = await access(contextId);
    return { value: await apiRequest<SessionQueue>(base + '/devices/' + resourceId(deviceId) + '/session-queue/' + resourceId(id) + '/end', { token, method: 'POST' }) };
  } catch (error) { return { error: errorMessage(error) }; }
}
export async function practiceSessionResult(contextId: string, id: string): Promise<ApiResult<SessionResult>> {
  try {
    const { token, base } = await access(contextId, 'org.results.read');
    return { value: await apiRequest<SessionResult>(base + '/practice-sessions/' + resourceId(id), { token }) };
  } catch (error) { return { error: errorMessage(error) }; }
}
export async function practiceSessionHistory(contextId: string, cursor?: string): Promise<ApiResult<{ items: QueuedSession[]; next_cursor: string | null }>> {
  try {
    const { token, base } = await access(contextId, 'org.results.read');
    return { value: await apiRequest<{ items: QueuedSession[]; next_cursor: string | null }>(base + '/practice-sessions?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), { token }) };
  } catch (error) { return { error: errorMessage(error) }; }
}
export async function sessionHistory(contextId: string, cursor?: string): Promise<ApiResult<{ items: SessionHistoryEntry[]; next_cursor: string | null }>> {
  try {
    const { token, base } = await access(contextId, 'org.results.read');
    return { value: await apiRequest<{ items: SessionHistoryEntry[]; next_cursor: string | null }>(base + '/session-history?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), { token }) };
  } catch (error) { return { error: errorMessage(error) }; }
}
