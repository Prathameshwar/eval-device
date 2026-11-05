'use server';
import { ApiError, apiRequest } from './api';
import { consoleSession, resourceId, queryString } from './console-api';
import { consoleError } from './console-errors';
import { inputIssues } from './input-errors';
import type { ApiResult, DirectoryPage } from './directory-api';
import {
  catalogPayload,
  validateCatalog,
  type CatalogKind,
  type CatalogRecord,
  type CatalogOptions,
  type CatalogQuery,
} from './patient-catalog';

async function access(kind?: CatalogKind, manage = false) {
  if (kind && !['categories', 'patients', 'cases'].includes(kind)) throw new ApiError(404, 'not_found');
  const session = await consoleSession(manage ? 'org.clinical.author' : 'org.status.read');
  if (!session.user.contextId || session.user.contextId === 'platform' ||
      (!manage && !session.user.permissions.some((p) =>
        ['org.clinical.author', 'org.clinical.review', 'org.clinical.read'].includes(p))))
    throw new ApiError(403, 'permission_denied');
  return {
    token: session.token,
    base: '/organizations/' + resourceId(session.user.contextId) + '/clinical-catalog' +
      (kind ? '/' + (kind === 'categories' ? 'specialties' : kind) : ''),
  };
}
function record(row: CatalogRecord): CatalogRecord {
  return { ...row, category_id: row.specialty_id ?? row.category_id,
    patient_identity_id: row.patient_profile_id ?? row.patient_identity_id };
}
function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return consoleError(error);
  const messages: Record<string, string> = {
    catalog_duplicate: 'This code or name already exists. Choose a different one.',
    catalog_limit: 'This catalog has reached its record limit. Edit an existing record.',
    case_incomplete: 'Complete the required case fields before activation.',
    invalid_case_document:
      'Check the case fields and fact references. Answers cannot reference facts marked Never disclose.',
    catalog_parent_inactive: 'Activate the clinical specialty and patient profile before activating this case.',
    catalog_parent_archived: 'Restore the clinical specialty and patient profile before editing this case.',
    catalog_in_use: 'Deactivate active cases that use this clinical specialty or patient profile first.',
    catalog_code_immutable: 'The code cannot change after creation.',
    case_relationship_immutable: 'Create a new case to change its clinical specialty or patient profile.',
  };
  const issues = inputIssues(error);
  return (messages[error.code] ?? consoleError(error)) + (issues ? ' ' + issues : '');
}
export async function listCatalog(
  kind: CatalogKind,
  query: CatalogQuery,
  cursor?: string,
): Promise<ApiResult<DirectoryPage<CatalogRecord>>> {
  try {
    const { base, token } = await access(kind);
    const result = await apiRequest<DirectoryPage<CatalogRecord>>(
      base + '?' + queryString({ ...query, cursor }), { token });
    return {
      value: { ...result, items: result.items.map(record) },
    };
  } catch (error) {
    return { error: errorMessage(error) };
  }
}
export async function catalogOptions(): Promise<ApiResult<CatalogOptions>> {
  try {
    const { base, token } = await access();
    const options = await apiRequest<CatalogOptions & { specialties: CatalogRecord[] }>(
      base + '/options', { token });
    return { value: { ...options, categories: options.specialties } };
  } catch (error) {
    return { error: errorMessage(error) };
  }
}
export async function readCatalog(kind: CatalogKind, id: string): Promise<ApiResult<CatalogRecord>> {
  try {
    const { base, token } = await access(kind);
    return {
      value: record(await apiRequest<CatalogRecord>(base + '/' + resourceId(id), {
        token,
      })),
    };
  } catch (error) {
    return { error: errorMessage(error) };
  }
}
export async function saveCatalog(kind: CatalogKind, row: CatalogRecord): Promise<ApiResult<CatalogRecord>> {
  try {
    const { base, token } = await access(kind, true);
    const errors = validateCatalog(kind, row);
    if (errors.length) return { error: errors.join(' ') };
    const data = catalogPayload(kind, row);
    return {
      value: record(await apiRequest<CatalogRecord>(base + (row.id ? '/' + resourceId(row.id) : ''), {
        token,
        method: row.id ? 'PATCH' : 'POST',
        body: row.id ? { expected_version: row.version, data } : data,
      })),
    };
  } catch (error) {
    return { error: errorMessage(error) };
  }
}
export async function setCatalogActive(
  kind: CatalogKind,
  id: string,
  version: number,
  active: boolean,
): Promise<ApiResult<CatalogRecord>> {
  try {
    const { base, token } = await access(kind, true);
    return {
      value: record(await apiRequest<CatalogRecord>(
        base +
          '/' +
          resourceId(id) +
          (active ? '/restore' : '?expected_version=' + encodeURIComponent(version)),
        {
          token,
          method: active ? 'POST' : 'DELETE',
          ...(active ? { body: { expected_version: version } } : {}),
        },
      )),
    };
  } catch (error) {
    return { error: errorMessage(error) };
  }
}
