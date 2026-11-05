import type { MemberRole } from './people';

export type ImportOptions = { role: MemberRole; auth_method: 'local' | 'oidc'; department_id: string };
export type ImportRow = {
  row_number: number; full_name: string; email: string;
  status: 'ready' | 'invalid' | 'succeeded' | 'failed'; code: string | null;
  message: string | null; membership_id: string | null; email_status?: string | null;
  has_password?: boolean; password?: string | null;
};
export type ImportSummary = {
  id: string; role: MemberRole; auth_method: 'local' | 'oidc'; department_id: string | null;
  status: 'validated' | 'completed'; created_at: string; completed_at: string | null;
  validated_until: string; expires_at: string; email_configured: boolean;
  counts: { total: number; ready: number; succeeded: number; failed: number };
  password_count: number;
};
export type MemberImport = ImportSummary & { rows: ImportRow[] };
export const IMPORT_ROLES = [
  { value: 'org_user', label: 'User' }, { value: 'org_trainee', label: 'Trainee / student' },
  { value: 'org_read_only', label: 'Read only' }, { value: 'org_admin', label: 'Tenant administrator' },
];
export function importRole(role: string) { return IMPORT_ROLES.find(item => item.value === role)?.label ?? role; }
export function importOptions(options: ImportOptions) {
  if (!IMPORT_ROLES.some(role => role.value === options.role) ||
      !['local', 'oidc'].includes(options.auth_method) ||
      options.role === 'org_admin' && options.department_id) throw new Error('Invalid import options');
  return new URLSearchParams({ role: options.role, auth_method: options.auth_method,
    ...(options.department_id ? { department_id: options.department_id } : {}) }).toString();
}
