'use client';
import { createContext, useContext, useRef, useState, type ReactNode } from 'react';
import { DEFAULT_TENANT_QUERY, type Tenant } from '@/lib/tenant-directory';
import { validateTenantDraft, type TenantDraft } from '@/lib/tenant-editor';
import { listTenants, saveTenant, tenantLifecycle } from '@/lib/tenant-actions';
import { useApiDirectory } from '@/lib/use-api-directory';

type SavedTenant = { id: string; name: string; created: boolean };
type SaveResult = { tenant: Tenant; error?: never } | { tenant?: never; error: string };
function useDirectoryState(initialRows: readonly Tenant[], plans: Readonly<Record<string, string>>, activePlans: Readonly<Record<string, string>>) {
  const [rows, setRows] = useState(initialRows);
  const directory = useApiDirectory(DEFAULT_TENANT_QUERY, listTenants);
  const [savedTenant, setSavedTenant] = useState<SavedTenant | null>(null);
  const listBookmark = useRef<{ id: string; tableTop: number; pageTop: number } | null>(null);
  function remember(tenant: Tenant) {
    setRows(current => [tenant, ...current.filter(row => row.id !== tenant.id)]);
    directory.reload();
  }
  async function save(draft: TenantDraft, original: Tenant | null): Promise<SaveResult> {
    if (Object.keys(validateTenantDraft(draft, activePlans, !original)).length) return { error: 'Check the tenant details before saving.' };
    const result = await saveTenant(draft, original?.id, original?.management_version);
    if (result.error !== undefined) return { error: result.error };
    remember(result.value);
    setSavedTenant({ id: result.value.id, name: result.value.name, created: !original });
    return { tenant: result.value };
  }
  async function archive(original: Tenant, restore = false): Promise<string | undefined> {
    try {
      const result = await tenantLifecycle(original.id, original.management_version, restore);
      if (result.error !== undefined) return result.error;
      remember(result.value); setSavedTenant(null);
    } catch { return 'Unable to confirm the result. Refresh this record before retrying.'; }
  }
  return { ...directory, rows, plans, activePlans, savedTenant, setSavedTenant, listBookmark, save, archive, remember };
}
const DirectoryContext = createContext<ReturnType<typeof useDirectoryState> | null>(null);
export function TenantDirectoryProvider({ initialRows = [], plans, activePlans = plans, children }: {
  initialRows?: readonly Tenant[]; plans: Readonly<Record<string, string>>; activePlans?: Readonly<Record<string, string>>; children: ReactNode;
}) {
  const state = useDirectoryState(initialRows, plans, activePlans);
  return <DirectoryContext.Provider value={state}>{children}</DirectoryContext.Provider>;
}
export function useTenantDirectory() {
  const state = useContext(DirectoryContext);
  if (!state) throw new Error('Tenant pages require TenantDirectoryProvider.');
  return state;
}
