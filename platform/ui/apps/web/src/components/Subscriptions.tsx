'use client';
import { BackNavigation } from './BackNavigation';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, DataTable, FilterBar, Notice, PageHeader, Pager, Select, TextField, useGranted, type Column } from '@pms/ui';
import { listSubscriptions, readSubscription, saveSubscription, saveSubscriptionPlan, subscriptionHistory, subscriptionPlans } from '@/lib/subscription-actions';
import { DEFAULT_SUBSCRIPTION_QUERY, displayDate, price, type Plan, type Subscription, type SubscriptionEvent, type SubscriptionQuery } from '@/lib/subscriptions';
import { useApiDirectory } from '@/lib/use-api-directory';
import { SubscriptionEditor, SubscriptionPlanEditor } from './SubscriptionEditor';
import { SettingsBreadcrumbs } from './SettingsBreadcrumbs';

function usePlans(contextId: string) {
  const [plans, setPlans] = useState<Plan[]>(); const [error, setError] = useState<string>(); const [revision, setRevision] = useState(0);
  useEffect(() => { let active = true; setError(undefined);
    void subscriptionPlans(contextId).then(result => { if (!active) return; if (result.error !== undefined) setError(result.error); else setPlans(result.value); })
      .catch(() => { if (active) setError('Unable to load plans.'); });
    return () => { active = false; };
  }, [contextId, revision]);
  return { plans, setPlans, error, reload: () => setRevision(v => v + 1) };
}
const tracked = <Notice tone="info" live="off">Manual tracking only: subscription dates and status do not block processing. Plan seat limits remain enforced. No payments are collected.</Notice>;

export function Subscriptions({ contextId }: { contextId: string }) {
  const granted = useGranted(); const catalog = usePlans(contextId); const [editing, setEditing] = useState<Plan>(); const [message, setMessage] = useState<string>();
  const fetch = useCallback((query: SubscriptionQuery, cursor?: string) => listSubscriptions(contextId, query, cursor), [contextId]);
  const directory = useApiDirectory(DEFAULT_SUBSCRIPTION_QUERY, fetch);
  const { query, setQuery, page } = directory;
  const columns: Column<Subscription>[] = [
    { key: 'tenant', header: 'Tenant', type: 'custom', render: row => <Link href={'/licenses/' + row.organization_id}>{row.organization_name}</Link> },
    { key: 'plan', header: 'Plan', value: row => row.plan.name },
    { key: 'state', header: 'Subscription status' },
    { key: 'end', header: 'Ends at', value: row => displayDate(row.ends_at) },
    { key: 'users', header: 'User seats', value: row => row.usage.users + ' / ' + row.plan.max_users },
    { key: 'devices', header: 'Device seats', value: row => row.usage.devices + ' / ' + row.plan.max_devices },
  ];
  return <div className="pms-page">
    <SettingsBreadcrumbs title="Subscriptions" />
    <PageHeader title="Subscriptions" overline="Platform" lede="Manage manual tenant subscriptions, validity dates and plan allowances."
      actions={<Button variant="ghost" onClick={() => { directory.setQuery(current => ({ ...current })); catalog.reload(); }}>Refresh subscriptions</Button>} />
    {tracked}{message && <Notice tone="success">{message}</Notice>}
    <FilterBar actions={<Button variant="ghost" onClick={() => setQuery({ ...DEFAULT_SUBSCRIPTION_QUERY })}>Clear filters</Button>}>
      <div className="pms-table-search"><TextField label="Search tenants" type="search" maxLength={128} value={query.q} onChange={e => setQuery(current => ({ ...current, q: e.target.value }))} /></div>
      <Select label="Subscription status" value={query.state} options={['all', 'active', 'scheduled', 'expired', 'suspended', 'cancelled'].map(value => ({ value, label: value.charAt(0).toUpperCase() + value.slice(1) }))} onChange={state => setQuery(current => ({ ...current, state }))} />
      <Select label="Plan filter" value={query.plan_id} options={[{ value: '', label: 'All plans' }, ...(catalog.plans ?? []).map(p => ({ value: p.id, label: p.name }))]} onChange={plan_id => setQuery(current => ({ ...current, plan_id }))} />
    </FilterBar>
    <DataTable caption="Tenant subscriptions" columns={columns} rows={page.items} rowId={row => row.organization_id} loading={directory.loading}
      error={directory.error ? 500 : undefined} errorDetail={directory.error} onRetry={directory.reload} emptyTitle="No subscriptions found" emptyBody="Change the filters or register a tenant with a subscription plan." />
    <Pager count={page.items.length} from={page.from} limit={query.limit} hasPrevious={directory.pageIndex > 0} hasNext={page.has_more} busy={directory.loading}
      onPrevious={() => directory.setPageIndex(directory.pageIndex - 1)} onNext={() => directory.setPageIndex(directory.pageIndex + 1)} noun="subscription" />
    <h2>Plan catalog</h2>
    {catalog.error && <Notice tone="danger">{catalog.error}<Button variant="ghost" onClick={catalog.reload}>Retry plans</Button></Notice>}
    <div className="pms-grid pms-console__settings-grid">{catalog.plans?.map(plan => <Card key={plan.id}><CardHeader title={plan.name} /><CardBody>
      <p>{price(plan)}</p><p>{plan.max_users} user seats ? {plan.max_devices} device seats</p>
      <p>{plan.is_active ? 'Available for new assignments' : 'Closed to new assignments; existing subscriptions remain assigned'}</p>
      {granted('platform.settings.manage') && <Button variant="ghost" onClick={() => setEditing(plan)}>Edit {plan.name} plan</Button>}
    </CardBody></Card>)}</div>
    {editing && <SubscriptionPlanEditor key={editing.id} plan={editing} onClose={() => setEditing(undefined)} onSave={async draft => {
      const result = await saveSubscriptionPlan(contextId, draft); if (result.error !== undefined) return result.error;
      setEditing(undefined); setMessage('Plan saved. Updated catalog values apply to all assigned tenants.'); catalog.reload(); directory.setQuery(current => ({ ...current }));
    }} />}
  </div>;
}

