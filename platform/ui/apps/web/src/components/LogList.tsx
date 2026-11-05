'use client';
import { BackNavigation } from './BackNavigation';
import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import { Button, CopyIcon, DataTable, ErrorState, FilterBar, PageHeader, Pager, Select, TableSearch, TextField, useFormatters, useToast, type Column, type Sort } from '@pms/ui';
import { CATEGORY_LABELS, defaultLogQuery, LOG_PAGE_LIMITS, type ActivityEvent, type LogCategory, type LogQuery } from '@/lib/log-directory';
import { useLogDirectory } from './LogDirectoryProvider';
import { LogSeverityBadge } from './LogStatusBadge';

const SORT_OPTIONS = [
  { value: 'occurred_at:desc', label: 'Occurred: newest first' }, { value: 'occurred_at:asc', label: 'Occurred: oldest first' },
  { value: 'received_at:desc', label: 'Received: newest first' },
  { value: 'event_type:asc', label: 'Event type A-Z' }, { value: 'event_type:desc', label: 'Event type Z-A' },
];
const ID_PATTERN = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
export function LogList() {
  const { query, setQuery, page, pageIndex, setPageIndex, canRead, user, categories, loading, error, reload } = useLogDirectory();
  const [advanced, setAdvanced] = useState({ organization_id: query.organization_id, device_id: query.device_id, since: query.since, until: query.until });
  const toast = useToast(); const format = useFormatters();
  const platform = user.contextId === 'platform';
  const sort: readonly Sort[] = [{ key: query.sort_by, direction: query.sort_order }];
  const change = (patch: Partial<LogQuery>) => setQuery(current => ({ ...current, ...patch }));
  function changeSort(next: readonly Sort[]) {
    const selected = next[0];
    if (selected && ['occurred_at', 'received_at', 'event_type'].includes(selected.key)) change({ sort_by: selected.key as LogQuery['sort_by'], sort_order: selected.direction });
  }
  function clearFilters() {
    const next = defaultLogQuery(categories[0] ?? 'operational');
    setAdvanced({ organization_id: '', device_id: '', since: '', until: '' }); setQuery(next);
  }
  function apply(event: FormEvent) { event.preventDefault(); change(advanced); }
  async function copyId(row: ActivityEvent) {
    try { await navigator.clipboard.writeText(row.id); toast.success('Log ID copied.'); }
    catch { toast.error('Clipboard unavailable. Open the details to select and copy the ID.'); }
  }
  const columns: Column<ActivityEvent>[] = [
    { key: 'event_type', header: 'Event', type: 'custom', sortable: true, render: row => <div className="pms-console__tenant-cell">
      <Link className="pms-link" href={'/logs/' + row.id}>{row.event_type}</Link>
      <span className="pms-meta">{CATEGORY_LABELS[row.category]} · {row.actor_type}{row.entity_type ? ' · ' + row.entity_type : ''}</span>
    </div> },
    { key: 'severity', header: 'Severity', type: 'custom', render: row => <LogSeverityBadge severity={row.severity} /> },
    { key: 'occurred_at', header: 'Occurred', type: 'custom', sortable: true, defaultSortDirection: 'desc', render: (row, fmt) => <time dateTime={row.occurred_at}>{fmt.dateTime(row.occurred_at)}</time> },
    { key: 'received_at', header: 'Received', type: 'custom', sortable: true, defaultSortDirection: 'desc', render: (row, fmt) => <time dateTime={row.received_at}>{fmt.dateTime(row.received_at)}</time> },
    { key: 'actions', header: 'Details', type: 'custom', render: row => <div className="pms-console__tenant-actions">
      <Link className="pms-btn pms-btn--ghost" href={'/logs/' + row.id} aria-label={'View ' + row.event_type}>View</Link>
      <Button variant="ghost" aria-label={'Copy ID for ' + row.event_type} onClick={() => void copyId(row)}><CopyIcon size={16} /></Button>
    </div> },
  ];
  const filtered = !!(query.q || query.category !== categories[0] || query.severity || query.actor_type || query.since || query.until || query.organization_id || query.device_id);
  if (!canRead) return <div className="pms-page"><BackNavigation href="/home" label="Back to home" /><ErrorState status={403} /></div>;
  return <div className="pms-page">
    <BackNavigation href="/home" label="Back to home" />
    <PageHeader overline={platform ? 'Platform audit' : user.tenant?.name ?? 'Tenant activity'} title="Activity logs"
      lede={platform ? 'Review retained administrative audit across the platform and its tenants.' : 'Review recorded administrative changes and operational events within your access scope.'}
      actions={<Button variant="ghost" disabled={loading} onClick={() => { setQuery(current => ({ ...current })); reload(); }}>Refresh logs</Button>} />
    <FilterBar>
      <TableSearch value={query.q} onChange={q => change({ q })} label="Search logs" placeholder="Event type, entity type or log ID" minLength={1} maxLength={128} />
      <Select label="Category" value={query.category} options={categories.map(value => ({ value, label: CATEGORY_LABELS[value] }))} onChange={value => change({ category: value as LogCategory })} />
      <Select label="Severity" value={query.severity} options={[{ value: '', label: 'All severities' }, { value: 'info', label: 'Info' }, { value: 'warning', label: 'Warning' }, { value: 'error', label: 'Error' }]} onChange={value => change({ severity: value })} />
      <Select label="Actor" value={query.actor_type} options={[{ value: '', label: 'All actors' }, { value: 'user', label: 'User' }, { value: 'device', label: 'Device' }, { value: 'system', label: 'System' }]} onChange={value => change({ actor_type: value })} />
      <Select label="Sort logs" value={query.sort_by + ':' + query.sort_order} options={SORT_OPTIONS} onChange={value => { const [key, direction] = value.split(':'); if (key) changeSort([{ key, direction: direction as Sort['direction'] }]); }} />
    </FilterBar>
    <form onSubmit={apply} className="pms-console__list-filter-form">
      <FilterBar actions={<>
        <Button type="submit" variant="ghost" disabled={loading}>Apply date and ID filters</Button>
        <Button variant="ghost" onClick={clearFilters}>Clear filters</Button>
      </>}>
        <TextField label="Occurred from (UTC)" type="date" value={advanced.since} onChange={e => setAdvanced(current => ({ ...current, since: e.target.value }))} />
        <TextField label="Occurred through (UTC)" type="date" min={advanced.since || undefined} value={advanced.until} onChange={e => setAdvanced(current => ({ ...current, until: e.target.value }))} />
        {platform && <TextField label="Tenant ID" placeholder="All tenants" pattern={ID_PATTERN} maxLength={36} value={advanced.organization_id} onChange={e => setAdvanced(current => ({ ...current, organization_id: e.target.value }))} />}
        <TextField label="Device ID" placeholder="All devices" pattern={ID_PATTERN} maxLength={36} value={advanced.device_id} onChange={e => setAdvanced(current => ({ ...current, device_id: e.target.value }))} />
      </FilterBar>
    </form>
    <DataTable caption="Logs" rows={page.items} columns={columns} rowId={row => row.id} rowLabel={row => row.event_type} sort={sort} onSortChange={changeSort}
      loading={loading} error={error ? 500 : undefined} errorDetail={error} onRetry={() => { setQuery(current => ({ ...current })); reload(); }} filtered={filtered}
      emptyTitle={filtered ? 'No matching logs' : 'No logs recorded yet'} emptyBody={filtered ? 'Change the filters or clear them to see other retained events.' : 'Recorded activity will appear here. Older events may have expired under the retention policy.'} />
    <div className="pms-console__tenant-footer">
      {!loading && !error && <p className="pms-meta" role="status">{format.quantity(String(page.total), { precision: 0 })} {page.total === 1 ? 'log' : 'logs'}</p>}
      <Pager count={page.items.length} from={page.from} limit={query.limit} limitOptions={LOG_PAGE_LIMITS} noun="log" busy={loading || !!error}
        hasPrevious={pageIndex > 0} hasNext={page.has_more} onPrevious={() => setPageIndex(pageIndex - 1)} onNext={() => setPageIndex(pageIndex + 1)} onLimitChange={limit => change({ limit })} />
    </div>
  </div>;
}
