'use client';
import { BackNavigation } from './BackNavigation';
import { callAction } from '@/lib/call-action';
import Link from 'next/link';
import { useCallback, useState } from 'react';
import {
  Button,
  ConfirmDialog,
  DataTable,
  FilterBar,
  Notice,
  PageHeader,
  Pager,
  Select,
  TableSearch,
  type Column,
} from '@pms/ui';
import { listCatalog, setCatalogActive } from '@/lib/catalog-actions';
import {
  CATALOG_LABELS,
  type CatalogKind,
  type CatalogRecord,
  type CatalogQuery,
} from '@/lib/patient-catalog';
import { useApiDirectory } from '@/lib/use-api-directory';
export function CatalogDirectory({ kind, canManage }: { kind: CatalogKind; canManage: boolean }) {
  const labels = CATALOG_LABELS[kind];
  const fetchPage = useCallback(
    (q: CatalogQuery, cursor?: string) => callAction(() => listCatalog(kind, q, cursor)),
    [kind],
  );
  const { page, query, setQuery, pageIndex, setPageIndex, loading, error, reload } = useApiDirectory(
    { q: '', state: 'all', limit: 25 },
    fetchPage,
  );
  const [changing, setChanging] = useState<CatalogRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();
  const [notice, setNotice] = useState('');
  async function changeState() {
    if (!changing) return;
    setBusy(true);
    setFailure(undefined);
    const result = await callAction(() =>
      setCatalogActive(kind, changing.id, changing.version, !changing.is_active),
    );
    setBusy(false);
    if (result.error !== undefined) {
      setFailure(result.error);
      return;
    }
    setNotice(
      (changing.title ?? changing.name) + ' ' + (changing.is_active ? 'deactivated' : 'activated') + '.',
    );
    setChanging(null);
    reload();
  }
  const columns: Column<CatalogRecord>[] = [
    {
      key: 'name',
      header: kind === 'cases' ? 'Case' : 'Name',
      type: 'custom',
      render: (r) => (
        <div className="pms-console__tenant-cell">
          <Link href={'/catalog/' + kind + '/' + r.id}>{r.title ?? r.name}</Link>
          <span className="pms-meta">{r.code}</span>
        </div>
      ),
    },
    {
      key: 'state',
      header: 'Status',
      type: 'custom',
      render: (r) => (r.is_active ? 'Active' : 'Inactive'),
    },
    {
      key: 'version',
      header: 'Version',
      type: 'custom',
      render: (r) => r.version,
    },
    {
      key: 'actions',
      header: 'Actions',
      type: 'custom',
      align: 'end',
      render: (r) => (
        <div className="pms-console__tenant-actions">
          <Link className="pms-btn pms-btn--ghost" href={'/catalog/' + kind + '/' + r.id}>
            {canManage ? 'Edit' : 'View'}
          </Link>
          {canManage ? (
            <Button
              variant="ghost"
              onClick={() => {
                setFailure(undefined);
                setChanging(r);
              }}
            >
              {r.is_active ? 'Deactivate' : 'Activate'}
            </Button>
          ) : null}
        </div>
      ),
    },
  ];
  return (
    <div className="pms-page pms-console__tenant-page">
      <BackNavigation href="/home" label="Back to home" />
      <PageHeader
        overline="Content catalog"
        title={labels.title}
        lede={labels.description}
        actions={
          canManage ? (
            <Link className="pms-btn pms-btn--primary" href={'/catalog/' + kind + '/new'}>
              Create {labels.singular}
            </Link>
          ) : null
        }
      />
      <div className="pms-console__tenant-directory">
        {notice ? (
          <Notice tone="success" title="Catalog updated" onDismiss={() => setNotice('')}>
            {notice}
          </Notice>
        ) : null}
        {error ? (
          <Notice
            tone="danger"
            title="Could not load catalog"
            action={
              <Button variant="ghost" onClick={reload}>
                Retry
              </Button>
            }
          >
            {error}
          </Notice>
        ) : null}
        <FilterBar>
          <TableSearch
            label={'Search ' + labels.title.toLowerCase()}
            value={query.q}
            onChange={(q) => setQuery({ ...query, q })}
            minLength={1}
            maxLength={128}
          />
          <Select
            label="Status"
            value={query.state}
            options={[
              { value: 'all', label: 'All records' },
              { value: 'active', label: 'Active' },
              { value: 'inactive', label: 'Inactive' },
            ]}
            onChange={(state) => setQuery({ ...query, state })}
          />
        </FilterBar>
        <DataTable
          caption={labels.title}
          rows={error ? [] : page.items}
          columns={columns}
          rowId={(r) => r.id}
          rowLabel={(r) => r.title ?? r.name ?? r.code}
          loading={loading}
          emptyTitle={'No ' + labels.title.toLowerCase() + ' found'}
          emptyBody="Create a record or adjust the search and status filters."
        />
        <Pager
          count={page.items.length}
          from={page.from}
          limit={query.limit}
          hasPrevious={pageIndex > 0}
          hasNext={page.has_more}
          onPrevious={() => setPageIndex(pageIndex - 1)}
          onNext={() => setPageIndex(pageIndex + 1)}
          busy={loading}
          noun={labels.singular}
        />
      </div>
      <ConfirmDialog
        open={!!changing}
        title={
          (changing?.is_active ? 'Deactivate ' : 'Activate ') +
          (changing?.title ?? changing?.name ?? 'record') +
          '?'
        }
        confirmLabel={changing?.is_active ? 'Deactivate' : 'Activate'}
        tone={changing?.is_active ? 'danger' : 'default'}
        busy={busy}
        error={failure}
        onConfirm={() => void changeState()}
        onCancel={() => setChanging(null)}
      >
        {changing?.is_active
          ? 'This removes the record from new practice choices. Saved practice and history remain available.'
          : 'This makes the record available for new practice. Cases must have complete content, an active clinical specialty and an active patient profile.'}
      </ConfirmDialog>
    </div>
  );
}