function SubscriptionHistory({ contextId, organizationId }: { contextId: string; organizationId: string }) {
  const fetch = useCallback((_: { limit: number }, cursor?: string) => subscriptionHistory(contextId, organizationId, cursor), [contextId, organizationId]);
  const history = useApiDirectory({ limit: 25 }, fetch);
  const columns: Column<SubscriptionEvent>[] = [
    { key: 'time', header: 'Changed at', value: row => displayDate(row.occurred_at) },
    { key: 'actor', header: 'Changed by', value: row => row.actor_user_id ?? 'System' },
    { key: 'changes', header: 'Changes', type: 'custom', render: row => <div>{row.details.fields?.map(field => <div key={field}>
      {field.replace('subscription_', '').replaceAll('_', ' ')}{row.details.changes?.[field] ? ': ' + String(row.details.changes[field].before ?? 'not set') + ' ? ' + String(row.details.changes[field].after ?? 'not set') : ''}
    </div>) ?? (row.details.subscription_plan_id ? 'Plan assignment: ' + (row.details.previous_plan_id ?? 'not set') + ' ? ' + row.details.subscription_plan_id : row.event_type)}</div> },
  ];
  return <section><h2>Subscription history</h2><p>Retained manual changes and plan assignments. Internal note contents are excluded. Records follow the tenant audit retention policy.</p>
    <DataTable caption="Subscription history" columns={columns} rows={history.page.items} rowId={row => row.id} loading={history.loading}
      error={history.error ? 500 : undefined} errorDetail={history.error} onRetry={history.reload} emptyTitle="No retained subscription changes" />
    <Pager count={history.page.items.length} from={history.page.from} limit={25} hasPrevious={history.pageIndex > 0} hasNext={history.page.has_more} busy={history.loading}
      onPrevious={() => history.setPageIndex(history.pageIndex - 1)} onNext={() => history.setPageIndex(history.pageIndex + 1)} noun="change" />
  </section>;
}

