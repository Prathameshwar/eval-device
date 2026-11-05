'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import {
  Button, ConfirmDialog, CopyIcon, DataTable, EditIcon, ErrorState,
  EyeIcon, FilterBar, Menu, Notice, PageHeader, Pager, PlusIcon, Select, TableSearch,
  TrashIcon, useFormatters, useGranted, useToast,
  type Column, type MenuItem, type Sort,
} from '@pms/ui';
import {
  DEPARTMENT_PAGE_LIMITS, departmentPage,
  type Department, type DepartmentQuery,
} from '@/lib/department-directory';

import { DepartmentEditor } from './DepartmentEditor';
import type { DepartmentDraft } from '@/lib/department-editor';
import { useDepartmentDirectory } from './DepartmentDirectoryProvider';
import { DepartmentStatusBadge } from './DepartmentStatusBadge';

const SORT_OPTIONS = [
  { value: 'name:asc', label: 'Name A–Z' },
  { value: 'name:desc', label: 'Name Z–A' },
  { value: 'created_at:desc', label: 'Created newest' },
  { value: 'created_at:asc', label: 'Created oldest' },
];

export function DepartmentList() {
  const { rows, query, setQuery, pageIndex, setPageIndex, savedDepartment, setSavedDepartment,
    listBookmark, save: saveRecord, archive: archiveRecord } = useDepartmentDirectory();
  const [archiving, setArchiving] = useState<Department | null>(null);
  const [editor, setEditor] = useState<{ department: Department | null } | null>(null);
  const [archiveError, setArchiveError] = useState<string>();
  const container = useRef<HTMLDivElement>(null);
  const granted = useGranted();
  const toast = useToast();
  const format = useFormatters();

  // Permitted to manage if org.departments.manage or platform.organizations.manage
  const canManage = granted('org.departments.manage') || granted('platform.organizations.manage');

  const page = departmentPage(rows, query, pageIndex);
  const sort: readonly Sort[] = [{ key: query.sort_by, direction: query.sort_order }];

  function changeQuery(patch: Partial<DepartmentQuery>) {
    setQuery((current) => ({ ...current, ...patch }));
    setPageIndex(0);
  }

  function changeSort(next: readonly Sort[]) {
    const selected = next[0];
    if (!selected || !['name', 'created_at'].includes(selected.key)) return;
    changeQuery({ sort_by: selected.key as DepartmentQuery['sort_by'], sort_order: selected.direction });
  }

  function openEditor(department: Department | null = null) {
    if (!canManage || department?.archived_at) return;
    setEditor({ department });
  }

  function focusList(id?: string) {
    requestAnimationFrame(() => {
      const button = id ? [...(container.current?.querySelectorAll<HTMLElement>('[data-dept-view]') ?? [])]
        .find((element) => element.dataset.deptView === id) : undefined;
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
      const button = [...(container.current?.querySelectorAll<HTMLElement>('[data-dept-view]') ?? [])]
        .find((element) => element.dataset.deptView === bookmark.id);
      (button ?? container.current?.querySelector<HTMLElement>('[role="region"]'))?.focus({ preventScroll: true });
      const table = container.current?.querySelector('.pms-table-shell');
      const main = container.current?.closest('.pms-main');
      if (table) table.scrollTop = bookmark.tableTop;
      if (main) main.scrollTop = bookmark.pageTop;
    });
    return () => cancelAnimationFrame(frame);
  }, [listBookmark]);

  function save(draft: DepartmentDraft): string | undefined {
    if (!editor) return 'Reopen the form to continue.';
    const result = saveRecord(draft, editor.department);
    if (!result.department) return result.error;
    setEditor(null);
    focusList(result.department.id);
    return undefined;
  }

  async function copyId(row: Department) {
    try {
      await navigator.clipboard.writeText(row.id);
      toast.success(`Copied the ID for ${row.name}.`, { title: 'Department ID copied' });
    } catch {
      toast.error('Open View to select and copy the department ID manually.', { title: 'Could not copy ID' });
    }
  }

  function doArchive() {
    if (!canManage || !archiving || archiving.archived_at) return;
    const error = archiveRecord(archiving);
    if (error) { setArchiveError(error); return; }
    setArchiving(null);
    toast.success(`${archiving.name} was archived in the preview.`, {
      title: 'Department archived',
    });
    requestAnimationFrame(() => container.current?.querySelector<HTMLElement>('[role="region"]')?.focus());
  }

  function menuItems(row: Department): MenuItem[] {
    const disabledReason = row.archived_at ? 'This department is archived.' : undefined;
    return [
      { id: 'edit', label: 'Edit', icon: <EditIcon size={16} />, disabledReason, permission: 'org.departments.manage' },
      { id: 'copy', label: 'Copy ID', icon: <CopyIcon size={16} /> },
      { id: 'delete', label: 'Archive', icon: <TrashIcon size={16} />, destructive: true, disabledReason, permission: 'org.departments.manage' },
    ];
  }

  const columns: Column<Department>[] = [
    {
      key: 'name', header: 'Department', type: 'custom', sortable: true, width: '45%',
      render: (row) => (
        <div className="pms-console__tenant-cell">
          <strong>{row.name}</strong>
          <span className="pms-meta" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {row.description || 'No description provided.'}
          </span>
        </div>
      ),
    },
    {
      key: 'status', header: 'Status', type: 'custom', width: '20%',
      render: (row) => <DepartmentStatusBadge department={row} />,
    },
    {
      key: 'created_at', header: 'Created', type: 'custom', sortable: true, defaultSortDirection: 'desc', width: '20%',
      render: (row, fmt) => (
        <time dateTime={row.created_at} title={fmt.dateTime(row.created_at)}>
          {fmt.date(row.created_at.slice(0, 10))}
        </time>
      ),
    },
    {
      key: 'actions', header: 'Actions', type: 'custom', align: 'end', width: '15%',
      render: (row) => (
        <div className="pms-console__tenant-actions">
          <Link className="pms-btn pms-btn--ghost" aria-label={`View ${row.name}`} data-dept-view={row.id} href={`/departments/${encodeURIComponent(row.id)}`} onClick={() => rememberList(row.id)}>
            <EyeIcon size={16} />View
          </Link>
          <Menu label={`Actions for ${row.name}`} items={menuItems(row)} onSelect={(action) => {
            if (action === 'copy') void copyId(row);
            if (action === 'edit') openEditor(row);
            if (action === 'delete' && canManage && !row.archived_at) {
              setArchiveError(undefined);
              setArchiving(row);
            }
          }} />
        </div>
      ),
    },
  ];

  const filtered = rows.length > 0 && Boolean(query.q || query.is_active !== undefined || query.archived !== false);
  const clearFilters = () => changeQuery({ q: '', is_active: undefined, archived: false });

  if (!canManage) {
    return <div className="pms-page"><ErrorState status={403} /></div>;
  }

  return (
    <div className="pms-page pms-console__tenant-page" ref={container}>
      <PageHeader overline="Platform" title="Departments" lede="Manage organization departments and scope practice allocations."
        actions={canManage ? <Button onClick={() => openEditor()}><PlusIcon size={16} />Create new department</Button> : undefined} />
      
      <div className="pms-console__tenant-directory">
        {savedDepartment ? (
          <Notice tone="success" title={savedDepartment.created ? 'Department created' : 'Department updated'}
            onDismiss={() => setSavedDepartment(null)} action={
              <Link className="pms-btn pms-btn--ghost" href={`/departments/${encodeURIComponent(savedDepartment.id)}`} onClick={() => rememberList(savedDepartment.id)}>
                <EyeIcon size={16} />View department
              </Link>
            }>
            {savedDepartment.name} was {savedDepartment.created ? 'created successfully' : 'updated'} in this preview.
            {!page.items.some((row) => row.id === savedDepartment.id) ? ' It is outside the current filters or page. Use View department to see details.' : ''}
          </Notice>
        ) : null}

        <FilterBar>
          <TableSearch value={query.q} onChange={(q) => changeQuery({ q })} label="Search departments" placeholder="Search departments by name or description…" minLength={1} maxLength={128} />
          
          <Select label="Status" inline value={query.is_active === undefined ? 'all' : String(query.is_active)} options={[
            { value: 'all', label: 'All status' },
            { value: 'true', label: 'Active' },
            { value: 'false', label: 'Inactive' },
          ]} onChange={(value) => changeQuery({ is_active: value === 'all' ? undefined : value === 'true' })} />

          <Select label="Lifecycle" inline value={query.archived === undefined ? 'all' : String(query.archived)} options={[
            { value: 'false', label: 'Current' },
            { value: 'true', label: 'Archived' },
            { value: 'all', label: 'All records' },
          ]} onChange={(value) => changeQuery({ archived: value === 'all' ? undefined : value === 'true' })} />

          <Select label="Sort departments" inline value={`${query.sort_by}:${query.sort_order}`} options={SORT_OPTIONS} onChange={(value) => {
            const [key, direction] = value.split(':');
            if (key) changeSort([{ key, direction: direction as Sort['direction'] }]);
          }} />
        </FilterBar>

        <DataTable caption="Departments" rows={page.items} columns={columns} rowId={(row) => row.id} rowLabel={(row) => row.name}
          sort={sort} onSortChange={changeSort} filtered={filtered}
          emptyTitle={filtered ? 'No matching departments' : 'No departments yet'}
          emptyBody={filtered ? 'Try another search query or clear the filters.' : 'Departments will appear here once configured.'}
          onClearFilters={clearFilters}
          emptyAction={canManage ? <Button onClick={() => openEditor()}>Create new department</Button> : undefined} />

        <div className="pms-console__tenant-footer">
          <p className="pms-meta" role="status">{format.quantity(String(page.total), { precision: 0 })} {page.total === 1 ? 'department' : 'departments'}</p>
          <Pager count={page.items.length} from={page.from} limit={query.limit} limitOptions={DEPARTMENT_PAGE_LIMITS} noun="department"
            hasPrevious={page.page > 0} hasNext={page.has_more} onPrevious={() => setPageIndex(page.page - 1)} onNext={() => setPageIndex(page.page + 1)}
            onLimitChange={(limit) => changeQuery({ limit })} />
        </div>
      </div>

      {editor && canManage ? (
        <DepartmentEditor department={editor.department} onSave={save} onClose={() => {
          const id = editor.department?.id;
          setEditor(null);
          if (id) focusList(id);
        }} />
      ) : null}

      <ConfirmDialog open={Boolean(archiving)} title={`Archive ${archiving?.name ?? 'department'}?`} confirmLabel="Archive department" tone="danger"
        error={archiveError} onConfirm={doArchive} onCancel={() => setArchiving(null)}>
        This marks the department as Archived and inactive. Historical simulation contexts remain preserved.
        Changes apply only to this preview and reset when you reload.
      </ConfirmDialog>
    </div>
  );
}
