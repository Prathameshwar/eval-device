'use client';
import { BackNavigation } from './BackNavigation';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import {
  Button, ConfirmDialog, CopyIcon, DataTable, EditIcon, ErrorState,
  EyeIcon, FilterBar, Menu, Notice, PageHeader, Pager, PlusIcon, Select, TableSearch,
  TrashIcon, useFormatters, useGranted, useToast,
  type Column, type MenuItem, type Sort,
} from '@pms/ui';
import {
  DEVICE_PAGE_LIMITS,
  DEVICE_TYPES, deviceTypeLabel,
  type Device, type DeviceQuery,
} from '@/lib/device-directory';

import { DeviceEditor } from './DeviceEditor';
import { FleetDeviceEditor } from './FleetDeviceEditor';
import { DeviceStateDialog } from './DeviceStateDialog';
import type { DeviceDraft } from '@/lib/device-editor';
import { useDeviceDirectory } from './DeviceDirectoryProvider';
import { DeviceStatusBadge, DeviceConnectionBadge } from './DeviceStatusBadge';
import { DeviceModelDialog } from './DeviceModelDialog';

const SORT_OPTIONS = [
  { value: 'name:asc', label: 'Name A–Z' },
  { value: 'name:desc', label: 'Name Z–A' },
  { value: 'created_at:desc', label: 'Created newest' },
  { value: 'created_at:asc', label: 'Created oldest' },
  { value: 'last_seen_at:desc', label: 'Last seen newest' },
  { value: 'last_seen_at:asc', label: 'Last seen oldest' },
];

