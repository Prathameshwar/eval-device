'use client';
import { BackNavigation } from './BackNavigation';
import { callAction } from '@/lib/call-action';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  Checkbox,
  ConfirmDialog,
  DataTable,
  FilterBar,
  Notice,
  PageHeader,
  Pager,
  Select,
  TableSearch,
  TextField,
  type Column,
} from '@pms/ui';
import {
  listDepartments,
  readDepartment,
  saveDepartment,
  changeDepartmentState,
  type ManagedDepartment,
} from '@/lib/department-actions';
import { useApiDirectory } from '@/lib/use-api-directory';
import { FormTextArea } from './FormTextArea';
export function ManagedDepartments({ contextId, id }: { contextId: string; id?: string }) {
  const router = useRouter();
  const fetchPage = useCallback(
    (q: { q: string; archived: string; limit: number }, cursor?: string) =>
      callAction(() => listDepartments(contextId, q, cursor)),
    [contextId],
  );
  const directory = useApiDirectory({ q: '', archived: 'false', limit: 25 }, fetchPage);
  const [row, setRow] = useState<ManagedDepartment>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState('');
  const [target, setTarget] = useState<ManagedDepartment>();
  const [load, setLoad] = useState(0);
  useEffect(() => {
    if (id || new URLSearchParams(window.location.search).get('saved') !== '1') return;
    setNotice('Department saved.');
    window.history.replaceState(null, '', '/departments');
  }, [id]);
  useEffect(() => {
    let live = true;
    setError(undefined);
    setRow(undefined);
    if (id === 'new')
      setRow({
        id: '',
        name: '',
        description: '',
        is_active: true,
        archived_at: null,
        management_version: 0,
      });
    else if (id)
      void callAction(() => readDepartment(contextId, id)).then((r) => {
        if (!live) return;
        if (r.error !== undefined) setError(r.error);
        else setRow(r.value);
      });
    return () => {
      live = false;
    };
  }, [id, contextId, load]);
  async function save() {
    if (!row) return;
    setBusy(true);
    setError(undefined);
    const result = await callAction(() => saveDepartment(contextId, row));
    setBusy(false);
    if (result.error !== undefined) {
      setError(result.error);
      return;
    }
    directory.reload();
    router.push('/departments?saved=1');
  }
  async function state() {
    if (!target) return;
    setBusy(true);
    setError(undefined);
    const r = await callAction(() => changeDepartmentState(contextId, target));
    setBusy(false);
    if (r.error !== undefined) {
      setError(r.error);
      return;
    }
    setNotice(target.archived_at ? 'Department restored. Enable it when ready.' : 'Department archived.');
    if (row?.id === target.id) setRow(r.value);
    setTarget(undefined);
    directory.reload();
  }
  const actions = (r: ManagedDepartment) => (
    <div className="pms-console__tenant-actions">
      <Link className="pms-btn pms-btn--ghost" href={'/departments/' + r.id}>
        View / edit
      </Link>
      <Button
        variant="ghost"
        onClick={() => {
          setError(undefined);
          setTarget(r);
        }}
      >
        {r.archived_at ? 'Restore' : 'Archive'}
      </Button>
    </div>
  );
  const columns: Column<ManagedDepartment>[] = [
    {
      key: 'name',
      header: 'Department',
      type: 'custom',
      render: (r) => (
        <div className="pms-console__tenant-cell">
          <strong>{r.name}</strong>
          <span className="pms-meta">{r.description}</span>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      type: 'custom',
      render: (r) => (r.archived_at ? 'Archived' : r.is_active ? 'Active' : 'Inactive'),
    },
    { key: 'actions', header: 'Actions', type: 'custom', render: actions },
  ];
  return (
    <div className="pms-page pms-console__tenant-page">
      <BackNavigation href={id ? '/departments' : '/settings'} label={id ? 'Back to departments' : 'Back to settings'} />
      <PageHeader
        overline="Tenant"
        title={id ? (id === 'new' ? 'Create department' : 'Department details') : 'Departments'}
        lede="Manage departments and their availability for tenant members and devices."
        actions={
          !id ? <Link className="pms-btn pms-btn--ghost" href="/departments/new">Create department</Link> : undefined
        }
      />
      {notice ? (
        <Notice tone="success" title="Department updated">
          {notice}
        </Notice>
      ) : null}
      {error || directory.error ? (
        <Notice
          tone="danger"
          title="Request failed"
          action={
            <Button
              variant="ghost"
              onClick={() => {
                setLoad((x) => x + 1);
                directory.reload();
              }}
            >
              Reload
            </Button>
          }
        >
          {error ?? directory.error}
        </Notice>
      ) : null}
      {id ? (
        row ? (
          <Card>
            <CardBody>
              <form
                className="pms-console__tenant-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  void save();
                }}
              >
                <fieldset className="pms-console__tenant-fieldset" disabled={busy || !!row.archived_at}>
                  <legend>Department</legend>
                  <TextField
                    label="Department name"
                    required
                    maxLength={256}
                    value={row.name}
                    onChange={(e) => setRow({ ...row, name: e.target.value })}
                  />
                  <FormTextArea
                    label="Description"
                    maxLength={4000}
                    value={row.description ?? ''}
                    onChange={(e) => setRow({ ...row, description: e.target.value })}
                  />
                  {row.id ? (
                    <Checkbox
                      checked={row.is_active}
                      onChange={(e) => setRow({ ...row, is_active: e.target.checked })}
                    >
                      Active
                    </Checkbox>
                  ) : null}
                  <Button type="submit" loading={busy}>
                    Save department
                  </Button>
                </fieldset>
                {row.archived_at ? (
                  <Button type="button" onClick={() => setTarget(row)}>
                    Restore department
                  </Button>
                ) : null}
              </form>
            </CardBody>
          </Card>
        ) : (
          <p role="status">Loading department…</p>
        )
      ) : (
        <>
          <FilterBar>
            <TableSearch
              label="Search departments"
              value={directory.query.q}
              onChange={(q) => directory.setQuery({ ...directory.query, q })}
              maxLength={128}
            />
            <Select
              label="Lifecycle"
              value={directory.query.archived}
              options={[
                { value: 'false', label: 'Current' },
                { value: 'true', label: 'Archived' },
              ]}
              onChange={(archived) => directory.setQuery({ ...directory.query, archived })}
            />
          </FilterBar>
          <DataTable
            caption="Departments"
            rows={directory.page.items}
            columns={columns}
            rowId={(r) => r.id}
            loading={directory.loading}
            emptyTitle="No departments found"
            emptyBody="Create a department or adjust the filters."
          />
          <Pager
            count={directory.page.items.length}
            from={directory.page.from}
            limit={directory.query.limit}
            hasPrevious={directory.pageIndex > 0}
            hasNext={directory.page.has_more}
            onPrevious={() => directory.setPageIndex(directory.pageIndex - 1)}
            onNext={() => directory.setPageIndex(directory.pageIndex + 1)}
            busy={directory.loading}
          />
        </>
      )}
      <ConfirmDialog
        open={!!target}
        title={(target?.archived_at ? 'Restore ' : 'Archive ') + (target?.name ?? 'department') + '?'}
        confirmLabel={target?.archived_at ? 'Restore' : 'Archive'}
        tone={target?.archived_at ? 'default' : 'danger'}
        busy={busy}
        error={error}
        onCancel={() => {
          setTarget(undefined);
          setError(undefined);
        }}
        onConfirm={() => void state()}
      >
        {target?.archived_at
          ? 'The department will return as inactive. Enable it after reviewing its details.'
          : 'Active members and devices must be reassigned first. Department history is preserved.'}
      </ConfirmDialog>
    </div>
  );
}
