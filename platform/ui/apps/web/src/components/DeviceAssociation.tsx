'use client';
import { useId, useState } from 'react';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, Drawer, Notice, Select, TextField, useGranted, useToast } from '@pms/ui';
import type { Device } from '@/lib/device-directory';
import { transferDevice } from '@/lib/device-actions';
import { useDeviceDirectory } from './DeviceDirectoryProvider';
export function DeviceAssociation({ device }: { device: Device }) {
  const { contextId, platform, scopeName, associationTargets = {}, remember } = useDeviceDirectory();
  const granted = useGranted(); const toast = useToast();
  const canManage = !!platform && granted('platform.organizations.manage');
  const [open, setOpen] = useState(false); const [target, setTarget] = useState(''); const [name, setName] = useState(device.name);
  const [active, setActive] = useState(false); const [busy, setBusy] = useState(false); const [confirm, setConfirm] = useState(false); const [error, setError] = useState<string>();
  const form = useId(); const targets = Object.entries(associationTargets).filter(([id]) => id !== device.organization_id);
  function close() { if (!busy) { setOpen(false); setConfirm(false); setError(undefined); } }
  async function transfer() {
    if (busy) return; setBusy(true); setError(undefined);
    try {
      const result = await transferDevice(contextId, device.id, target, name, active, device.management_etag);
      if (result.error !== undefined) { setError(result.error); return; }
      remember(result.value.source); setOpen(false); setConfirm(false);
      toast.success('A new registration was created in ' + associationTargets[target] + '. Its administrator must complete fresh enrollment.', { title: 'Tenant association changed' });
    } catch { setError('Unable to confirm the result. Refresh the registration before retrying.'); }
    finally { setBusy(false); }
  }
  return <Card><CardHeader title="Tenant association" /><CardBody>
    <p><strong>{device.organization_name ?? (platform ? device.organization_id : scopeName)}</strong></p>
    <p className="pms-meta" style={{ overflowWrap: 'anywhere' }}>{device.organization_id}</p>
    <p>Platform administrators manage transfers between tenants. Removing or transferring a registration retains its historical records in this tenant.</p>
    {canManage && device.enrollment_state !== 'retired' && <Button variant="ghost" disabled={!targets.length} onClick={() => { setName(device.name); setTarget(''); setActive(false); setError(undefined); setOpen(true); }}>Transfer to another tenant</Button>}
    {canManage && !targets.length && device.enrollment_state !== 'retired' && <p className="pms-hint">An active destination tenant is required.</p>}
    <Drawer open={open} title="Transfer device registration" onClose={close}
      footer={<><Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button><Button type="submit" form={form} disabled={busy}>Review transfer</Button></>}>
      <form id={form} onSubmit={event => { event.preventDefault(); if (target && name.trim()) setConfirm(true); }}>
        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <Select label="Destination tenant" required value={target} options={[{ value: '', label: 'Choose a tenant' }, ...targets.map(([value, label]) => ({ value, label }))]} onChange={setTarget} />
          <TextField label="Registration name" required value={name} maxLength={256} onChange={event => setName(event.target.value)} />
          <Select label="Destination status" value={String(active)} options={[{ value: 'false', label: 'Inactive until configured' }, { value: 'true', label: 'Active (uses a device seat)' }]} onChange={value => setActive(value === 'true')} />
          <Notice tone="warning">This retires the current registration and revokes its credential and enrollment token. The device keeps its unique ID and receives a new registration requiring fresh enrollment. Configuration, contact details, location, health, sessions and results stay in the source tenant.</Notice>
        </fieldset>
      </form>
    </Drawer>
    <ConfirmDialog open={confirm} title="Confirm tenant transfer" confirmLabel="Transfer registration" tone="danger" busy={busy} error={error} onCancel={() => { setConfirm(false); setError(undefined); }} onConfirm={() => void transfer()}>
      Move {device.name} to {associationTargets[target]}? The current registration cannot be reactivated after transfer.
    </ConfirmDialog>
  </CardBody></Card>;
}