export function DeviceList({ initialConfigureDevice }: { initialConfigureDevice?: string } = {}) {
  const { departments, languages, tenants, associationTargets, platform, scopeName, query, setQuery, setPageIndex, savedDevice, setSavedDevice, page, loading, error: loadError, reload,
    listBookmark, save: saveRecord, retire: retireRecord } = useDeviceDirectory();
  const [changingState, setChangingState] = useState<Device | null>(null);
  const [retiring, setRetiring] = useState<Device | null>(null);
  const [editor, setEditor] = useState<{ device: Device | null } | null>(null);
  const [retireError, setRetireError] = useState<string>();
  const [configuringModel, setConfiguringModel] = useState<string | null>(null);
  const modelFocus = useRef<string | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const granted = useGranted();
  const toast = useToast();
  const format = useFormatters();

  // Permitted to manage if org.devices.manage or platform.organizations.manage
  const canManage = granted(platform ? 'platform.organizations.manage' : 'org.devices.manage');
  const managePermission = platform ? 'platform.organizations.manage' : 'org.devices.manage';

  // Portalled dialogs open after hydration, including when following an old assignment link.
  useEffect(() => { if (initialConfigureDevice) setConfiguringModel(initialConfigureDevice); }, [initialConfigureDevice]);

  function closeModel() {
    modelFocus.current = configuringModel;
    setConfiguringModel(null);
    if (initialConfigureDevice) {
      const url = new URL(window.location.href);
      url.searchParams.delete('configureModel');
      window.history.replaceState(window.history.state, '', url);
    }
  }
  useEffect(() => {
    if (configuringModel || loading || !modelFocus.current) return;
    const id = modelFocus.current;
    const frame = requestAnimationFrame(() => {
      const row = page.items.find(item => item.id === id);
      const buttons = [...(container.current?.querySelectorAll<HTMLButtonElement>('button') ?? [])];
      const button = buttons.find(item => item.dataset.deviceConfigure === id && !item.disabled)
        ?? (row && buttons.find(item => item.getAttribute('aria-label') === `Actions for ${row.name}`));
      (button || container.current?.querySelector<HTMLElement>('[role="region"]'))?.focus({ preventScroll: true });
      modelFocus.current = null;
    });
    return () => cancelAnimationFrame(frame);
  }, [configuringModel, loading, page.items]);

  // Permitted to read if org.devices.summary.read or platform.health.read
  const canRead = granted('org.devices.summary.read') || granted('platform.health.read') || granted('org.devices.read');

  const [busy, setBusy] = useState(false);
  const sort: readonly Sort[] = [{ key: query.sort_by, direction: query.sort_order }];

  function changeQuery(patch: Partial<DeviceQuery>) {
    setQuery((current) => ({ ...current, ...patch }));
    setPageIndex(0);
  }

  function changeSort(next: readonly Sort[]) {
    const selected = next[0];
    if (!selected || !['name', 'created_at', 'last_seen_at'].includes(selected.key)) return;
    changeQuery({ sort_by: selected.key as DeviceQuery['sort_by'], sort_order: selected.direction });
  }

  function openEditor(device: Device | null = null) {
    if (!canManage || (!platform && !device) || device?.enrollment_state === 'retired') return;
    setEditor({ device });
  }

  function focusList(id?: string) {
    requestAnimationFrame(() => {
      const button = id ? [...(container.current?.querySelectorAll<HTMLElement>('[data-device-view]') ?? [])]
        .find((element) => element.dataset.deviceView === id) : undefined;
      (button ?? container.current?.querySelector<HTMLElement>('[role="region"]'))?.focus();
    });
  }

  function rememberList(id: string) {
    listBookmark.current = {
      id, tableTop: container.current?.querySelector('.pms-table-shell')?.scrollTop ?? 0,
      pageTop: container.current?.closest('.pms-main')?.scrollTop ?? 0,
    };
  }

  useEffect(() => {
    const bookmark = listBookmark.current;
    if (!bookmark) return;
    const frame = requestAnimationFrame(() => {
      const button = [...(container.current?.querySelectorAll<HTMLElement>('[data-device-view]') ?? [])]
        .find((element) => element.dataset.deviceView === bookmark.id);
      (button ?? container.current?.querySelector<HTMLElement>('[role="region"]'))?.focus({ preventScroll: true });
      const table = container.current?.querySelector('.pms-table-shell');
      const main = container.current?.closest('.pms-main');
      if (table) table.scrollTop = bookmark.tableTop;
      if (main) main.scrollTop = bookmark.pageTop;
    });
    return () => cancelAnimationFrame(frame);
  }, [listBookmark]);

  async function save(draft: DeviceDraft): Promise<string | undefined> {
    if (!editor) return 'Reopen the form to continue.';
    const result = await saveRecord(draft, editor.device);
    if (!result.device) return result.error;
    setEditor(null);
    focusList(result.device.id);
    return undefined;
  }

  async function copyId(row: Device) {
    try {
      await navigator.clipboard.writeText(row.id);
      toast.success(`Copied the ID for ${row.name}.`, { title: 'Device ID copied' });
    } catch {
      toast.error('Open View to select and copy the device ID manually.', { title: 'Could not copy ID' });
    }
  }

  async function retire() {
    if (!canManage || !retiring || retiring.enrollment_state === 'retired') return;
    if (busy) return;
    setBusy(true);
    const error = await retireRecord(retiring);
    setBusy(false);
    if (error) { setRetireError(error); return; }
    setRetiring(null);
    toast.success(`${retiring.name} was moved to Retired state.`, {
      title: 'Device retired',
    });
    requestAnimationFrame(() => container.current?.querySelector<HTMLElement>('[role="region"]')?.focus());
  }

  function menuItems(row: Device): MenuItem[] {
    const disabledReason = row.enrollment_state === 'retired' ? 'This device is retired.' : undefined;
    return [
      { id: 'edit', label: 'Edit', icon: <EditIcon size={16} />, disabledReason, permission: managePermission },
      ...(platform ? [{ id: 'models', label: 'Configure model', disabledReason: disabledReason ?? (!row.is_active ? 'Activate this device first.' : undefined), permission: managePermission }] : []),
      { id: 'state', label: row.is_active ? 'Deactivate' : 'Activate', disabledReason, permission: managePermission },
      { id: 'copy', label: 'Copy ID', icon: <CopyIcon size={16} /> },
      { id: 'delete', label: 'Retire', icon: <TrashIcon size={16} />, destructive: true, disabledReason, permission: managePermission },
    ];
  }

  const columns: Column<Device>[] = [
    {
      key: 'name', header: 'Device', type: 'custom', sortable: true, width: platform ? '20%' : '25%',
      render: (row) => (
        <div className="pms-console__tenant-cell">
          <strong>{row.name}</strong>
          <span className="pms-meta">{row.device_unique_id}</span>
          <span className="pms-meta">{deviceTypeLabel(row.device_type)}</span>
        </div>
      ),
    },
    {
      key: 'assignment', header: platform ? 'Tenant' : 'Department', type: 'custom', width: platform ? '18%' : '25%',
      render: (row) => (
        <div className="pms-console__tenant-cell">
          {platform ? <>
            <span>{row.organization_name ?? tenants?.[row.organization_id] ?? row.organization_id}</span>
          </> : <>
          <span>{row.department_id ? (row.department_name ?? departments[row.department_id] ?? 'Department unavailable') : 'No department'}</span>
          </>}
        </div>
      ),
    },
    {
      key: 'status', header: 'Enrollment & Connectivity', type: 'custom', width: platform ? '20%' : '22%',
      render: (row) => (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--pms-space-2)', alignItems: 'center' }}>
          <DeviceStatusBadge device={row} />
          <DeviceConnectionBadge device={row} />
          {platform && row.models_configured === false ? <span className="pms-meta">Model required</span> : null}
        </div>
      ),
    },
    {
      key: 'last_seen_at', header: 'Last Seen', type: 'custom', sortable: true, defaultSortDirection: 'desc', width: platform ? '12%' : '13%',
      render: (row, fmt) => row.last_seen_at ? (
        <time dateTime={row.last_seen_at} title={fmt.dateTime(row.last_seen_at)}>
          {fmt.date(row.last_seen_at.slice(0, 10))}
        </time>
      ) : (
        <span className="pms-meta">Never</span>
      ),
    },
    {
      key: 'actions', header: 'Actions', type: 'custom', align: 'end', width: platform ? '30%' : '15%',
      render: (row) => (
        <div className="pms-console__tenant-actions" data-model-required={platform && row.models_configured === false ? 'true' : undefined}>
          <Link className="pms-btn pms-btn--ghost" aria-label={`View ${row.name}`} data-device-view={row.id} href={`/devices/${encodeURIComponent(row.id)}`} onClick={() => rememberList(row.id)}>
            <EyeIcon size={16} />View
          </Link>
          {platform && canManage && row.models_configured === false ? (
            <Button variant="ghost" data-device-configure={row.id} aria-label={`Configure Model for ${row.name}`}
              disabled={!row.is_active || row.enrollment_state === 'retired'}
              title={row.enrollment_state === 'retired' ? 'This device is retired.' : !row.is_active ? 'Activate this device first.' : 'Configure a model so this device can connect and work.'}
              onClick={() => setConfiguringModel(row.id)}>Configure Model</Button>
          ) : null}
          <Menu label={`Actions for ${row.name}`} items={menuItems(row)} onSelect={(action) => {
            if (action === 'copy') void copyId(row);
            if (action === 'edit') openEditor(row);
            if (action === 'models' && platform && canManage && row.is_active && row.enrollment_state !== 'retired') setConfiguringModel(row.id);
            if (action === 'state' && canManage && row.enrollment_state !== 'retired') setChangingState(row);
            if (action === 'delete' && canManage && row.enrollment_state !== 'retired') {
              setRetireError(undefined);
              setRetiring(row);
            }
          }} />
        </div>
      ),
    },
  ];

  const filtered = Boolean(query.q || query.is_active !== undefined || query.device_type !== undefined || query.enrollment_state !== 'current' || query.department_id !== undefined || query.online !== undefined || query.organization_id !== undefined);
  const clearFilters = () => changeQuery({
    q: '', organization_id: undefined, is_active: undefined, device_type: undefined,
    enrollment_state: 'current', department_id: undefined, online: undefined
  });

  if (!canRead) {
    return <div className="pms-page"><BackNavigation href="/home" label="Back to home" /><ErrorState status={403} /></div>;
  }

  return (
    <div className="pms-page pms-console__tenant-page" ref={container}>
      <BackNavigation href="/home" label="Back to home" />
      <PageHeader overline={scopeName} title="Devices" lede="Manage organization device records and monitor connectivity."
        actions={<><Button variant="ghost" disabled={loading} onClick={() => { setQuery(current => ({ ...current })); reload(); }}>Refresh devices</Button>{canManage && platform ? <>
          <Button onClick={() => openEditor()}><PlusIcon size={16} />Create new device</Button>

        </> : null}</>} />

      <div className="pms-console__tenant-directory">
        {savedDevice ? (
          <Notice tone="success" title={savedDevice.created ? 'Device created' : 'Device updated'}
            onDismiss={() => setSavedDevice(null)} action={
              <Link className="pms-btn pms-btn--ghost" href={`/devices/${encodeURIComponent(savedDevice.id)}`} onClick={() => rememberList(savedDevice.id)}>
                <EyeIcon size={16} />View device
              </Link>
            }>
            {savedDevice.name} was {savedDevice.created ? 'created successfully' : 'updated'}.
            {!page.items.some((row) => row.id === savedDevice.id) ? ' It is outside the current filters or page. Use View device to see details.' : ''}
          </Notice>
        ) : null}

        <FilterBar>
          {platform ? <Select label="Tenant" value={query.organization_id ?? ''} options={[{value: '', label: 'All tenants'}, ...Object.entries(tenants ?? {}).map(([value, label]) => ({ value, label }))]} onChange={value => changeQuery({ organization_id: value || undefined })} /> : null}
          <TableSearch value={query.q} onChange={(q) => changeQuery({ q })} label="Search devices" placeholder="Search devices by name or location…" minLength={1} maxLength={128} />

          <Select label="Type" value={query.device_type === undefined ? 'all' : query.device_type} options={[
            { value: 'all', label: 'All types' },
            ...DEVICE_TYPES,
          ]} onChange={(value) => changeQuery({ device_type: value === 'all' ? undefined : value as DeviceQuery['device_type'] })} />

          <Select label="Enrollment" value={query.enrollment_state === undefined ? 'all' : query.enrollment_state} options={[
            { value: 'current', label: 'Current registrations' },
            { value: 'all', label: 'All states' },
            { value: 'pending', label: 'Pending' },
            { value: 'enrolled', label: 'Enrolled' },
            { value: 'retired', label: 'Retired' },
          ]} onChange={(value) => changeQuery({ enrollment_state: value === 'all' ? undefined : value as DeviceQuery['enrollment_state'] })} />

          <Select label="Status" value={query.online === undefined ? 'all' : String(query.online)} options={[
            { value: 'all', label: 'All status' },
            { value: 'true', label: 'Online' },
            { value: 'false', label: 'Offline' },
          ]} onChange={(value) => changeQuery({ online: value === 'all' ? undefined : value === 'true' })} />

          <Select label="Administrative status" value={query.is_active === undefined ? '' : String(query.is_active)} options={[{ value: '', label: 'Active and inactive' }, { value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }]} onChange={value => changeQuery({ is_active: value === '' ? undefined : value === 'true' })} />
          {!platform && Object.keys(departments).length > 0 ? <Select label="Department" value={query.department_id ?? ''} options={[{ value: '', label: 'All departments' }, ...Object.entries(departments).map(([value, label]) => ({ value, label }))]} onChange={value => changeQuery({ department_id: value || undefined })} /> : null}
          <Select label="Sort devices" value={`${query.sort_by}:${query.sort_order}`} options={SORT_OPTIONS} onChange={(value) => {
            const [key, direction] = value.split(':');
            if (key) changeSort([{ key, direction: direction as Sort['direction'] }]);
          }} />
        </FilterBar>

        <DataTable caption="Devices" rows={page.items} loading={loading} error={loadError ? 500 : null} errorDetail={loadError} onRetry={reload} columns={columns} rowId={(row) => row.id} rowLabel={(row) => row.name}
          sort={sort} onSortChange={changeSort} filtered={filtered}
          emptyTitle={filtered ? 'No matching devices' : 'No devices yet'}
          emptyBody={filtered ? 'Try another search query or clear the filters.' : 'Devices will appear here once onboarded.'}
          onClearFilters={clearFilters}
          emptyAction={canManage && platform ? <Button onClick={() => openEditor()}>Create new device</Button> : undefined} />

        <div className="pms-console__tenant-footer">
          <p className="pms-meta" role="status">{format.quantity(String(page.total), { precision: 0 })} {page.total === 1 ? 'device' : 'devices'}</p>
          <Pager count={page.items.length} from={page.from} limit={query.limit} limitOptions={DEVICE_PAGE_LIMITS} noun="device"
            busy={loading || !!loadError} hasPrevious={page.page > 0} hasNext={page.has_more} onPrevious={() => setPageIndex(page.page - 1)} onNext={() => setPageIndex(page.page + 1)}
            onLimitChange={(limit) => changeQuery({ limit })} />
        </div>
      </div>

      {changingState && <DeviceStateDialog key={changingState.id} device={changingState} onClose={() => setChangingState(null)} />}
      {configuringModel && platform && canManage && <DeviceModelDialog key={configuringModel} deviceId={configuringModel} onClose={closeModel}
        onSaved={name => { closeModel(); reload(); toast.success(`${name} will use the saved setup on its next configuration refresh.`, { title: 'Model configuration saved' }); }} />}
      {editor && canManage && platform ? <FleetDeviceEditor device={editor.device} tenants={associationTargets ?? {}} languages={languages ?? {}} onSave={save} onClose={() => setEditor(null)} /> : null}
      {editor && canManage && !platform ? (
        <DeviceEditor device={editor.device} departments={departments} languages={languages} onSave={save} onClose={() => {
          const id = editor.device?.id;
          setEditor(null);
          if (id) focusList(id);
        }} />
      ) : null}

      <ConfirmDialog open={Boolean(retiring)} title={`Retire ${retiring?.name ?? 'device'}?`} confirmLabel="Retire device" tone="danger"
        busy={busy} error={retireError} onConfirm={retire} onCancel={() => setRetiring(null)}>
        This removes the registration from the current fleet by marking it Retired and inactive. The registration cannot be reactivated. Its historical records will be retained, but it can no longer check in.
        Existing device credentials will be revoked.
      </ConfirmDialog>
    </div>
  );
}
