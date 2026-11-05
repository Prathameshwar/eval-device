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
  TENANT_PAGE_LIMITS,
  type Tenant, type TenantQuery,
} from '@/lib/tenant-directory';

import { TenantEditor } from './TenantEditor';
import type { TenantDraft } from '@/lib/tenant-editor';
import { useTenantDirectory } from './TenantDirectoryProvider';
import { TenantStatusBadge } from './TenantStatusBadge';
import { TenantAssociations } from './TenantAssociations';

const SORT_OPTIONS = [
  { value: 'name:asc', label: 'Name A–Z' },
  { value: 'name:desc', label: 'Name Z–A' },
  { value: 'created_at:desc', label: 'Created newest' },
  { value: 'created_at:asc', label: 'Created oldest' },
  { value: 'updated_at:desc', label: 'Updated newest' },
  { value: 'updated_at:asc', label: 'Updated oldest' },
];

export function TenantList() {
  const { rows, plans, activePlans, query, setQuery, setPageIndex, savedTenant, setSavedTenant, page, loading, error: loadError, reload,
    listBookmark, save: saveRecord, archive: archiveRecord } = useTenantDirectory();
  const [deleting, setDeleting] = useState<Tenant | null>(null);
  const [associations, setAssociations] = useState<Tenant | null>(null);
  const [editor, setEditor] = useState<{ tenant: Tenant | null } | null>(null);
  const [deleteError, setDeleteError] = useState<string>();
  const container = useRef<HTMLDivElement>(null);
  const granted = useGranted();
  const toast = useToast();
  const format = useFormatters();
  const canManage = granted('platform.organizations.manage');
  const [busy, setBusy] = useState(false);
  const sort: readonly Sort[] = [{ key: query.sort_by, direction: query.sort_order }];
  const planName = (row: Tenant) => plans[row.subscription_plan_id] ?? 'Plan unavailable';

  function changeQuery(patch: Partial<TenantQuery>) {
    setQuery((current) => ({ ...current, ...patch }));
    setPageIndex(0);
  }

  function changeSort(next: readonly Sort[]) {
    const selected = next[0];
    if (!selected || !['name', 'created_at', 'updated_at'].includes(selected.key)) return;
    changeQuery({ sort_by: selected.key as TenantQuery['sort_by'], sort_order: selected.direction });
  }

  function openEditor(tenant: Tenant | null = null) {
    if (!canManage || tenant?.archived_at) return;
    setEditor({ tenant });
  }

  function focusList(id?: string) {
    requestAnimationFrame(() => {
      const button = id ? [...(container.current?.querySelectorAll<HTMLElement>('[data-tenant-view]') ?? [])]
        .find((element) => element.dataset.tenantView === id) : undefined;
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
      const button = [...(container.current?.querySelectorAll<HTMLElement>('[data-tenant-view]') ?? [])]
        .find((element) => element.dataset.tenantView === bookmark.id);
      (button ?? container.current?.querySelector<HTMLElement>('[role="region"]'))?.focus({ preventScroll: true });
      const table = container.current?.querySelector('.pms-table-shell');
      const main = container.current?.closest('.pms-main');
      if (table) table.scrollTop = bookmark.tableTop;
      if (main) main.scrollTop = bookmark.pageTop;
    });
    return () => cancelAnimationFrame(frame);
  }, [listBookmark]);

  async function save(draft: TenantDraft): Promise<string | undefined> {
    if (!editor) return 'Reopen the form to continue.';
    const result = await saveRecord(draft, editor.tenant);
    if (!result.tenant) return result.error;
    setEditor(null);
    focusList(result.tenant.id);
    return undefined;
  }

  async function copyId(row: Tenant) {
    try {
      await navigator.clipboard.writeText(row.id);
      toast.success(`Copied the ID for ${row.name}.`, { title: 'Tenant ID copied' });
    } catch {
      toast.error('Open View to select and copy the tenant ID manually.', { title: 'Could not copy ID' });
    }
  }

  async function archive() {
    if (!canManage || !deleting || deleting.archived_at) return;
    if (busy) return;
    setBusy(true);
    const error = await archiveRecord(deleting);
    setBusy(false);
    if (error) { setDeleteError(error); return; }
    setDeleting(null);
    toast.success(`${deleting.name} was moved to Archived.`, {
      title: 'Tenant archived',
    });
    // The deleted row's menu may disappear; leave keyboard focus on the remaining table.
    requestAnimationFrame(() => container.current?.querySelector<HTMLElement>('[role="region"]')?.focus());
  }

  function menuItems(row: Tenant): MenuItem[] {
    const disabledReason = row.archived_at ? 'This tenant is archived.' : undefined;
    return [
      { id: 'edit', label: 'Edit', icon: <EditIcon size={16} />, disabledReason, permission: 'platform.organizations.manage' },
      { id: 'copy', label: 'Copy ID', icon: <CopyIcon size={16} /> },
      { id: 'delete', label: 'Delete', icon: <TrashIcon size={16} />, destructive: true, disabledReason, permission: 'platform.organizations.manage' },
    ];
  }

  const columns: Column<Tenant>[] = [
    {
      key: 'name', header: 'Tenant', type: 'custom', sortable: true,
      render: (row) => <strong className="pms-console__tenant-line" title={row.name}>{row.name}</strong>,
    },
    {
      key: 'plan', header: 'Plan', type: 'text', width: '7rem', truncate: true,
      value: planName,
    },
    {
      key: 'contact', header: 'Contact', type: 'text', truncate: true,
      value: (row) => [row.contact_name, row.contact_email].filter(Boolean).join(' · ') || 'No contact added',
    },
    {
      key: 'status', header: 'Status', type: 'custom', width: '7rem',
      render: (row) => <TenantStatusBadge tenant={row} />,
    },
    {
      key: 'created_at', header: 'Created', type: 'custom', sortable: true, defaultSortDirection: 'desc', width: '8rem',
      render: (row, fmt) => <time dateTime={row.created_at} title={fmt.dateTime(row.created_at)}>{fmt.date(row.created_at.slice(0, 10))}</time>,
    },
    {
      key: 'actions', header: 'Actions', type: 'custom', align: 'end', width: '17rem',
      render: (row) => <div className="pms-console__tenant-actions">
        <Link className="pms-btn pms-btn--ghost" aria-label={`View ${row.name}`} data-tenant-view={row.id} href={`/tenants/${encodeURIComponent(row.id)}`} onClick={() => rememberList(row.id)}><EyeIcon size={16} />View</Link>
        {granted('platform.organizations.read') && <Button variant="ghost" aria-label={`Administration for ${row.name}`} aria-haspopup="dialog" onClick={() => setAssociations(row)}>Administration</Button>}
        <Menu label={`Actions for ${row.name}`} items={menuItems(row)} onSelect={(action) => {
          if (action === 'copy') void copyId(row);
          if (action === 'edit') openEditor(row);
          if (action === 'delete' && canManage && !row.archived_at) { setDeleteError(undefined); setDeleting(row); }
        }} />
      </div>,
    },
  ];

  const filtered = Boolean(query.q || query.is_active !== undefined || query.archived !== false);
  const clearFilters = () => changeQuery({ q: '', is_active: undefined, archived: undefined });

  if (!granted('platform.organizations.read')) {
    return <div className="pms-page"><BackNavigation href="/home" label="Back to home" /><ErrorState status={403} /></div>;
  }

  return (
    <div className="pms-page pms-console__tenant-page" ref={container}>
      <BackNavigation href="/home" label="Back to home" />
      <PageHeader overline="Platform" title="Tenants" lede="Manage tenant records and their status."
        actions={canManage ? <Link className="pms-btn pms-btn--primary" href="/tenants/new"><PlusIcon size={16} />Create new tenant</Link> : undefined} />
      <div className="pms-console__tenant-directory">
        {savedTenant ? <Notice tone="success" title={savedTenant.created ? 'Tenant created' : 'Tenant updated'}
          onDismiss={() => setSavedTenant(null)} action={<Link className="pms-btn pms-btn--ghost"
            href={`/tenants/${encodeURIComponent(savedTenant.id)}`} onClick={() => rememberList(savedTenant.id)}><EyeIcon size={16} />View tenant</Link>}>
          {savedTenant.name} was {savedTenant.created ? 'created' : 'updated'}.
          {!page.items.some((row) => row.id === savedTenant.id) ? ' It is outside the current filters or page. Use View tenant to see the saved details.' : ''}
        </Notice> : null}
        <FilterBar>
          <TableSearch value={query.q} onChange={(q) => changeQuery({ q })} label="Search tenants" placeholder="Search tenants by name…" minLength={1} maxLength={128} />
          <Select label="Status" value={query.is_active === undefined ? 'all' : String(query.is_active)} options={[
            { value: 'all', label: 'All statuses' }, { value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' },
          ]} onChange={(value) => changeQuery({ is_active: value === 'all' ? undefined : value === 'true' })} />
          <Select label="Records" value={query.archived === undefined ? 'all' : String(query.archived)} options={[
            { value: 'false', label: 'Current' }, { value: 'true', label: 'Archived' }, { value: 'all', label: 'All records' },
          ]} onChange={(value) => changeQuery({ archived: value === 'all' ? undefined : value === 'true' })} />
          <Select label="Sort tenants" value={`${query.sort_by}:${query.sort_order}`} options={SORT_OPTIONS} onChange={(value) => {
            const [key, direction] = value.split(':');
            if (key) changeSort([{ key, direction: direction as Sort['direction'] }]);
          }} />
        </FilterBar>
        <DataTable caption="Tenants" rows={page.items} loading={loading} error={loadError ? 500 : null} errorDetail={loadError} onRetry={reload} columns={columns} rowId={(row) => row.id} rowLabel={(row) => row.name}
          sort={sort} onSortChange={changeSort} filtered={filtered}
          emptyTitle={filtered ? 'No matching tenants' : 'No tenants yet'}
          emptyBody={filtered ? 'Try another name or change your filters.' : 'Tenant records will appear here once created.'}
          onClearFilters={clearFilters}
          emptyAction={canManage ? <Link className="pms-btn pms-btn--primary" href="/tenants/new"><PlusIcon size={16} />Create new tenant</Link> : undefined} />
        <div className="pms-console__tenant-footer">
          <p className="pms-meta" role="status">{format.quantity(String(page.total), { precision: 0 })} {page.total === 1 ? 'tenant' : 'tenants'}</p>
          <Pager count={page.items.length} from={page.from} limit={query.limit} limitOptions={TENANT_PAGE_LIMITS} noun="tenant"
          hasPrevious={page.page > 0} hasNext={page.has_more} onPrevious={() => setPageIndex(page.page - 1)} onNext={() => setPageIndex(page.page + 1)}
          onLimitChange={(limit) => changeQuery({ limit })} />
        </div>
      </div>
      {editor && canManage ? <TenantEditor tenant={editor.tenant} plans={editor.tenant ? plans : activePlans} onSave={save} onClose={() => {
        const id = editor.tenant?.id;
        setEditor(null);
        if (id) focusList(id);
      }} /> : null}
      {associations && <TenantAssociations key={associations.id} tenant={rows.find(row => row.id === associations.id) ?? associations} onClose={() => setAssociations(null)} />}
      <ConfirmDialog open={Boolean(deleting)} title={`Delete ${deleting?.name ?? 'tenant'}?`} confirmLabel="Delete tenant" tone="danger"
        busy={busy} error={deleteError} onConfirm={archive} onCancel={() => setDeleting(null)}>
        This moves the tenant to Archived and marks it inactive. Its record is retained.
        Existing device access is suspended until the tenant is restored and activated.
      </ConfirmDialog>
    </div>
  );
}
