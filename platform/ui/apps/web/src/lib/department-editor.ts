import type { Department } from './department-directory';

export type DepartmentDraft = {
  name: string;
  description: string;
  is_active: boolean;
  status_reason: string;
};

export type DepartmentField = Exclude<keyof DepartmentDraft, 'is_active'>;
export type DepartmentErrors = Partial<Record<DepartmentField, string>>;

export const DEPARTMENT_FIELD_LIMITS = {
  name: 80,
  description: 4000,
  status_reason: 4000,
} as const;

export function departmentDraft(row: Department | null): DepartmentDraft {
  return {
    name: row?.name ?? '',
    description: row?.description ?? '',
    is_active: row?.is_active ?? true,
    status_reason: row?.status_reason ?? '',
  };
}

export function validateDepartmentDraft(draft: DepartmentDraft): DepartmentErrors {
  const errors: DepartmentErrors = {};

  if (!draft.name.trim()) {
    errors.name = 'Enter a department name.';
  }

  for (const field of Object.keys(DEPARTMENT_FIELD_LIMITS) as (keyof typeof DEPARTMENT_FIELD_LIMITS)[]) {
    if (draft[field].trim().length > DEPARTMENT_FIELD_LIMITS[field]) {
      errors[field] = `Use ${DEPARTMENT_FIELD_LIMITS[field]} characters or fewer.`;
    }
  }

  return errors;
}

export function saveDepartmentDraft(
  draft: DepartmentDraft,
  row: Department | null,
  id: string,
  timestamp: string
): Department {
  const optional = (value: string) => value.trim() || null;
  return {
    id: row?.id ?? id,
    organization_id: row?.organization_id ?? '10000000-0000-4000-8000-000000000001',
    name: draft.name.trim(),
    description: optional(draft.description),
    is_active: draft.is_active,
    status_reason: optional(draft.status_reason),
    created_at: row?.created_at ?? timestamp,
    updated_at: timestamp,
    archived_at: row?.archived_at ?? null,
    management_version: (row?.management_version ?? 0) + 1,
  };
}
