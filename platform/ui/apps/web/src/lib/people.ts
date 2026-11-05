export type MemberRole = 'org_admin' | 'org_user' | 'org_read_only' | 'org_trainee';
export const MEMBER_ROLES = [
  { value: 'org_admin', label: 'Tenant administrator' }, { value: 'org_user', label: 'User' },
  { value: 'org_read_only', label: 'Read only' }, { value: 'org_trainee', label: 'Trainee' },
];
export type Person = {
  id: string; display_name: string | null; email: string; phone?: string | null;
  auth_method?: 'local' | 'oidc'; platform_role?: 'platform_admin' | null; setup_pending?: boolean;
  tenant_admin?: boolean;
  role?: MemberRole; department_id?: string | null; user_id?: string | null;
  invitation_status?: 'pending' | 'accepted' | 'revoked' | 'expired';
  invitation_auth_method?: 'local' | 'oidc' | null; invited_email?: string | null; invitation_expires_at?: string | null;
  is_active: boolean; archived_at: string | null; status_reason: string | null;
  created_at: string; updated_at: string; joined_at?: string | null; management_version: number;
  user?: { id: string; display_name: string; email: string; auth_method: 'local' | 'oidc'; is_active: boolean; archived_at: string | null } | null;
};
export type DepartmentOption = { id: string; name: string; is_active: boolean; archived_at: string | null };
export type TenantOption = { id: string; name: string; is_active: boolean; archived_at: string | null };
export type PeopleQuery = { q: string; state: string; role: string; auth_method: string; department_id: string; sort_by: string; sort_order: 'asc' | 'desc'; limit: number };
export const peopleQuery = (platform: boolean): PeopleQuery => ({ q: '', state: 'current', role: '', auth_method: '', department_id: '', sort_by: platform ? 'display_name' : 'name', sort_order: 'asc', limit: 25 });
export type PersonDraft = { display_name: string; email: string; phone: string; auth_method: 'local' | 'oidc'; role: string; organization_id?: string; department_id: string; is_active: boolean; status_reason: string };
export function personDraft(platform: boolean, row?: Person | null): PersonDraft {
  return { display_name: row?.display_name ?? '', email: row?.email ?? '', phone: row?.phone ?? '',
    auth_method: row?.auth_method ?? row?.invitation_auth_method ?? 'local', role: platform ? row?.platform_role ?? '' : row?.role ?? 'org_user',
    organization_id: '', department_id: row?.department_id ?? '', is_active: row?.is_active ?? true, status_reason: row?.status_reason ?? '' };
}
export function platformPersonRole(row: Person): string {
  return [row.platform_role === 'platform_admin' ? 'Platform administrator' : '', row.tenant_admin ? 'Tenant administrator' : ''].filter(Boolean).join(', ') || 'User';
}
export function personView(row: Person, platform: boolean): Person {
  return platform ? row : { ...row, display_name: row.user?.display_name ?? null, email: row.user?.email ?? row.invited_email ?? '' };
}
export function personState(row: Person): string {
  if (row.archived_at) return 'Archived';
  if (row.invitation_status && row.invitation_status !== 'accepted') {
    if (row.invitation_status === 'pending' && row.invitation_expires_at && Date.parse(row.invitation_expires_at) <= Date.now()) return 'Expired';
    return row.invitation_status[0]!.toUpperCase() + row.invitation_status.slice(1);
  }
  if (!row.is_active) return 'Disabled';
  if (row.user && (!row.user.is_active || row.user.archived_at)) return 'Account unavailable';
  return row.setup_pending ? 'Setup pending' : 'Enabled';
}
export type PersonAction = 'archive' | 'restore' | 'enable' | 'disable' | 'resend' | 'revoke' | 'setup';
export type PersonResult = { person: Person; email_delivered?: boolean; invitation_token?: string | null; setup_token?: string | null; setup_queued?: boolean };
