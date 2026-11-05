'use server';
import { ApiError, apiRequest } from './api';
import { consoleSession, queryString, resourceId } from './console-api';
import { consoleError } from './console-errors';
import { inputIssues } from './input-errors';
import type { ApiResult, DirectoryPage } from './directory-api';
import { emptyDocument, type CaseDocument } from './patient-catalog';
export type ScenarioRow = {
  id: string;
  code: string;
  title: string;
  revision: number;
  version?: number;
  schema_version: number;
  is_archived?: boolean;
  is_active?: boolean;
  execution_supported?: boolean;
  document?: CaseDocument;
  source_case_id?: string | null;
  source_scenario_id?: string | null;
  source_case_revision?: number | null;
  approved_by?: string | null;
  approved_at?: string | null;
  publication_source?: 'tenant_review' | 'system_starter';
  starter_case_id?: string | null;
  specialty_id?: string | null;
  workflow_version?: number;
  submitted_revision?: number | null;
  submitted_at?: string | null;
};
export type ScenarioValidation = {
  revision: number;
  publishable: boolean;
  errors: { path: (string | number)[]; message: string }[];
  warnings: { path: (string | number)[]; message: string }[];
};
export type EducatorApproval = { educator_name: string; statement: string };
async function access(contextId: string, mode: 'read' | 'author' | 'review' = 'author') {
  const s = await consoleSession(mode === 'read' ? 'org.status.read' :
    mode === 'review' ? 'org.clinical.review' : 'org.clinical.author');
  if (s.user.contextId !== contextId) throw new ApiError(409, 'context_changed');
  if (mode === 'read' && !s.user.permissions.some((p) =>
    ['org.clinical.author', 'org.clinical.review'].includes(p)))
    throw new ApiError(403, 'permission_denied');
  return {
    token: s.token,
    base: '/organizations/' + resourceId(contextId) + '/training',
  };
}
function message(e: unknown) {
  const messages: Record<string, string> = {
    draft_revision_conflict: 'This draft changed. Reload before continuing.',
    draft_code_conflict: 'A draft already uses this code. Choose another code.',
    scenario_incomplete: 'Complete the case fields and validate before publishing.',
    translation_incomplete: 'Complete all content in this language before recording a review.',
    translation_review_required: 'Review the source language before publishing.',
    draft_archived: 'Restore this draft before editing.',
    draft_identity_conflict: 'The code and document format cannot change after creation.',
    draft_capacity: 'The tenant has reached its draft limit.',
    draft_not_submitted: 'Submit the saved revision before clinical review or publication.',
    specialty_required: 'Choose an active clinical specialty before submitting.',
    specialty_inactive: 'The clinical specialty is inactive. Choose another one.',
  };
  return e instanceof ApiError ? (messages[e.code] ?? consoleError(e)) : consoleError(e);
}
export async function listScenarios(
  contextId: string,
  q: { q: string; limit: number; view: string },
  cursor?: string,
): Promise<ApiResult<DirectoryPage<ScenarioRow>>> {
  try {
    const { base, token } = await access(contextId, 'read');
    const versionView = q.view === 'published' || q.view === 'retired';
    const result = await apiRequest<{
      items: ScenarioRow[];
      next_cursor: string | null;
    }>(
      base +
        (versionView ? '/scenarios' : '/scenario-drafts') +
        '?' +
        queryString({
          q: q.q,
          limit: q.limit,
          cursor,
          ...(versionView
            ? { schema_version: 'all', status: q.view === 'retired' ? 'retired' : 'approved' }
            : { archived: q.view === 'archived' }),
        }),
      { token },
    );
    return {
      value: {
        ...result,
        total: result.items.length,
        has_more: !!result.next_cursor,
      },
    };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}
export async function readScenario(
  contextId: string,
  id: string,
  published: boolean,
): Promise<ApiResult<ScenarioRow>> {
  try {
    const { base, token } = await access(contextId, 'read');
    return {
      value: await apiRequest<ScenarioRow>(
        base + (published ? '/scenarios/' : '/scenario-drafts/') + resourceId(id),
        { token },
      ),
    };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}
export async function createScenario(
  contextId: string,
  code: string,
  requestKey: string,
  sourceId?: string,
  sourceCaseId?: string,
  specialtyId?: string,
  title?: string,
): Promise<ApiResult<ScenarioRow>> {
  try {
    const { base, token } = await access(contextId);
    const r = await apiRequest<{ draft: ScenarioRow }>(base + '/scenario-drafts', {
      token,
      method: 'POST',
      body: {
        code,
        request_key: resourceId(requestKey),
        ...(sourceId ? { source_scenario_id: resourceId(sourceId) } :
          sourceCaseId ? { source_case_id: resourceId(sourceCaseId) } : {
            schema_version: 5,
            specialty_id: specialtyId ? resourceId(specialtyId) : undefined,
            document: { ...emptyDocument(), version: 5, code, title: title?.trim() || undefined },
          }),
      },
    });
    return { value: r.draft };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}
export async function saveScenario(contextId: string, row: ScenarioRow): Promise<ApiResult<ScenarioRow>> {
  try {
    const { base, token } = await access(contextId);
    return {
      value: await apiRequest<ScenarioRow>(base + '/scenario-drafts/' + resourceId(row.id), {
        token,
        method: 'PUT',
        body: { expected_revision: row.revision, document: row.document,
          specialty_id: row.specialty_id || undefined },
      }),
    };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}
export async function submitScenario(contextId: string, row: ScenarioRow): Promise<ApiResult<ScenarioRow>> {
  try {
    const { base, token } = await access(contextId);
    return { value: await apiRequest<ScenarioRow>(
      base + '/scenario-drafts/' + resourceId(row.id) + '/submit',
      { token, method: 'POST', body: { expected_revision: row.revision } },
    ) };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}
export async function archiveScenario(contextId: string, row: ScenarioRow): Promise<ApiResult<ScenarioRow>> {
  try {
    const { base, token } = await access(contextId);
    return {
      value: await apiRequest<ScenarioRow>(base + '/scenario-drafts/' + resourceId(row.id), {
        token,
        method: 'PATCH',
        body: {
          expected_revision: row.revision,
          is_archived: !row.is_archived,
        },
      }),
    };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}
export async function validateScenario(
  contextId: string,
  row: ScenarioRow,
): Promise<ApiResult<ScenarioValidation>> {
  try {
    const { base, token } = await access(contextId, 'read');
    return {
      value: await apiRequest<ScenarioValidation>(
        base + '/scenario-drafts/' + resourceId(row.id) + '/validate',
        { token, method: 'POST', body: { expected_revision: row.revision } },
      ),
    };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}
export async function approveScenario(
  contextId: string,
  row: ScenarioRow,
  approval: EducatorApproval,
  language: string,
  requestKey?: string,
): Promise<ApiResult<ScenarioRow>> {
  try {
    const { base, token } = await access(contextId, 'review');
    if (!/^[a-z]{2,3}(-[A-Z]{2})?$/.test(language)) throw new ApiError(422, 'invalid_language');
    const path = base + '/scenario-drafts/' + resourceId(row.id);
    if (requestKey) {
      const r = await apiRequest<{ scenario: ScenarioRow }>(path + '/publish', {
        token,
        method: 'POST',
        body: {
          expected_revision: row.revision,
          request_key: resourceId(requestKey),
          approval,
        },
      });
      return { value: r.scenario };
    }
    return {
      value: await apiRequest<ScenarioRow>(
        path + '/localizations/' + encodeURIComponent(language) + '/review',
        {
          token,
          method: 'POST',
          body: { expected_revision: row.revision, approval },
        },
      ),
    };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}
export async function retireScenario(contextId: string, id: string): Promise<ApiResult<boolean>> {
  try {
    const { base, token } = await access(contextId, 'review');
    await apiRequest(base + '/scenarios/' + resourceId(id) + '/retire', {
      token,
      method: 'POST',
    });
    return { value: true };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}

export async function refreshScenarioCase(contextId: string, row: ScenarioRow): Promise<ApiResult<ScenarioRow>> {
  try {
    const { base, token } = await access(contextId);
    return { value: await apiRequest<ScenarioRow>(
      base + '/scenario-drafts/' + resourceId(row.id) + '/refresh-case',
      { token, method: 'POST', body: { expected_revision: row.revision } }) };
  } catch (e) {
    return { error: [message(e), inputIssues(e)].filter(Boolean).join(' ') };
  }
}
