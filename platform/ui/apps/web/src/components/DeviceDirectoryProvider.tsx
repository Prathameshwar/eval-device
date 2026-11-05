'use client';
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';
import { DEFAULT_DEVICE_QUERY, type Device } from '@/lib/device-directory';
import { validateDeviceDraft, type DeviceDraft } from '@/lib/device-editor';
import { changeDeviceLifecycle, listDevices, saveDevice } from '@/lib/device-actions';
import { useApiDirectory } from '@/lib/use-api-directory';
type SavedDevice = { id: string; name: string; created: boolean };
type SaveResult = { device: Device; error?: never } | { device?: never; error: string };
function useDirectoryState(contextId: string, initialRows: readonly Device[], departments: Readonly<Record<string, string>>) {
  const [rows, setRows] = useState(initialRows);
  const fetchPage = useCallback((query: typeof DEFAULT_DEVICE_QUERY, cursor?: string) => listDevices(contextId, query, cursor), [contextId]);
  const directory = useApiDirectory(DEFAULT_DEVICE_QUERY, fetchPage);
  const [savedDevice, setSavedDevice] = useState<SavedDevice | null>(null);
  const listBookmark = useRef<{ id: string; tableTop: number; pageTop: number } | null>(null);
  function remember(row: Device) {
    setRows(current => [row, ...current.filter(item => item.id !== row.id)]);
    directory.reload();
  }
  async function save(draft: DeviceDraft, original: Device | null): Promise<SaveResult> {
    if (contextId !== 'platform' && Object.keys(validateDeviceDraft(draft, departments, !original, original)).length) return { error: 'Check the device details before saving.' };
    const result = await saveDevice(contextId, draft, original?.id, original?.management_etag);
    if (result.error !== undefined) return { error: result.error };
    remember(result.value); setSavedDevice({ id: result.value.id, name: result.value.name, created: !original });
    return { device: result.value };
  }
  async function retire(original: Device): Promise<string | undefined> {
    try {
      const result = await changeDeviceLifecycle(contextId, original.id, 'retire', original.management_etag);
      if (result.error !== undefined) return result.error;
      remember(result.value); setSavedDevice(null);
    } catch { return 'Unable to complete this request. Refresh to check the device before retrying.'; }
  }
  return { ...directory, rows, departments, savedDevice, setSavedDevice, listBookmark, save, retire, remember };
}
type Options = { contextId: string; associationTargets?: Readonly<Record<string, string>>; initialRows?: readonly Device[]; departments: Readonly<Record<string, string>>; tenants?: Readonly<Record<string, string>>; languages?: Readonly<Record<string, string>>; platform?: boolean; scopeName?: string; children: ReactNode };
type State = ReturnType<typeof useDirectoryState> & Pick<Options, 'tenants' | 'languages' | 'platform' | 'scopeName' | 'contextId' | 'associationTargets'>;
const DirectoryContext = createContext<State | null>(null);
export function DeviceDirectoryProvider({ contextId, associationTargets = {}, initialRows = [], departments, tenants = {}, languages = {}, platform = false, scopeName = 'Tenant', children }: Options) {
  const state = useDirectoryState(contextId, initialRows, departments);
  return <DirectoryContext.Provider value={{ ...state, tenants, languages, platform, scopeName, contextId, associationTargets }}>{children}</DirectoryContext.Provider>;
}
export function useDeviceDirectory() {
  const state = useContext(DirectoryContext);
  if (!state) throw new Error('Device pages require DeviceDirectoryProvider.');
  return state;
}
