'use client';
import { useId, useState } from 'react';
import { Button, ConfirmDialog, Drawer, Notice, Select, TextField } from '@pms/ui';
import { deviceDraft, type DeviceDraft } from '@/lib/device-editor';
import { DEVICE_TYPES, type Device } from '@/lib/device-directory';

export function FleetDeviceEditor({ device, tenants, languages, onSave, onClose }: {
  device: Device | null; tenants: Readonly<Record<string, string>>; languages: Readonly<Record<string, string>>;
  onSave: (draft: DeviceDraft) => Promise<string | undefined>; onClose: () => void;
}) {
  const [draft, setDraft] = useState(() => deviceDraft(device));
  const [initial] = useState(() => deviceDraft(device));
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string>(); const [discard, setDiscard] = useState(false);
  const form = useId();
  const change = (patch: Partial<DeviceDraft>) => setDraft(current => ({ ...current, ...patch }));
  function close() { if (busy) return; if (JSON.stringify(draft) !== JSON.stringify(initial)) setDiscard(true); else onClose(); }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (busy) return;
    if (!draft.name.trim() || !device && !tenants[draft.organization_id]) { setError('Enter a name and select an active tenant.'); return; }
    if (!device && (!draft.device_unique_id.trim() || draft.device_unique_id.trim().length > 50)) { setError('Enter a device unique ID of up to 50 characters.'); return; }
    setBusy(true); setError(undefined);
    try { setError(await onSave(draft)); } catch { setError('Unable to confirm the result. Refresh the directory before retrying.'); }
    finally { setBusy(false); }
  }
  return <>
    <Drawer open title={device ? 'Edit registration' : 'Register device with tenant'} onClose={close}
      footer={<><Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button><Button type="submit" form={form} loading={busy}>{device ? 'Save changes' : 'Register device'}</Button></>}>
      <form id={form} onSubmit={submit}>
        {error && <Notice tone="danger">{error}</Notice>}
        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <TextField label="Device unique ID" required={!device} readOnly={!!device} maxLength={50} value={draft.device_unique_id} onChange={e => { if (!device) change({ device_unique_id: e.target.value }); }} hint="Unique across the platform. Cannot be changed after registration." />
          <TextField label="Device name" required maxLength={256} value={draft.name} onChange={e => change({ name: e.target.value })} />
          {!device ? <>
            <Select label="Tenant association" required value={draft.organization_id}
              options={[{ value: '', label: 'Choose an active tenant' }, ...Object.entries(tenants).map(([value, label]) => ({ value, label }))]}
              onChange={organization_id => change({ organization_id })} />
            <Select label="Device type" value={draft.device_type} options={[...DEVICE_TYPES]} onChange={value => change({ device_type: value as DeviceDraft['device_type'] })} />
            <Select label="Preferred language" value={draft.preferred_language} options={[{ value: '', label: 'Default (English)' }, ...Object.entries(languages).map(([value, label]) => ({ value, label }))]} onChange={preferred_language => change({ preferred_language })} />
          </> : <p>Tenant: {device.organization_name ?? device.organization_id}. Use Transfer to change the tenant.</p>}
          <Select label="Device status" value={String(draft.is_active)} options={[{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }]} onChange={value => change({ is_active: value === 'true' })} />
          <p className="pms-hint">Use Configure model in the device menu after saving this registration.</p>
        </fieldset>
      </form>
    </Drawer>
    <ConfirmDialog open={discard} title="Discard unsaved changes?" confirmLabel="Discard changes" onConfirm={onClose} onCancel={() => setDiscard(false)}>Your changes have not been saved.</ConfirmDialog>
  </>;
}
