'use client';

import Link from 'next/link';
import { useEffect, useId, useState } from 'react';
import { Button, ConfirmDialog, Modal, Notice, Select, Tabs, TextField, tabButtonId, useGranted } from '@pms/ui';
import { assignTenantAdministrator, assignTenantPlan, findAdministrators, tenantSupport, type TenantSupport } from '@/lib/tenant-actions';
import type { Tenant } from '@/lib/tenant-directory';
import { useTenantDirectory } from './TenantDirectoryProvider';
import { TenantDevicesPanel } from './TenantDevicesPanel';
import { TenantStatusBadge } from './TenantStatusBadge';
import styles from './TenantAdministration.module.css';

type AdministrationTab = 'subscription' | 'administrators' | 'devices';

export function TenantAdministration({ tenant, onClose, initialTab = 'subscription' }: {
  tenant: Tenant; onClose: () => void; initialTab?: AdministrationTab;
}) {
  const { activePlans, plans, archive, remember } = useTenantDirectory();
  const granted = useGranted();
  const panelId = useId();
  const canViewDevices = granted('platform.health.read');
  const [tab, setTab] = useState<AdministrationTab>(() =>
    initialTab === 'devices' && !canViewDevices ? 'subscription' : initialTab);
  const [panelLocked, setPanelLocked] = useState(false);
  const [taskActive, setTaskActive] = useState(false);
  const [support, setSupport] = useState<TenantSupport>();
  const [loadError, setLoadError] = useState<string>();
  const [actionError, setActionError] = useState<string>();
  const [searchError, setSearchError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [revision, setRevision] = useState(0);
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState<{ id: string; display_name: string; email: string }[]>([]);
  const [userId, setUserId] = useState('');
  const [planId, setPlanId] = useState(tenant.subscription_plan_id);
  const [confirm, setConfirm] = useState<'restore' | 'plan' | 'admin'>();
  const [message, setMessage] = useState('');
  const administrators = support?.administrators.items ?? [];
  const selectedUser = users.find(user => user.id === userId);
  const canManage = granted('platform.organizations.manage');
  const canAssign = granted('platform.organization_admins.manage') && granted('platform.users.read');
  const locked = busy || !!confirm || panelLocked;

  useEffect(() => { setPlanId(tenant.subscription_plan_id); }, [tenant.subscription_plan_id]);
  useEffect(() => {
    if (tab !== 'subscription' && tab !== 'administrators') return;
    let active = true;
    setSupport(undefined);
    setLoadError(undefined);
    void tenantSupport(tenant.id).then(result => {
      if (!active) return;
      if (result.error !== undefined) setLoadError(result.error);
      else setSupport(result.value);
    }).catch(() => { if (active) setLoadError('Unable to load tenant administration.'); });
    return () => { active = false; };
  }, [tenant.id, tenant.management_version, revision, tab]);

  function resetSearch() {
    setUsers([]);
    setUserId('');
    setSearched(false);
    setSearchError(undefined);
  }

  async function search() {
    if (searching || busy || !query.trim()) return;
    resetSearch();
    setSearching(true);
    try {
      const result = await findAdministrators(query.trim());
      if (result.error !== undefined) setSearchError(result.error);
      else { setUsers(result.value); setSearched(true); }
    } catch { setSearchError('Unable to search accounts. Please try again.'); }
    finally { setSearching(false); }
  }

  function ask(action: 'restore' | 'plan' | 'admin') {
    setActionError(undefined);
    setMessage('');
    setConfirm(action);
  }

  async function apply() {
    if (busy || !confirm) return;
    setBusy(true);
    setActionError(undefined);
    try {
      if (confirm === 'restore') {
        const failure = await archive(tenant, true);
        if (failure) { setActionError(failure); return; }
        setMessage('Tenant restored as inactive. Review its administrators before activating it from Edit tenant.');
      } else if (confirm === 'plan') {
        const result = await assignTenantPlan(tenant.id, planId, tenant.management_version);
        if (result.error !== undefined) { setActionError(result.error); return; }
        remember(result.value);
        setMessage('Subscription plan updated.');
      } else {
        if (!selectedUser) return;
        const result = await assignTenantAdministrator(tenant.id, selectedUser.id);
        if (result.error !== undefined) { setActionError(result.error); return; }
        setRevision(value => value + 1);
        setMessage('Administrator assigned.');
        setQuery('');
        resetSearch();
      }
      setConfirm(undefined);
    } catch { setActionError('Unable to complete this request. Refresh to check its status before trying again.'); }
    finally { setBusy(false); }
  }

  return <>
    <Modal open title="Tenant administration" size="lg" onClose={onClose} busy={locked}
      footer={taskActive ? undefined : <Button variant="ghost" onClick={onClose} disabled={locked}>Done</Button>}>
      <div className={styles.shell} data-task-active={taskActive || undefined}>
        <div className={styles.identity}><h3>{tenant.name}</h3><TenantStatusBadge tenant={tenant} /></div>
        {message ? <Notice tone="success" onDismiss={() => setMessage('')}>{message}</Notice> : null}
        {tenant.archived_at ? <Notice tone="warning" title="Archived tenant">
          <p>Restore this tenant to change its plan, administrators or devices.</p>
          {canManage ? <Button onClick={() => ask('restore')}>Restore tenant</Button> : null}
        </Notice> : !tenant.is_active ? <Notice tone="info">This tenant is inactive. Assign an administrator, then activate it from Edit tenant before adding devices.</Notice> : null}
        <div className={styles.navigation} hidden={taskActive}><Tabs label="Tenant administration sections" active={tab} panelId={panelId}
          onChange={value => { if (!locked) setTab(value as AdministrationTab); }}
          tabs={[{ id: 'subscription', label: 'Subscription' }, { id: 'administrators', label: 'Administrators' },
            ...(canViewDevices ? [{ id: 'devices', label: 'Devices' }] : [])]} /></div>
        <div id={panelId} role="tabpanel" aria-labelledby={tabButtonId(tab, panelId)} tabIndex={0} className={styles.panel}>
          {tab === 'devices' && canViewDevices ? <TenantDevicesPanel key={tenant.id} tenant={tenant} onLockChange={setPanelLocked} onTaskChange={setTaskActive} />
              : loadError ? <Notice tone="danger" title="Unable to load details">
            <p>{loadError}</p><Button variant="ghost" onClick={() => setRevision(value => value + 1)}>Retry</Button>
          </Notice> : !support ? <p role="status">Loading tenant administration…</p> : tab === 'subscription' ? <>
            <div className={styles.columns}>
            <section className={styles.card}>
              <h3>Current plan: {support.subscription.plan.name}</h3>
              <p className="pms-hint">The plan sets how many users and devices this tenant can have.</p>
              <dl className={styles.usage}>
                <div><dt>Users</dt><dd><strong>{support.subscription.usage.users}</strong> used<span>{support.subscription.remaining.users} available</span></dd></div>
                <div><dt>Devices</dt><dd><strong>{support.subscription.usage.devices}</strong> used<span>{support.subscription.remaining.devices} available</span></dd></div>
              </dl>
              {support.subscription.over_limit ? <Notice tone="warning">Current usage exceeds the plan limits. Choose a suitable plan or reduce usage.</Notice> : null}
            </section>
            {!tenant.archived_at && canManage ? <fieldset className={styles.formCard} disabled={busy}>
              <legend>Change plan</legend>
              <Select label="New subscription plan" value={planId}
                options={Object.entries(activePlans).map(([value, label]) => ({ value, label }))}
                onChange={setPlanId} hint="A change is allowed only when the new plan supports this tenant's current usage." />
              <div className={styles.actions}>
                <Button disabled={planId === tenant.subscription_plan_id || !activePlans[planId]} onClick={() => ask('plan')}>Change plan</Button>
              </div>
            </fieldset> : null}
            </div>
            <section className={`${styles.card} ${styles.linkCard}`}>
              <div><h3>Subscription dates and status</h3>
              <p className="pms-hint">Manage the subscription period, renewals and status on the subscription page.</p>
              </div>
              <Link href={'/licenses/' + tenant.id} className="pms-btn pms-btn--ghost">Manage subscription dates and status</Link>
            </section>
          </> : <>
            <div className={styles.columns}>
            <section className={styles.card}>
              <h3>Current administrators</h3>
              <p className="pms-hint">These accounts have active administrator access to this tenant.</p>
              {administrators.length ? <ul className={styles.adminList}>
                {administrators.map(user => <li key={user.id}><span className={styles.avatar} aria-hidden="true">{user.display_name.slice(0, 1).toUpperCase()}</span><div><strong>{user.display_name}</strong><span>{user.email}</span></div></li>)}
              </ul> : <p className={styles.empty}>No active administrators assigned.</p>}
            </section>
            {!tenant.archived_at && canAssign ? <form onSubmit={event => { event.preventDefault(); void search(); }}>
              <fieldset className={styles.formCard} disabled={busy || searching}>
                <legend>Add tenant administrator</legend>
                <p className="pms-hint">Choose an existing user account to give it administrator access to this tenant. The account must be active and its setup complete.</p>
                <div className={styles.fieldAction}><TextField label="Account name or email" value={query} maxLength={128}
                  onChange={event => { setQuery(event.target.value); resetSearch(); }} />
                  <Button type="submit" variant="ghost" disabled={!query.trim()} loading={searching} loadingLabel="Searching accounts…">Search accounts</Button>
                </div>
                {searchError ? <Notice tone="danger">{searchError}</Notice> : null}
                {searched && !users.length ? <p role="status">No active accounts match. Try another name or email.</p> : null}
                {users.length ? <>
                  <Select label="Account to assign" value={userId} placeholder="Choose an account" options={users.map(user => ({
                    value: user.id,
                    label: user.display_name + ' — ' + user.email + (administrators.some(admin => admin.id === user.id) ? ' (already an administrator)' : ''),
                    disabled: administrators.some(admin => admin.id === user.id),
                  }))} onChange={setUserId} hint="Up to 25 matches are shown. Refine your search if the account is missing." />
                  <div className={styles.actions}>
                    <Button disabled={!selectedUser} onClick={() => ask('admin')}>Assign administrator</Button>
                  </div>
                </> : null}
              </fieldset>
            </form> : null}
            </div>
          </>}
        </div>
      </div>
    </Modal>
    <ConfirmDialog open={!!confirm} title={confirm === 'restore' ? 'Restore this tenant?' : confirm === 'plan' ? 'Change subscription plan?' : 'Assign tenant administrator?'}
      confirmLabel={confirm === 'restore' ? 'Restore tenant' : confirm === 'plan' ? 'Change plan' : 'Assign administrator'}
      busy={busy} error={actionError} onConfirm={() => void apply()} onCancel={() => setConfirm(undefined)}>
      {confirm === 'restore' ? <p>{tenant.name} will return as inactive.</p> : confirm === 'plan' ?
        <p>Change {tenant.name} from {plans[tenant.subscription_plan_id] ?? 'its current plan'} to {activePlans[planId]}? Current usage must fit within the new plan limits.</p> : <>
          <p>Give {selectedUser?.display_name} ({selectedUser?.email}) administrator access to {tenant.name}?</p>
          <p>If this account is already a member, its current role is replaced with tenant administrator and its access covers the whole tenant.</p>
        </>}
    </ConfirmDialog>
  </>;
}
