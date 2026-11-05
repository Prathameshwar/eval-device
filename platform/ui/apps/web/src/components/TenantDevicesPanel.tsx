'use client';
import Link from 'next/link';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Button, ConfirmDialog, DataTable, FilterBar, Notice, Pager, Select, TableSearch, TextField, useGranted, type Column } from '@pms/ui';
import { changeDeviceLifecycle, listDevices, saveDevice, transferDevice } from '@/lib/device-actions';
import { DEFAULT_DEVICE_QUERY, DEVICE_TYPES, deviceTypeLabel, type Device, type DeviceQuery } from '@/lib/device-directory';
import { deviceDraft } from '@/lib/device-editor';
import type { Tenant } from '@/lib/tenant-directory';
import { useApiDirectory } from '@/lib/use-api-directory';
import styles from './TenantAdministration.module.css';
import { TenantTaskHeader } from './TenantTaskHeader';
import { TenantTaskReview } from './TenantTaskReview';

type Pending = { kind: 'register' } | { kind: 'transfer' | 'activate' | 'deactivate' | 'retire' | 'rename'; row: Device };
const INITIAL_QUERY: DeviceQuery = { ...DEFAULT_DEVICE_QUERY, limit: 10 };
const EMPTY_PAGE = { items: [], total: 0, has_more: false, next_cursor: null };
export function TenantDevicesPanel({ tenant, onLockChange, onTaskChange }: { tenant: Tenant; onLockChange: (value: boolean) => void; onTaskChange?: (active: boolean) => void }) {
  const granted = useGranted();
  const manage = !tenant.archived_at && granted('platform.organizations.manage');
  const fetchPage = useCallback((query: DeviceQuery, cursor?: string) => tenant.archived_at ? Promise.resolve({ value: EMPTY_PAGE })
    : listDevices('platform', { ...query, organization_id: tenant.id }, cursor), [tenant.id, tenant.archived_at]);
  const directory = useApiDirectory(INITIAL_QUERY, fetchPage);
  const findPage = useCallback((query: DeviceQuery, cursor?: string) => query.q.trim() ? listDevices('platform', { ...query, organization_id: undefined, exclude_organization_id: tenant.id, enrollment_state: 'current' }, cursor) : Promise.resolve({ value: EMPTY_PAGE }), [tenant.id]);
  const candidates = useApiDirectory(INITIAL_QUERY, findPage);
  const [mode, setMode] = useState<'register' | 'transfer'>();
  const panel = useRef<HTMLDivElement>(null);
  const previousMode = useRef<typeof mode>(undefined);
  const [search, setSearch] = useState('');
  const [name, setName] = useState('');
  const [uniqueId, setUniqueId] = useState('');
  const [type, setType] = useState<Device['device_type']>('laptop');
  const [pending, setPending] = useState<Pending>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();
  const mutation = useRef(false);
  useEffect(() => { onLockChange(!!pending || busy); return () => onLockChange(false); }, [pending, busy, onLockChange]);
  useLayoutEffect(() => { onTaskChange?.(!!mode); return () => onTaskChange?.(false); }, [mode, onTaskChange]);
  useEffect(() => {
    if (previousMode.current && !mode) panel.current?.querySelector<HTMLButtonElement>(`[data-device-task="${previousMode.current}"]`)?.focus();
    previousMode.current = mode;
  }, [mode]);
  function ask(value: Pending) { setError(undefined); setPending(value); if (value.kind === 'rename') setName(value.row.name); }
  function openMode(value: typeof mode) { setMode(value); setName(''); setUniqueId(''); setType('laptop'); setSearch(''); candidates.setQuery(INITIAL_QUERY); setPending(undefined); setError(undefined); }
  async function apply() {
    if (!pending || mutation.current) return;
    mutation.current = true; setBusy(true); setError(undefined);
    try {
      const result = pending.kind === 'register' ? await saveDevice('platform', { ...deviceDraft(null), organization_id: tenant.id, name, device_unique_id: uniqueId.trim(), device_type: type, is_active: false })
        : pending.kind === 'transfer' ? await transferDevice('platform', pending.row.id, tenant.id, pending.row.name, false, pending.row.management_etag)
          : pending.kind === 'rename' ? await saveDevice('platform', { ...deviceDraft(pending.row), name }, pending.row.id, pending.row.management_etag)
            : await changeDeviceLifecycle('platform', pending.row.id, pending.kind, pending.row.management_etag);
      if (result.error !== undefined) { setError(result.error); return; }
      setMessage(pending.kind === 'transfer' ? 'Transferred into this tenant as a new inactive registration. The tenant administrator must complete fresh enrollment.'
        : pending.kind === 'register' ? 'Device registered as inactive. The tenant administrator must configure and enroll it before use.'
          : pending.kind === 'retire' ? 'Device registration removed and credentials revoked. Its historical records remain with this tenant.' : 'Device updated.');
      setPending(undefined); openMode(undefined); directory.reload();
    } catch { setError('Unable to confirm this change. Refresh the list before trying again.'); }
    finally { mutation.current = false; setBusy(false); }
  }
  const state = (row: Device) => row.enrollment_state === 'retired' ? 'Removed' : `${row.is_active ? 'Active' : 'Inactive'} · ${row.enrollment_state === 'enrolled' ? 'Enrolled' : 'Awaiting enrollment'}`;
  const identity: Column<Device> = { key: 'name', header: 'Device', type: 'custom', render: row => <div className="pms-console__tenant-cell"><strong>{row.name}</strong><span className="pms-meta">{deviceTypeLabel(row.device_type)}</span></div> };
  const columns: Column<Device>[] = [identity, { key: 'status', header: 'Status', value: state },
    { key: 'actions', header: 'Manage', type: 'custom', align: 'end', render: row => <div className="pms-console__association-actions">
      <Link className="pms-btn pms-btn--ghost" href={'/devices/' + row.id}>View</Link>
      {manage && row.enrollment_state !== 'retired' && <>
        <Button variant="ghost" onClick={() => ask({ kind: 'rename', row })}>Rename</Button>
        <Button variant="ghost" disabled={!row.is_active && !tenant.is_active} onClick={() => ask({ kind: row.is_active ? 'deactivate' : 'activate', row })}>{row.is_active ? 'Deactivate' : 'Activate'}</Button>
        <Button variant="ghost" onClick={() => ask({ kind: 'retire', row })}>Remove</Button>
      </>}
    </div> },
  ];
  const candidateColumns: Column<Device>[] = [identity,
    { key: 'organization', header: 'Current tenant', value: row => row.organization_name ?? row.organization_id },
    { key: 'status', header: 'Status', value: state },
    { key: 'select', header: 'Action', type: 'custom', render: row => <Button variant="ghost" onClick={() => ask({ kind: 'transfer', row })}>Review transfer</Button> },
  ];
  const actionLabel = pending?.kind === 'register' ? 'Register device' : pending?.kind === 'transfer' ? 'Transfer device' : pending?.kind === 'retire' ? 'Remove device' : pending?.kind === 'rename' ? 'Save name' : pending?.kind === 'activate' ? 'Activate device' : 'Deactivate device';
  const reviewingTask = pending?.kind === 'register' || pending?.kind === 'transfer';
  const { query, setQuery, page, loading } = directory;
  return <div className={styles.panel} ref={panel} onKeyDown={event => {
    if (event.key === 'Escape' && reviewingTask && !busy) {
      event.preventDefault(); event.stopPropagation(); setPending(undefined); setError(undefined);
    }
  }}>
    {!mode && <div className={styles.toolbar}>
      <div><h3>Tenant devices</h3><p className="pms-hint">Manage registrations and access. Configuration, enrollment and historical content remain tenant-scoped.</p></div>
      <div className={styles.actions}><Button variant="ghost" disabled={loading || busy} onClick={directory.reload}>Refresh devices</Button>
        {manage && <><Button data-device-task="register" disabled={!tenant.is_active} onClick={() => { setMessage(undefined); openMode('register'); }}>Register device</Button>
          <Button data-device-task="transfer" variant="ghost" disabled={!tenant.is_active} onClick={() => { setMessage(undefined); openMode('transfer'); }}>Transfer device</Button></>}</div>
    </div>}
    {!mode && message && <Notice tone="success" onDismiss={() => setMessage(undefined)}>{message}</Notice>}
    {tenant.archived_at && <p className="pms-hint">Device registrations are unavailable while this tenant is archived.</p>}
    {mode && <TenantTaskHeader title={mode === 'register' ? 'Register device' : 'Transfer device'} backLabel="Back to devices" onBack={() => openMode(undefined)} steps={mode === 'register' ? ['Device details', 'Review'] : ['Find device', 'Review transfer']} step={reviewingTask ? 1 : 0} busy={busy} />}
    {reviewingTask && <TenantTaskReview title={pending.kind === 'register' ? 'Register device?' : 'Transfer device into this tenant?'}
      details={pending.kind === 'register'
        ? [{ label: 'Device', value: name }, { label: 'Device unique ID', value: uniqueId.trim() }, { label: 'Device type', value: deviceTypeLabel(type) }, { label: 'Tenant', value: tenant.name }, { label: 'Initial status', value: 'Inactive · Awaiting enrollment' }]
        : [{ label: 'Device', value: pending.row.name }, { label: 'Device unique ID', value: pending.row.device_unique_id }, { label: 'Device type', value: deviceTypeLabel(pending.row.device_type) }, { label: 'From tenant', value: pending.row.organization_name ?? pending.row.organization_id }, { label: 'To tenant', value: tenant.name }]}
      backLabel={pending.kind === 'register' ? 'Back to details' : 'Back to search'} confirmLabel={actionLabel} busy={busy} error={error} danger={pending.kind === 'transfer'}
      onBack={() => { setPending(undefined); setError(undefined); }} onConfirm={() => void apply()}>
      {pending.kind === 'register' ? <p className="pms-hint">The tenant administrator must configure and enroll this device before it can be used.</p>
        : <Notice tone="warning" title="Transfer requires fresh enrollment"><p>The source registration will be permanently retired and its credentials revoked. This tenant receives a new inactive registration requiring fresh enrollment. Configuration and historical records remain with the source tenant.</p></Notice>}
    </TenantTaskReview>}
    {mode === 'register' && !reviewingTask && <form className={styles.taskForm} onSubmit={event => { event.preventDefault(); if (name.trim() && uniqueId.trim() && uniqueId.trim().length <= 50) ask({ kind: 'register' }); }}>
      <fieldset className={styles.formCard}><legend>New device details</legend>
        <p className="pms-hint">Register a new device for {tenant.name}.</p>
        <div className={styles.fields}>
        <TextField label="Device name" required maxLength={256} value={name} onChange={event => setName(event.target.value)} />
        <TextField label="Device unique ID" required maxLength={50} value={uniqueId} onChange={event => setUniqueId(event.target.value)} hint="Unique across the platform. Cannot be changed after registration." />
        <Select label="Device type" value={type} options={[...DEVICE_TYPES]} onChange={value => setType(value as Device['device_type'])} />
        </div>
        <p className="pms-hint">The registration starts inactive. The tenant administrator completes configuration and enrollment.</p>
        <div className={styles.taskActions}><Button type="submit" disabled={!name.trim() || !uniqueId.trim()}>Review registration</Button></div>
      </fieldset>
    </form>}
    {mode === 'transfer' && !reviewingTask && <fieldset className={`${styles.formCard} ${styles.taskForm}`}><legend>Find a device in another tenant</legend>
      <p className="pms-hint">Search for the device to move to {tenant.name}. Review its current tenant and the transfer details before confirming.</p>
      <form className={styles.fieldAction} onSubmit={event => { event.preventDefault(); candidates.setQuery(current => ({ ...current, q: search.trim() })); }}>
        <TextField label="Device to find" type="search" value={search} maxLength={128} onChange={event => { setSearch(event.target.value); candidates.setQuery(INITIAL_QUERY); }} />
        <Button type="submit" variant="ghost" disabled={!search.trim()} loading={candidates.loading && !!candidates.query.q}>Search devices</Button>
      </form>
      {!!candidates.query.q && <div className={styles.directory}>
        <DataTable caption="Devices available to transfer" columns={candidateColumns} rows={candidates.page.items} rowId={row => row.id} loading={candidates.loading} error={candidates.error ? 500 : undefined} errorDetail={candidates.error} onRetry={candidates.reload} emptyTitle="No matching devices" emptyBody="Search for a current registration belonging to another tenant." />
        <Pager count={candidates.page.items.length} from={candidates.page.from} limit={candidates.query.limit} hasPrevious={candidates.page.page > 0} hasNext={candidates.page.has_more} busy={candidates.loading} noun="device" onPrevious={() => candidates.setPageIndex(candidates.page.page - 1)} onNext={() => candidates.setPageIndex(candidates.page.page + 1)} />
      </div>}
    </fieldset>}
    {!mode && <div className={styles.directory}><FilterBar>
      <TableSearch label="Search tenant devices" value={query.q} onChange={q => setQuery(current => ({ ...current, q }))} maxLength={128} />
      <Select label="Device records" value={query.enrollment_state ?? ''} options={[{ value: 'current', label: 'Current' }, { value: 'retired', label: 'Removed' }, { value: '', label: 'All' }]} onChange={value => setQuery(current => ({ ...current, enrollment_state: (value || undefined) as DeviceQuery['enrollment_state'] }))} />
    </FilterBar>
    <DataTable caption="Tenant devices" columns={columns} rows={page.items} rowId={row => row.id} loading={loading} error={directory.error ? 500 : undefined} errorDetail={directory.error} onRetry={directory.reload} emptyTitle="No matching devices" emptyBody="Change the filter, register a device or transfer one into this tenant." />
    <Pager count={page.items.length} from={page.from} limit={query.limit} hasPrevious={page.page > 0} hasNext={page.has_more} busy={loading || busy} noun="device" onPrevious={() => directory.setPageIndex(page.page - 1)} onNext={() => directory.setPageIndex(page.page + 1)} />
    </div>}
    <ConfirmDialog open={!!pending && !reviewingTask} title={`${actionLabel}?`} confirmLabel={actionLabel} busy={busy} error={error} tone={pending?.kind === 'retire' || pending?.kind === 'deactivate' ? 'danger' : 'default'}
      onCancel={() => { if (!busy) { setPending(undefined); setError(undefined); } }} onConfirm={() => { if (pending?.kind === 'rename' && !name.trim()) setError('Enter a device name.'); else void apply(); }}>
      <p><strong>{pending?.kind === 'register' ? name : pending?.row.name}</strong> · {tenant.name}</p>
      {pending?.kind === 'rename' ? <TextField label="New device name" value={name} required maxLength={256} onChange={event => setName(event.target.value)} disabled={busy} />
        : pending?.kind === 'retire' ? <p>Permanently retire this registration and revoke its credentials. Historical records stay with this tenant. This action cannot be undone.</p>
              : pending?.kind === 'deactivate' ? <p>Suspend device operations in this tenant. The registration and history are retained.</p>
                : <p>Enable device operations, subject to enrollment, configuration and the subscription device limit.</p>}
    </ConfirmDialog>
  </div>;
}
