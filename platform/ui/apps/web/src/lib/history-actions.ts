'use server';
import { ApiError, apiRequest } from './api';
import { allOptions, consoleSession, resourceId, queryString } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult, DirectoryPage } from './directory-api';
import { canStartSession } from './session-start';
export type HistoryRow = {
  id: string;
  device_id: string;
  learner_id?: string;
  instructor_id?: string;
  scenario_id?: string;
  status: string;
  created_at: string;
  language?: string;
  operation?: string;
  duration_seconds?: number;
  media_available?: boolean;
  feedback_version?: number;
  result?: {
    turns?: number;
    recording_status?: string;
    audio_recordings?: string[];
    video_recordings?: string[];
    [key: string]: unknown;
  } | null;
  feedback?: { scores: Record<string, string>; comments: string } | null;
};
export type SessionOptions = {
  devices: { id: string; name: string }[];
  learners: { id: string; name: string }[];
  scenarios: { id: string; title: string; languages: string[] }[];
};
export type MediaItem = {
  index: number;
  role: string;
  format: string;
  content_type: string;
};
async function access(contextId: string, permission = 'org.results.read') {
  const s = await consoleSession(permission);
  if (s.user.contextId !== contextId) throw new ApiError(409, 'context_changed');
  return { ...s, base: '/organizations/' + resourceId(contextId) };
}
function message(e: unknown) {
  const messages: Record<string, string> = {
    training_not_configured:
      'The API training signing key is not configured. Ask the operator to enable training sessions.',
    scenario_runtime_unsupported: 'Choose a scenario supported by the device training runtime.',
    training_profile_required: 'Configure local conversation, Whisper speech recognition and eSpeak speech output models for this device.',
    training_agent_required: 'The device needs its training software connected before a session can start.',
    session_duration_limit: 'This duration exceeds the device limit. Choose a shorter session.',
    scenario_not_approved: 'This scenario is no longer available for training. Reload the session setup.',
    session_not_reviewable: 'Finish the session before adding feedback.',
    feedback_version_conflict: 'Feedback changed. Reload the session before saving.',
    media_expired: 'This recording has expired under the retention policy.',
    result_unavailable: 'This recording is not available yet.',
    participant_unavailable: 'Choose an active learner in the device department.',
    rubric_mismatch: 'Rate every item in the session rubric.',
  };
  return e instanceof ApiError ? (messages[e.code] ?? consoleError(e)) : consoleError(e);
}
export async function listHistory(
  contextId: string,
  q: { limit: number; mine: boolean; kind: 'sessions' | 'runs' },
  cursor?: string,
): Promise<ApiResult<DirectoryPage<HistoryRow>>> {
  try {
    const { base, token } = await access(contextId);
    const r = await apiRequest<{
      items: HistoryRow[];
      next_cursor?: string | null;
      total?: number;
      has_more?: boolean;
    }>(
      base +
        (q.kind === 'runs' ? '/runs' : '/training/sessions') +
        '?' +
        queryString({
          limit: q.limit,
          cursor,
          ...(q.kind === 'sessions' ? { mine: q.mine } : {}),
        }),
      { token },
    );
    return {
      value: {
        ...r,
        total: r.total ?? r.items.length,
        next_cursor: r.next_cursor ?? null,
        has_more: r.has_more ?? !!r.next_cursor,
      },
    };
  } catch (e) {
    return { error: message(e) };
  }
}
export async function readHistory(
  contextId: string,
  id: string,
  kind: 'sessions' | 'runs',
): Promise<ApiResult<HistoryRow>> {
  try {
    const { base, token } = await access(contextId);
    return {
      value: await apiRequest<HistoryRow>(
        base + (kind === 'runs' ? '/runs/' : '/training/sessions/') + resourceId(id),
        { token },
      ),
    };
  } catch (e) {
    return { error: message(e) };
  }
}
export async function stopHistory(
  contextId: string,
  id: string,
  kind: 'sessions' | 'runs',
): Promise<ApiResult<HistoryRow>> {
  try {
    const { base, token, user } = await access(contextId, 'org.processing.execute');
    if (kind === 'sessions' && !canStartSession(user.permissions)) throw new ApiError(403, 'permission_denied');
    return {
      value: await apiRequest<HistoryRow>(
        base +
          (kind === 'runs' ? '/runs/' : '/training/sessions/') +
          resourceId(id) +
          (kind === 'runs' ? '/cancel' : '/stop'),
        { token, method: 'POST' },
      ),
    };
  } catch (e) {
    return { error: message(e) };
  }
}
export async function historyOptions(contextId: string): Promise<ApiResult<SessionOptions>> {
  try {
    const { base, token, user } = await access(contextId, 'org.processing.execute');
    if (!canStartSession(user.permissions)) throw new ApiError(403, 'permission_denied');
    const [devices, scenarios, members] = await Promise.all([
      allOptions<{ id: string; name: string; enrollment_state: string }>(base + '/devices?is_active=true&archived=false', token),
      allOptions<{
        id: string;
        title: string;
        languages: string[];
        execution_supported: boolean;
        approved: boolean;
        is_active: boolean;
      }>(base + '/training/scenarios?schema_version=all', token),
      user.permissions.includes('org.members.manage')
        ? allOptions<{
            user: {
              id: string;
              display_name: string;
              is_active: boolean;
            } | null;
          }>(base + '/members?is_active=true&archived=false&invitation_status=accepted', token)
        : Promise.resolve([]),
    ]);
    return {
      value: {
        devices: devices.filter(d => d.enrollment_state === 'enrolled'),
        scenarios: scenarios.filter((s) => s.execution_supported && s.approved && s.is_active && s.languages.length),
        learners: members.length
          ? members
              .filter((m) => m.user?.is_active)
              .map((m) => ({ id: m.user!.id, name: m.user!.display_name }))
          : [{ id: user.id, name: user.name }],
      },
    };
  } catch (e) {
    return { error: message(e) };
  }
}
export async function createSession(
  contextId: string,
  body: {
    request_key: string;
    device_id: string;
    learner_id: string;
    scenario_id: string;
    language: string;
    duration_seconds: number;
  },
): Promise<ApiResult<HistoryRow>> {
  try {
    const { base, token, user } = await access(contextId, 'org.processing.execute');
    if (!canStartSession(user.permissions)) throw new ApiError(403, 'permission_denied');
    return {
      value: await apiRequest<HistoryRow>(base + '/training/sessions', {
        token,
        method: 'POST',
        body,
      }),
    };
  } catch (e) {
    return { error: message(e) };
  }
}
export async function sessionRubric(
  contextId: string,
  id: string,
): Promise<ApiResult<{ items: { id: string; description: string }[] }>> {
  try {
    const { base, token, user } = await access(contextId, 'org.processing.execute');
    if (!canStartSession(user.permissions)) throw new ApiError(403, 'permission_denied');
    return {
      value: await apiRequest<{ items: { id: string; description: string }[] }>(
        base + '/training/sessions/' + resourceId(id) + '/rubric',
        { token },
      ),
    };
  } catch (e) {
    return { error: message(e) };
  }
}
export async function saveFeedback(
  contextId: string,
  row: HistoryRow,
  scores: Record<string, string>,
  comments: string,
): Promise<ApiResult<HistoryRow>> {
  try {
    const { base, token, user } = await access(contextId, 'org.processing.execute');
    if (!canStartSession(user.permissions)) throw new ApiError(403, 'permission_denied');
    return {
      value: await apiRequest<HistoryRow>(base + '/training/sessions/' + resourceId(row.id) + '/feedback', {
        token,
        method: 'POST',
        body: {
          expected_version: row.feedback_version ?? 0,
          scores,
          comments,
        },
      }),
    };
  } catch (e) {
    return { error: message(e) };
  }
}
export async function historyStats(contextId: string): Promise<
  ApiResult<{
    sessions: number;
    hours_practiced: number;
    average_score: number | null;
    awaiting_review: number;
  }>
