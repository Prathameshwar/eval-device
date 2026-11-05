'use client';
import type { Tenant } from '@/lib/tenant-directory';
import { TenantAdministration } from './TenantAdministration';

export function TenantAssociations({ tenant, onClose }: { tenant: Tenant; onClose: () => void }) {
  return <TenantAdministration tenant={tenant} onClose={onClose} initialTab="administrators" />;
}
