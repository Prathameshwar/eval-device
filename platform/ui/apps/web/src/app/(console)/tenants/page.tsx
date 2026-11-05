import type { Metadata } from 'next';
import { TenantList } from '@/components/TenantList';
import { requireTenantRead } from '@/lib/tenant-access';
export const metadata: Metadata = { title: 'Tenants' };
export default async function Page() {
  await requireTenantRead();
  return <TenantList />;
}
