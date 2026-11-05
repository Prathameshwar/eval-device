import type { ReactNode } from 'react';
import { Notice } from '@pms/ui';
import { TenantDirectoryProvider } from '@/components/TenantDirectoryProvider';
import { tenantPlans } from '@/lib/tenant-actions';
import { consoleError } from '@/lib/console-errors';
import { requireTenantRead } from '@/lib/tenant-access';
export default async function TenantLayout({ children }: { children: ReactNode }) {
  await requireTenantRead();
  try {
    const { plans, activePlans } = await tenantPlans();
    return <TenantDirectoryProvider plans={plans} activePlans={activePlans}>{children}</TenantDirectoryProvider>;
  } catch (error) {
    return <Notice tone="danger" title="Tenants unavailable">{consoleError(error)} <a href="/tenants">Retry</a></Notice>;
  }
}
