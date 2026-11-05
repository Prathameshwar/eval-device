'use client';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { Button, ConfirmDialog, Drawer, Notice, Select, TextField } from '@pms/ui';
import { MEMBER_ROLES, personDraft, type DepartmentOption, type TenantOption, type Person, type PersonDraft } from '@/lib/people';
import { peopleTenants } from '@/lib/people-actions';
import styles from './PeopleDirectory.module.css';

export function PersonEditor({ platform, row, departments, manageAdministrators, manageTenantAdministrators = false, onSave, onClose }: {
  platform: boolean; row: Person | null; departments: DepartmentOption[]; manageAdministrators: boolean;
  manageTenantAdministrators?: boolean;
  onSave: (draft: PersonDraft) => Promise<string | undefined>; onClose: () => void;
}) {
  const [initial] = useState(() => personDraft(platform, row));
  const [draft, setDraft] = useState(initial);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [tenants, setTenants] = useState<TenantOption[]>([]);
  const [tenantError, setTenantError] = useState<string>();
  const [loadingTenants, setLoadingTenants] = useState(false);
  const [tenantAttempt, setTenantAttempt] = useState(0);
  const creatingTenantAdmin = platform && !row && draft.role === 'org_admin';
  const saving = useRef(false);
  const id = useId();
  const dirty = JSON.stringify(initial) !== JSON.stringify(draft);
  const identityEditable = platform ? draft.auth_method === 'local' : !row;
  const available = departments.filter(d => d.is_active && !d.archived_at);
  useEffect(() => {
    if (!creatingTenantAdmin || !manageTenantAdministrators) return;
    let live = true;
    setLoadingTenants(true); setTenantError(undefined); setTenants([]);
    void peopleTenants().then(result => {
      if (!live) return;
      setTenantError(result.error); setTenants((result.value ?? []).filter(tenant => !tenant.archived_at));
    }).catch(() => { if (live) setTenantError('Unable to load tenants. Please retry.'); })
      .finally(() => { if (live) setLoadingTenants(false); });
    return () => { live = false; };
  }, [creatingTenantAdmin, manageTenantAdministrators, tenantAttempt]);
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);
  const change = <K extends keyof PersonDraft>(key: K, value: PersonDraft[K]) => setDraft(current => ({ ...current, [key]: value }));
  const close = () => { if (!saving.current) { if (dirty) setDiscard(true); else onClose(); } };
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving.current) return;
    if (identityEditable && draft.auth_method === 'local' && !draft.display_name.trim()) { setError('Enter a display name.'); return; }
    if (platform && !row && !['platform_admin', 'org_admin'].includes(draft.role)) { setError('Choose an administrator role.'); return; }
    if (creatingTenantAdmin && (loadingTenants || tenantError || !tenants.some(tenant => tenant.id === draft.organization_id))) { setError('Select an available tenant for this administrator.'); return; }
    if (!platform && draft.department_id && !available.some(d => d.id === draft.department_id)) { setError('Select an active department.'); return; }
    saving.current = true; setBusy(true); setError(undefined);
    try { setError(await onSave(draft)); }
    catch { setError('Unable to save. Please try again.'); }
    finally { saving.current = false; setBusy(false); }
  }
  const title = row ? platform ? 'Edit user' : 'Edit member' : platform ? 'Create user' : 'Invite member';
  return <>
    <Drawer open title={title} onClose={close} busy={busy} footer={<>
      <Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button>
      <Button type="submit" form={id} loading={busy} disabled={busy || creatingTenantAdmin && (loadingTenants || !!tenantError || !tenants.length)}>{row ? 'Save changes' : platform ? 'Create user' : 'Send invitation'}</Button>
    </>}>
      <form id={id} onSubmit={event => void submit(event)} className={styles.editorForm}>
        {error && <Notice tone="danger">{error}</Notice>}
        {!row && <div className={styles.editorIntro}><h3>{platform ? 'Set up an administrator' : 'Welcome someone to your team'}</h3><p>{platform ? 'The recipient chooses their own password using a setup link. If email is unavailable, share the link shown after creation privately.' : 'Choose their role and department below. Access begins after they sign in and accept the invitation. If account setup is needed, a private setup link will be provided.'}</p></div>}
        {!platform && !row && <Select label="Authentication" value={draft.auth_method} options={[{ value: 'local', label: 'Local account' }, { value: 'oidc', label: 'External identity (OIDC)' }]} onChange={value => change('auth_method', value as PersonDraft['auth_method'])} />}
        {(row || draft.auth_method === 'local') && <TextField label="Display name" required={identityEditable && draft.auth_method === 'local'} readOnly={!identityEditable} maxLength={256} value={draft.display_name} onChange={e => change('display_name', e.target.value)} />}
        <TextField label="Email address" type="email" required readOnly={!!row} maxLength={320} value={draft.email} onChange={e => change('email', e.target.value)} />
        {row && <p className="pms-hint">{platform ? 'Email changes require verification through the account settings. External profiles are managed by the identity provider.' : 'Account identity belongs to the user. This page controls their access to this tenant.'}</p>}
        {platform && <TextField label="Phone" readOnly={!identityEditable} maxLength={80} value={draft.phone} onChange={e => change('phone', e.target.value)} />}
        <Select label={platform ? row ? 'Platform role' : 'Administrator role' : 'Member role'} disabled={busy || platform && !!row && !manageAdministrators} value={draft.role}
          required={platform && !row} placeholder={platform && !row ? 'Choose a role' : undefined}
          options={platform ? row ? [{ value: '', label: 'User (no platform access)' }, { value: 'platform_admin', label: 'Platform administrator' }] : [
            ...(manageAdministrators ? [{ value: 'platform_admin', label: 'Platform administrator' }] : []),
            ...(manageTenantAdministrators ? [{ value: 'org_admin', label: 'Tenant administrator' }] : []),
          ] : MEMBER_ROLES}
          onChange={value => setDraft(current => ({ ...current, role: value, organization_id: '', department_id: !platform && value === 'org_admin' ? '' : current.department_id }))} />
        {creatingTenantAdmin ? <>
          <Select label="Tenant" required value={draft.organization_id ?? ''} loading={loadingTenants} disabled={busy || !!tenantError}
            placeholder="Choose a tenant" options={tenants.map(tenant => ({ value: tenant.id, label: tenant.name + (tenant.is_active ? '' : ' (inactive)') }))}
            onChange={value => change('organization_id', value)} hint="Administrator access covers the whole tenant. The recipient must complete password setup and accept the tenant invitation." />
          {tenantError ? <Notice tone="danger">{tenantError} <Button variant="ghost" onClick={() => setTenantAttempt(value => value + 1)}>Retry tenants</Button></Notice> : !loadingTenants && !tenants.length ? <Notice tone="info">Create or restore a tenant before adding its administrator.</Notice> : null}
        </> : null}
        {platform && row?.tenant_admin ? <p className="pms-hint">This account also has a tenant administrator assignment. Manage tenant access from the tenant's administration screen.</p> : null}
        {!platform && <Select label="Department" disabled={draft.role === 'org_admin'} value={draft.department_id}
          options={[{ value: '', label: 'Whole tenant' }, ...available.map(d => ({ value: d.id, label: d.name })),
            ...(draft.department_id && !available.some(d => d.id === draft.department_id) ? [{ value: draft.department_id, label: 'Unavailable department - choose another' }] : [])]}
          onChange={value => change('department_id', value)} />}
        {row && <TextField label="Status reason" maxLength={4000} value={draft.status_reason} onChange={e => change('status_reason', e.target.value)} />}
      </form>
    </Drawer>
    <ConfirmDialog open={discard} title="Discard changes?" confirmLabel="Discard" onCancel={() => setDiscard(false)} onConfirm={onClose}>Your unsaved changes will be lost.</ConfirmDialog>
  </>;
}
