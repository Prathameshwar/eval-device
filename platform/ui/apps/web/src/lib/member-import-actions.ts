'use server';
import { revalidatePath } from 'next/cache';
import { ApiError } from './api';
import { resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult } from './directory-api';
import { importOptions, type ImportOptions, type ImportSummary, type MemberImport } from './member-imports';
import { importRequest } from './member-import-transport';

export async function importError(error: unknown): Promise<string> {
  const messages: Record<string, string> = {
    import_file_size: 'Choose an Excel file no larger than 512 KB.',
    payload_too_large: 'Choose an Excel file no larger than 512 KB.',
    import_workbook_limit: 'This workbook is too complex. Use a fresh template.',
    import_invalid_workbook: 'The file could not be read. Download a fresh .xlsx template.',
    import_headers: 'Keep the Full name, Email, and optional Password headings exactly as in the template.',
    import_sheet: 'The workbook needs a sheet named Members.',
    import_columns: 'Use only the supplied workbook columns.',
    import_row_limit: 'Use at most 200 rows per workbook.',
    import_empty: 'Add at least one person to the Members sheet.',
    import_expired: 'This validation expired. Upload and validate the workbook again.',
    import_no_valid_rows: 'Correct the errors and validate a new workbook first.',
    import_history_limit: 'This tenant has reached 100 retained imports. Older results expire after 30 days.',
    local_auth_disabled: 'Local account sign-in is disabled. Choose external sign-in if it is configured.',
  };
  return error instanceof ApiError && messages[error.code] ? messages[error.code]! : consoleError(error);
}
export async function validateMemberImport(contextId: string, options: ImportOptions, form: FormData): Promise<ApiResult<MemberImport>> {
  try {
    const query = importOptions(options);
    if (options.department_id) resourceId(options.department_id);
    const file = form.get('file');
    if (!(file instanceof File) || !file.name.toLowerCase().endsWith('.xlsx') || !file.size || file.size > 512 * 1024)
      throw new ApiError(422, 'import_file_size');
    const response = await importRequest(contextId, '/validate?' + query, { method: 'POST',
      headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
      body: await file.arrayBuffer() });
    return { value: await response.json() };
  } catch (error) { return { error: await importError(error) }; }
}
export async function readMemberImport(contextId: string, id: string): Promise<ApiResult<MemberImport>> {
  try { return { value: await (await importRequest(contextId, '/' + resourceId(id))).json() }; }
  catch (error) { return { error: await importError(error) }; }
}
export async function commitMemberImport(contextId: string, id: string): Promise<ApiResult<MemberImport>> {
  try {
    const value = await (await importRequest(contextId, '/' + resourceId(id) + '/commit', { method: 'POST' })).json();
    revalidatePath('/members');
    return { value };
  } catch (error) { return { error: await importError(error) }; }
}
export async function memberImportHistory(contextId: string): Promise<ApiResult<ImportSummary[]>> {
  try { return { value: (await (await importRequest(contextId, '')).json()).items }; }
  catch (error) { return { error: await importError(error) }; }
}
