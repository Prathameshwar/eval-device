'use server';
import { ApiError, apiRequest } from './api';
import { consoleSession, resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult } from './directory-api';
export type ArchiveItem = { id: string; kind: string; byte_size: number; sequence: number; available: boolean };
export type Archive = { id: string; learner_name: string; scenario_title: string; created_at: string; sync_status: string;
  transfer_status?: string; capture_status?: string; upload_until?: string; media_expires_at?: string;
  outcome?: string | null;
  expected_items: number | null; received_items: number; items: ArchiveItem[]; assigned_session_id: string | null };
export type ArchiveTurn = { turn_key: string; input_text: string; response_text: string | null; occurred_at: string; outcome: string };
async function request<T>(context: string, suffix: string): Promise<ApiResult<T>> {
  try {
    const session = await consoleSession('org.results.read');
    if (session.user.contextId !== context) throw new ApiError(409, 'context_changed');
    return { value: await apiRequest<T>('/organizations/' + resourceId(context) + '/session-archives' + suffix, { token: session.token }) };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function listArchives(context: string, cursor?: string) {
  return request<{items: Archive[]; next_cursor: string | null}>(context, '?limit=25' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''));
}
export async function readArchive(context: string, id: string) {
  return request<Archive>(context, '/' + resourceId(id));
}
export async function archiveTurns(context: string, id: string, offset = 0) {
  return request<{items: ArchiveTurn[]; next_offset: number | null}>(context, '/' + resourceId(id) + '/turns?offset=' + encodeURIComponent(offset));
}
