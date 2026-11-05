import { Badge, type Tone } from '@pms/ui';
import { tenantStatus, type Tenant, type TenantStatus } from '@/lib/tenant-directory';
export const TENANT_STATUS: Record<TenantStatus, { label: string; tone: Tone }> = {
  active: { label: 'Active', tone: 'success' },
  inactive: { label: 'Inactive', tone: 'neutral' },
  archived: { label: 'Archived', tone: 'warn' },
};
export function TenantStatusBadge({ tenant }: { tenant: Tenant }) {
  const status = TENANT_STATUS[tenantStatus(tenant)];
  return <Badge tone={status.tone}>{status.label}</Badge>;
}
