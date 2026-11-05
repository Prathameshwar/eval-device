import { isEmailLike, normalizeEmail } from '@pms/ui';
import type { Tenant } from './tenant-directory';

/** Tenant detail fields follow OrganizationCreate / OrganizationPatch, not subscription assignment. */
export type TenantDraft = {
  name: string;
  description: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  subscription_plan_id: string;
  is_active: boolean;
};
export type TenantField = Exclude<keyof TenantDraft, 'is_active'>;
export type TenantErrors = Partial<Record<TenantField, string>>;
export const TENANT_FIELD_LIMITS = {
  name: 256, description: 4000, contact_name: 256, contact_email: 320, contact_phone: 80,
} as const;

export function tenantDraft(tenant: Tenant | null): TenantDraft {
  return {
    name: tenant?.name ?? '', description: tenant?.description ?? '',
    contact_name: tenant?.contact_name ?? '', contact_email: tenant?.contact_email ?? '',
    contact_phone: tenant?.contact_phone ?? '', subscription_plan_id: tenant?.subscription_plan_id ?? '',
    is_active: tenant?.is_active ?? false,
  };
}

export function validateTenantDraft(draft: TenantDraft, plans: Readonly<Record<string, string>>, creating: boolean): TenantErrors {
  const errors: TenantErrors = {};
  if (!draft.name.trim()) errors.name = 'Enter a tenant name.';
  for (const field of Object.keys(TENANT_FIELD_LIMITS) as (keyof typeof TENANT_FIELD_LIMITS)[]) {
    if (draft[field].trim().length > TENANT_FIELD_LIMITS[field]) {
      errors[field] = `Use ${TENANT_FIELD_LIMITS[field]} characters or fewer.`;
    }
  }
  const email = normalizeEmail(draft.contact_email);
  if (email && !isEmailLike(email)) errors.contact_email = 'Enter an email address such as name@example.com.';
  if (creating && !Object.prototype.hasOwnProperty.call(plans, draft.subscription_plan_id)) {
    errors.subscription_plan_id = 'Choose an available subscription plan.';
  }
  return errors;
}

/** Called only on a local save. UUIDs/timestamps are event values, never initial render values. */
export function saveTenantDraft(draft: TenantDraft, tenant: Tenant | null, id: string, timestamp: string): Tenant {
  const optional = (value: string) => value.trim() || null;
  return {
    id: tenant?.id ?? id,
    name: draft.name.trim(), description: optional(draft.description),
    contact_name: optional(draft.contact_name), contact_email: optional(normalizeEmail(draft.contact_email)),
    contact_phone: optional(draft.contact_phone),
    // Creation starts inactive; an edit cannot silently reassign the subscription.
    subscription_plan_id: tenant?.subscription_plan_id ?? draft.subscription_plan_id,
    is_active: tenant ? draft.is_active : false,
    archived_at: tenant?.archived_at ?? null,
    created_at: tenant?.created_at ?? timestamp, updated_at: timestamp,
    management_version: (tenant?.management_version ?? 0) + 1,
  };
}