export function SubscriptionDetails({ contextId, organizationId }: { contextId: string; organizationId: string }) {
  const granted = useGranted(); const platform = contextId === 'platform'; const manage = platform && granted('platform.organizations.manage');
  const catalog = usePlans(contextId); const [row, setRow] = useState<Subscription>(); const [error, setError] = useState<string>(); const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState<Subscription>(); const [pending, setPending] = useState<{ row: Subscription; status: Subscription['status'] }>();
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [message, setMessage] = useState<string>();
  useEffect(() => { let active = true; setError(undefined); setLoading(true);
    void readSubscription(contextId, organizationId).then(result => { if (!active) return; if (result.error !== undefined) setError(result.error); else setRow(result.value); })
      .catch(() => { if (active) setError('Unable to load the subscription.'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [contextId, organizationId, revision]);
  function saved(value: Subscription) { setRow(value); setMessage('Subscription saved. Processing access is unchanged.'); setError(undefined); }
  return <div className="pms-page">
    <BackNavigation href={platform ? '/licenses' : '/settings'} label={platform ? 'Back to subscriptions' : 'Back to settings'} />
    <PageHeader title={row?.organization_name ?? 'Subscription'} lede="Manual subscription details and capacity."
      actions={<Button variant="ghost" disabled={busy || loading} onClick={() => { setRevision(v => v + 1); catalog.reload(); }}>Refresh subscription</Button>} />
    {tracked}
    {error && !pending && <Notice tone="danger">{error}<Button variant="ghost" onClick={() => setRevision(v => v + 1)}>Retry subscription</Button></Notice>}
    {message && <Notice tone="success">{message}</Notice>}
    {loading && <p role="status">Loading subscription?</p>}
    {row && <>
      <Card><CardHeader title={row.plan.name + ' subscription'} /><CardBody>
        <dl className="pms-console__tenant-contact">{[
          ['Status', row.state], ['Starts at', displayDate(row.starts_at)], ['Ends at', displayDate(row.ends_at)],
          ['Plan price', price(row.plan)], ['User seats', row.usage.users + ' / ' + row.plan.max_users + ' (' + row.usage.pending_invitations + ' pending invitations)'],
          ['Device seats', row.usage.devices + ' / ' + row.plan.max_devices], ['Assigned at', displayDate(row.assigned_at)],
          ['Tenant status', row.organization_archived ? 'Archived' : row.organization_is_active ? 'Active' : 'Inactive'],
          ...(platform ? [['Manual reference', row.reference || 'Not set'], ['Internal notes', row.notes || 'Not set']] : []),
        ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd style={{ overflowWrap: 'anywhere' }}>{value}</dd></div>)}</dl>
        {row.over_limit && <Notice tone="warning">Usage exceeds current plan limits. Release seats or assign a larger plan before increasing capacity.</Notice>}
        {!row.plan.is_active && <Notice tone="info">This plan is closed to new assignments. Its existing assignment and seat limits remain in place.</Notice>}
        {manage && !row.organization_archived && <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <Button disabled={busy || loading || !catalog.plans} onClick={() => setEditing(row)}>Edit or renew subscription</Button>
          <Button variant="ghost" disabled={busy || loading} onClick={() => { setError(undefined); setPending({ row, status: row.status === 'active' ? 'suspended' : 'active' }); }}>{row.status === 'active' ? 'Suspend subscription' : 'Resume subscription'}</Button>
          {row.status !== 'cancelled' && <Button variant="danger" disabled={busy || loading} onClick={() => { setError(undefined); setPending({ row, status: 'cancelled' }); }}>Cancel subscription</Button>}
        </div>}
        {!platform && <p>Contact a platform administrator for plan changes, renewal or corrections.</p>}
      </CardBody></Card>
      <SubscriptionHistory key={organizationId + ':' + row.version + ':' + revision} contextId={contextId} organizationId={organizationId} />
    </>}
    {manage && catalog.error && <Notice tone="danger">{catalog.error}<Button onClick={catalog.reload}>Retry plans</Button></Notice>}
    {editing && catalog.plans && <SubscriptionEditor row={editing} plans={catalog.plans} onClose={() => setEditing(undefined)} onSave={async draft => {
      const result = await saveSubscription(contextId, organizationId, editing.version, draft); if (result.error !== undefined) return result.error;
      saved(result.value); setEditing(undefined);
    }} />}
    <ConfirmDialog open={!!pending} title={pending?.status === 'cancelled' ? 'Cancel subscription?' : pending?.status === 'suspended' ? 'Suspend subscription?' : 'Resume subscription?'}
      confirmLabel="Confirm status change" tone={pending?.status === 'active' ? 'default' : 'danger'} busy={busy} error={error}
      onCancel={() => { setPending(undefined); setError(undefined); }} onConfirm={async () => {
        if (!pending || busy) return; setBusy(true); setError(undefined);
        try { const result = await saveSubscription(contextId, organizationId, pending.row.version, { subscription_status: pending.status });
          if (result.error !== undefined) { setError(result.error); return; } saved(result.value); setPending(undefined);
        } catch { setError('Unable to confirm the result. Refresh before retrying.'); } finally { setBusy(false); }
      }}>This changes the recorded status only. Processing and historical data remain available. Resuming retains the existing dates; expired dates must be extended to record a renewal.</ConfirmDialog>
  </div>;
}
