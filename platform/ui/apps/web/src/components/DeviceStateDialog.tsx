'use client';
import { useState } from 'react';
import { ConfirmDialog } from '@pms/ui';
import type { Device } from '@/lib/device-directory';
import { changeDeviceLifecycle } from '@/lib/device-actions';
import { useDeviceDirectory } from './DeviceDirectoryProvider';
export function DeviceStateDialog({ device, onClose }: { device: Device; onClose: () => void }) {
  const { contextId, remember } = useDeviceDirectory();
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string>();
  const verb = device.is_active ? 'Deactivate' : 'Activate';
  return <ConfirmDialog open title={verb + ' ' + device.name + '?'} confirmLabel={verb + ' device'} busy={busy} error={error} tone={device.is_active ? 'danger' : 'default'} onCancel={onClose} onConfirm={async () => {
    if (busy) return; setBusy(true); setError(undefined);
    try {
      const result = await changeDeviceLifecycle(contextId, device.id, device.is_active ? 'deactivate' : 'activate', device.management_etag);
      if (result.error !== undefined) { setError(result.error); return; }
      remember(result.value); onClose();
    } catch { setError('Unable to confirm the result. Refresh the device before trying again.'); }
    finally { setBusy(false); }
  }}>
    {device.is_active ? 'This blocks processing while retaining the tenant association and credential for health/status checks. It frees a device seat.' : 'Activation requires an available tenant, valid assignments and a free device seat. Enrollment and configuration are still required for processing.'}
  </ConfirmDialog>;
}
