export type Department = {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  status_reason: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  management_version: number;
};

export type DepartmentQuery = {
  q: string;
  is_active: boolean | undefined;
  archived: boolean | undefined;
  sort_by: 'name' | 'created_at';
  sort_order: 'asc' | 'desc';
  limit: number;
};

export const DEPARTMENT_PAGE_LIMITS = [25, 50, 100] as const;

export const DEFAULT_DEPARTMENT_QUERY: DepartmentQuery = {
  q: '',
  is_active: undefined,
  archived: false,
  sort_by: 'name',
  sort_order: 'asc',
  limit: 25,
};

export function departmentStatus(row: Department): 'active' | 'inactive' | 'archived' {
  if (row.archived_at) return 'archived';
  return row.is_active ? 'active' : 'inactive';
}

/**
 * Filter, Sort, and Slice mock departments locally.
 */
export function departmentPage(
  rows: readonly Department[],
  query: DepartmentQuery,
  requestedPage: number
) {
  const needle = query.q.trim().slice(0, 128).toLowerCase();
  const direction = query.sort_order === 'asc' ? 1 : -1;
  const compare = (left: string | null, right: string | null) => {
    const l = left ?? '';
    const r = right ?? '';
    return l < r ? -1 : l > r ? 1 : 0;
  };

  const matches = rows.filter((row) => {
    const matchesQuery = !needle ||
      row.name.toLowerCase().includes(needle) ||
      (row.description && row.description.toLowerCase().includes(needle)) ||
      row.id.toLowerCase().includes(needle);

    const matchesActive = query.is_active === undefined || row.is_active === query.is_active;
    const matchesArchived = query.archived === undefined || (Boolean(row.archived_at) === query.archived);

    return matchesQuery && matchesActive && matchesArchived;
  }).sort((left, right) => {
    const primaryCompare = compare(left[query.sort_by], right[query.sort_by]);
    return direction * (primaryCompare || compare(left.id, right.id));
  });

  const limit = Math.max(1, Math.min(100, query.limit));
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

export function archiveDepartment(row: Department, timestamp: string): Department {
  if (row.archived_at) return row;
  return {
    ...row,
    is_active: false,
    archived_at: timestamp,
    updated_at: timestamp,
    management_version: row.management_version + 1,
  };
}
