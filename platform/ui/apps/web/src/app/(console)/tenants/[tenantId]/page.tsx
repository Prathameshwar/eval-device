import { BackNavigation } from '@/components/BackNavigation';
import type { Metadata } from 'next';
import { TenantDetails } from '@/components/TenantDetails';
import { Notice } from '@pms/ui';
import { readTenant } from '@/lib/tenant-actions';
import { requireTenantRead } from '@/lib/tenant-access';
export const metadata: Metadata = { title: 'Tenant details' };
export default async function Page({ params }: { params: Promise<{ tenantId: string }> }) {
  await requireTenantRead();
  const { tenantId } = await params;
  const result = await readTenant(tenantId);
  if (result.error !== undefined) return <div className="pms-page"><BackNavigation href="/tenants" label="Back to tenants" /><Notice tone="danger" title="Tenant unavailable">{result.error}</Notice></div>;
  return <TenantDetails key={tenantId} tenantId={tenantId} initialTenant={result.value} />;
}
