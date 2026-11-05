/** The fields consumed from GET /platform/organizations. Tenant is the UI label. */
export type Tenant = {
  id: string;
  name: string;
  description: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  subscription_plan_id: string;
  is_active: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  management_version: number;
};

export type TenantStatus = 'active' | 'inactive' | 'archived';
export type TenantQuery = {
  q: string;
  is_active: boolean | undefined;
  archived: boolean | undefined;
  sort_by: 'name' | 'created_at' | 'updated_at';
  sort_order: 'asc' | 'desc';
  limit: number;
};

export const TENANT_PAGE_LIMITS = [25, 50, 100] as const;
export const DEFAULT_TENANT_QUERY: TenantQuery = {
  q: '', is_active: undefined, archived: false,
  sort_by: 'name', sort_order: 'asc', limit: 25,
};

export function tenantStatus(tenant: Tenant): TenantStatus {
  return tenant.archived_at ? 'archived' : tenant.is_active ? 'active' : 'inactive';
}

/**
 * Local preview only. Filter/sort the entire fixture before slicing, never the visible page.
 * The API uses cursor/has_more; page numbers here are internal navigation state, not a promise
 * of random page access. A future adapter will keep previous cursors for the same two buttons.
 */
export function tenantPage(rows: readonly Tenant[], query: TenantQuery, requestedPage: number) {
  const needle = query.q.trim().slice(0, 128).toLowerCase();
  const direction = query.sort_order === 'asc' ? 1 : -1;
  const compare = (left: string, right: string) => left < right ? -1 : left > right ? 1 : 0;
  const matches = rows.filter((row) =>
    (!needle || row.name.toLowerCase().includes(needle)) &&
    (query.is_active === undefined || row.is_active === query.is_active) &&
    (query.archived === undefined || Boolean(row.archived_at) === query.archived),
  ).sort((left, right) => direction * (
    compare(left[query.sort_by], right[query.sort_by]) || compare(left.id, right.id)
  ));
  const limit = Math.max(1, Math.min(100, query.limit));
  // Deleting the final record on a page returns to the last remaining page.
  const page = Math.max(0, Math.min(requestedPage, Math.ceil(matches.length / limit) - 1));
  const offset = page * limit;
  return {
    items: matches.slice(offset, offset + limit),
    total: matches.length,
    page,
    from: matches.length ? offset + 1 : 0,
    has_more: offset + limit < matches.length,
  };
}

export function archiveTenant(row: Tenant, timestamp: string): Tenant {
  if (row.archived_at) return row;
  return {
    ...row, is_active: false, archived_at: timestamp, updated_at: timestamp,
    management_version: row.management_version + 1,
  };
}