> {
  try {
    const { base, token } = await access(contextId);
    return {
      value: await apiRequest<{
        sessions: number;
        hours_practiced: number;
        average_score: number | null;
        awaiting_review: number;
      }>(base + '/training/stats', { token }),
    };
  } catch (e) {
    return { error: message(e) };
  }
}
export async function listMedia(contextId: string, id: string): Promise<ApiResult<MediaItem[]>> {
  try {
    const { base, token } = await access(contextId, 'org.media.read');
    const r = await apiRequest<{ items: MediaItem[] }>(base + '/runs/' + resourceId(id) + '/media', {
      token,
    });
    return { value: r.items };
  } catch (e) {
    return { error: message(e) };
  }
}
export async function openMedia(
  contextId: string,
  id: string,
  index: number,
): Promise<ApiResult<{ url: string; expires_in: number }>> {
  try {
    const { base, token } = await access(contextId, 'org.media.read');
    if (!Number.isInteger(index) || index < 0) throw new ApiError(422, 'invalid_request');
    return {
      value: await apiRequest<{ url: string; expires_in: number }>(
        base + '/runs/' + resourceId(id) + '/media/' + index + '/access?method=GET',
        { token, method: 'POST' },
      ),
    };
  } catch (e) {
    return { error: message(e) };
  }
}
