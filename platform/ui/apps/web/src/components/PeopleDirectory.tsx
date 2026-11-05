'use client';
import { BackNavigation } from './BackNavigation';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Badge, Button, ConfirmDialog, DataTable, Drawer, Menu, Notice, PageHeader, Pager, Select, TextField, EditIcon, FilterIcon, PlusIcon, RefreshIcon, SearchIcon, UploadIcon, UserIcon, type Column, type MenuItem } from '@pms/ui';
import { listPeople, managePerson, peopleDepartments, readPerson, savePerson } from '@/lib/people-actions';
import { MEMBER_ROLES, peopleQuery, personState, platformPersonRole, type DepartmentOption, type PeopleQuery, type Person, type PersonAction, type PersonDraft, type PersonResult } from '@/lib/people';
import { useApiDirectory } from '@/lib/use-api-directory';
import type { SessionUser } from '@/lib/session-user';
import { PersonEditor } from './PersonEditor';
import { MemberCapabilities } from './MemberCapabilities';
import { SettingsBreadcrumbs } from './SettingsBreadcrumbs';
import styles from './PeopleDirectory.module.css';

function MemberStatus({ row }: { row: Person }) {
  const state = personState(row);
  return <Badge tone={state === 'Enabled' ? 'success' : ['Pending', 'Setup pending'].includes(state) ? 'info' : state === 'Expired' ? 'warn' : state === 'Account unavailable' ? 'danger' : 'neutral'}>{state === 'Pending' ? 'Invitation pending' : state}</Badge>;
}

export function PeopleDirectory({ user, memberId }: { user: SessionUser; memberId?: string }) {
  const contextId = user.contextId!;
  const platform = contextId === 'platform';
  const base = platform ? '/users' : '/members';
  const title = platform ? 'Users & administrators' : 'Members';
  const manage = user.permissions.includes(platform ? 'platform.users.manage' : 'org.members.manage');
  const manageAdministrators = user.permissions.includes('platform.administrators.manage');
  const manageTenantAdministrators = user.permissions.includes('platform.organization_admins.manage') && user.permissions.includes('platform.organizations.read');
  const canCreate = manage && (!platform || manageAdministrators || manageTenantAdministrators);
  const fetchPage = useCallback((query: PeopleQuery, cursor?: string) => memberId
    ? Promise.resolve({ value: { items: [], total: 0, next_cursor: null, has_more: false } })
    : listPeople(contextId, query, cursor), [contextId, memberId]);
  const directory = useApiDirectory(peopleQuery(platform), fetchPage);
  const [departments, setDepartments] = useState<DepartmentOption[]>([]);
  const [optionsReady, setOptionsReady] = useState(platform);
  const [optionsError, setOptionsError] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  const [detail, setDetail] = useState<Person>();
  const [detailLoading, setDetailLoading] = useState(!!memberId);
  const [detailError, setDetailError] = useState<string>();
  const [editor, setEditor] = useState<{ row: Person | null }>();
  const [pending, setPending] = useState<{ row: Person; action: PersonAction }>();
  const [delivery, setDelivery] = useState<{ invitationToken?: string; setupToken?: string; email: string }>();
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const active = useRef(false);
  useEffect(() => {
    let live = true;
    if (!platform) void peopleDepartments(contextId).then(result => { if (live) { setOptionsError(result.error); setOptionsReady(!!result.value); setDepartments(result.value ?? []); } })
      .catch(() => { if (live) setOptionsError('Unable to load departments.'); });
    return () => { live = false; };
  }, [contextId, platform, attempt]);
  useEffect(() => {
    if (!memberId) return;
    let live = true; setDetailLoading(true); setDetailError(undefined); setDetail(undefined);
    void readPerson(contextId, memberId).then(result => { if (live) { setDetail(result.value); setDetailError(result.error); } })
      .catch(() => { if (live) setDetailError('Unable to load this record.'); }).finally(() => { if (live) setDetailLoading(false); });
    return () => { live = false; };
  }, [contextId, memberId, attempt]);
  async function perform(work: () => Promise<void>) {
    if (active.current) return;
    active.current = true; setBusy(true); setError(undefined); setMessage(undefined);
    try { await work(); } catch { setError('Unable to complete this action. Refresh and try again.'); }
    finally { active.current = false; setBusy(false); }
  }
  function saved(result: PersonResult, text: string) {
    if (memberId === result.person.id) setDetail(result.person);
    const invitationMessage = result.email_delivered === true ? 'Tenant invitation sent by email.' : result.email_delivered === false ? 'Tenant invitation created. Email was not delivered; share the invitation link securely.' : '';
    setMessage([result.setup_token ? 'Account setup link generated. Share it privately with the recipient.' : result.setup_queued ? 'Account setup email queued.' : '', invitationMessage].filter(Boolean).join(' ') || text);
    if (result.invitation_token || result.setup_token) setDelivery({ invitationToken: result.invitation_token ?? undefined, setupToken: result.setup_token ?? undefined, email: result.person.email });
    directory.reload();
  }
  async function edit(row: Person) {
    await perform(async () => {
      const result = await readPerson(contextId, row.id);
      if (result.error !== undefined) { setError(result.error); return; }
      if (result.value.archived_at || (!platform && !['pending', 'accepted'].includes(result.value.invitation_status ?? ''))) { setError('This record is closed. Refresh the page to see its current status.'); return; }
      setEditor({ row: result.value });
    });
  }
  async function save(draft: PersonDraft) {
    const result = await savePerson(contextId, draft, editor?.row?.id, editor?.row?.management_version);
    if (result.error !== undefined) return result.error;
    setEditor(undefined); saved(result.value, 'Changes saved.');
  }
  async function confirm() {
    if (!pending) return;
    const { row, action } = pending;
    await perform(async () => {
      const result = await managePerson(contextId, row.id, action, row.management_version);
      if (result.error !== undefined) { setError(result.error); return; }
      setPending(undefined); saved(result.value, action === 'restore' ? 'Restored as disabled. Review the record before enabling access.' : 'Change saved.');
    });
  }
  function actions(row: Person) {
    if (!manage || platform && row.platform_role === 'platform_admin' && !manageAdministrators) return null;
    const self = platform ? row.id === user.id : row.user_id === user.id;
    if (!platform && !memberId) {
      const items: MenuItem[] = [];
      const add = (id: PersonAction, label: string) => items.push({ id, label,
        destructive: ['archive', 'disable', 'revoke'].includes(id),
        disabledReason: self && ['disable', 'archive'].includes(id) ? 'You cannot remove your own tenant access.' : undefined });
      if (row.archived_at) { if (row.user_id) add('restore', 'Restore'); }
      else {
        if (row.invitation_status === 'accepted') add(row.is_active ? 'disable' : 'enable', row.is_active ? 'Disable' : 'Enable');
        if (['pending', 'expired'].includes(row.invitation_status ?? '')) { add('resend', 'Resend invitation'); add('revoke', 'Revoke invitation'); }
        add('archive', 'Archive');
      }
      return <div className={styles.rowActions}>
        {!row.archived_at && ['accepted', 'pending'].includes(row.invitation_status ?? '') && <Button variant="ghost" disabled={busy || !optionsReady} onClick={() => void edit(row)}><EditIcon size={15} />Edit</Button>}
        {!!items.length && <Menu label={`Actions for ${row.display_name || row.email}`} items={items} disabled={busy} variant="outline"
          onSelect={action => { setError(undefined); setPending({ row, action: action as PersonAction }); }} />}
      </div>;
    }
    const button = (action: PersonAction, label: string) => <Button key={action} variant="ghost" disabled={busy || self && ['disable', 'archive'].includes(action)} onClick={() => { setError(undefined); setPending({ row, action }); }}>{label}</Button>;
    if (row.archived_at) return platform || row.user_id ? button('restore', 'Restore') : null;
    const accepted = platform || row.invitation_status === 'accepted';
    const inviting = !platform && ['pending', 'expired'].includes(row.invitation_status ?? '');
    return <div className={styles.detailActions}>
      {(accepted || row.invitation_status === 'pending') && <Button variant="ghost" disabled={busy || !optionsReady} onClick={() => void edit(row)}>Edit</Button>}
      {accepted && button(row.is_active ? 'disable' : 'enable', row.is_active ? 'Disable' : 'Enable')}
      {inviting && <>{button('resend', 'Resend invitation')}{button('revoke', 'Revoke invitation')}</>}
      {platform && row.setup_pending && row.is_active && (!row.tenant_admin || user.permissions.includes('platform.organization_admins.manage')) && button('setup', 'Regenerate setup link')}
      {button('archive', 'Archive')}
      {self ? <span className="pms-hint">Your {platform ? 'account' : 'tenant access'}: disabling and archiving are unavailable.</span> : null}
    </div>;
  }
  const columns: Column<Person>[] = [
    { key: 'display_name', header: platform ? 'Person' : 'Member', type: 'custom', render: row => platform ? <Link href={base + '/' + row.id}>{row.display_name || row.email}</Link> : <div className={styles.identity}>
      <span className={styles.avatar} aria-hidden="true">{row.display_name?.trim().split(/\s+/).slice(0, 2).map(word => word[0]).join('').toUpperCase() || <UserIcon size={18} />}</span>
      <div><Link href={base + '/' + row.id}>{row.display_name || row.email}</Link>{row.display_name && <span className={styles.email}>{row.email}</span>}{row.user_id === user.id && <span className={styles.you}>You</span>}</div>
    </div> },
    ...(platform ? [{ key: 'email', header: 'Email' }] : []),
    { key: 'role', header: 'Role', value: row => platform ? platformPersonRole(row) : MEMBER_ROLES.find(r => r.value === row.role)?.label ?? row.role ?? '' },
    ...(!platform ? [{ key: 'department', header: 'Department', value: (row: Person) => row.department_id ? departments.find(d => d.id === row.department_id)?.name ?? 'Unavailable department' : 'Whole tenant' }] : []),
    { key: 'status', header: 'Status', type: 'custom', render: row => <MemberStatus row={row} /> },
    { key: 'actions', header: 'Manage', type: 'custom', render: actions },
  ];
  const { query, setQuery, page, loading } = directory;
  const filter = (key: keyof PeopleQuery, value: string) => setQuery(current => ({ ...current, [key]: value }));
  const filtered = !!(query.q || query.role || query.department_id || query.auth_method || query.state !== 'current');
  const clearFilters = () => setQuery(peopleQuery(platform));
  const label = pending?.action === 'resend' ? 'Resend invitation' : pending?.action === 'revoke' ? 'Revoke invitation' : pending?.action === 'setup' ? 'Regenerate setup link' : pending ? pending.action[0]!.toUpperCase() + pending.action.slice(1) : 'Confirm';
  return <div className={`pms-page ${styles.page}`}>
    {memberId ? <BackNavigation href={base} label={platform ? 'Back to users' : 'Back to members'} />
      : platform ? <SettingsBreadcrumbs title={title} /> : <BackNavigation href="/home" label="Back to home" />}
    <PageHeader overline={platform ? 'Platform' : user.tenant?.name} title={memberId ? detail?.display_name || detail?.email || (platform ? 'User details' : 'Member details') : title}
      lede={memberId ? 'Account and access information.' : platform ? 'Create platform or tenant administrators and manage account access and setup.' : 'Manage your team, invitations and access in one place.'}
      actions={<><Button variant="ghost" disabled={busy || loading || detailLoading} onClick={() => { directory.reload(); setAttempt(n => n + 1); }}><RefreshIcon size={16} />Refresh</Button>
        {!memberId && manage && !platform && <Link className={`pms-btn pms-btn--ghost ${styles.importLink}`} href="/members/import"><UploadIcon size={16} />Import members</Link>}
        {!memberId && canCreate && <Button disabled={busy || !optionsReady} onClick={() => setEditor({ row: null })}><PlusIcon size={17} />{platform ? 'Create user' : 'Invite member'}</Button>}</>} />
    {optionsError && <Notice tone="danger">{optionsError} <Button onClick={() => setAttempt(n => n + 1)}>Retry departments</Button></Notice>}
    {error && !pending && <Notice tone="danger">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
    {memberId ? <>
      {detailLoading && <p role="status">Loading record...</p>}
      {detailError && <Notice tone="danger">{detailError}</Notice>}
      {detail && <><section className={styles.profile} aria-label="Member account">
        <div className={styles.profileHeader}><div><h2>Account & access</h2><p>{detail.email}</p></div><MemberStatus row={detail} /></div>
        {actions(detail)}<dl className={styles.facts}>{[
        ['Email', detail.email], ['Status', personState(detail)], ['Role', platform ? platformPersonRole(detail) : MEMBER_ROLES.find(r => r.value === detail.role)?.label],
        ['Authentication', detail.auth_method ?? detail.user?.auth_method ?? detail.invitation_auth_method ?? 'Not specified'],
        ['Department', platform ? undefined : departments.find(d => d.id === detail.department_id)?.name ?? (detail.department_id ? 'Unavailable' : 'Whole tenant')],
        ['Phone', detail.phone], ['Status reason', detail.status_reason], ['Invitation expires', detail.invitation_expires_at],
        ['Joined', detail.joined_at], ['Created', detail.created_at], ['Updated', detail.updated_at], ['Record ID', detail.id],
      ].filter(([, value]) => value).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{['Invitation expires', 'Joined', 'Created', 'Updated'].includes(name!) && value && !Number.isNaN(Date.parse(value)) ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : value}</dd></div>)}</dl></section>
        {!platform && manage && detail.is_active && !detail.archived_at && detail.invitation_status === 'accepted' && <div className={styles.capabilities}><MemberCapabilities contextId={contextId} memberId={detail.id} role={detail.role} departmentId={detail.department_id} /></div>}</>}
    </> : <>
      <section className={styles.directory} aria-label={platform ? 'User directory' : 'Member directory'}>
      <div className={styles.directoryHeading}><div><h2>{platform ? 'User directory' : 'Member directory'}</h2><p>{platform ? 'Find accounts and review their access.' : 'Find a member by name or email, or narrow the list by role and department.'}</p></div>
        {!platform && manage && <Link className={styles.historyLink} href="/members/import/history">Import history</Link>}
      </div>
      <div className={styles.filters} role="search" aria-label="Filter directory">
        <div className={styles.search}><TextField label="Search people" placeholder="Search by name or email" leading={<SearchIcon size={17} />} type="search" maxLength={128} value={query.q} onChange={e => filter('q', e.target.value)} /></div>
        <Select label="Role filter" value={query.role} options={[{ value: '', label: 'All roles' }, ...(platform ? [{ value: 'platform_admin', label: 'Platform administrators' }, { value: 'tenant_admin', label: 'Tenant administrators' }, { value: 'none', label: 'Users without platform access' }] : MEMBER_ROLES)]} onChange={value => filter('role', value)} />
        <Select label="Status filter" value={query.state} options={[{ value: 'current', label: 'Not archived' }, { value: 'all', label: 'All records' }, { value: 'enabled', label: 'Enabled' }, { value: 'disabled', label: 'Disabled' }, { value: 'archived', label: 'Archived' },
          ...(!platform ? [{ value: 'pending', label: 'Pending invitations' }, { value: 'expired', label: 'Expired invitations' }, { value: 'revoked', label: 'Revoked invitations' }] : [])]} onChange={value => filter('state', value)} />
        {platform ? <Select label="Authentication filter" value={query.auth_method} options={[{ value: '', label: 'All methods' }, { value: 'local', label: 'Local' }, { value: 'oidc', label: 'External (OIDC)' }]} onChange={value => filter('auth_method', value)} />
          : <Select label="Department filter" value={query.department_id} options={[{ value: '', label: 'All departments' }, ...departments.map(d => ({ value: d.id, label: d.name }))]} onChange={value => filter('department_id', value)} />}
      </div>
      <div className={styles.resultsBar}>
        <div className={styles.resultsSummary}><FilterIcon size={16} /><span>{loading ? platform ? 'Loading users…' : 'Loading members…' : directory.error ? 'Directory unavailable' : filtered ? 'Filtered results' : platform ? 'All current users' : 'All current members'}</span>
          {filtered && <Button variant="ghost" onClick={clearFilters}>Clear filters</Button>}</div>
        <div className={styles.sortControls}><Select label="Sort by" inline value={query.sort_by} options={[{ value: platform ? 'display_name' : 'name', label: 'Name' }, { value: 'email', label: 'Email' }, { value: 'created_at', label: 'Created' }, ...(!platform ? [{ value: 'joined_at', label: 'Joined' }] : [])]} onChange={value => filter('sort_by', value)} />
        <Select label="Sort order" hideLabel inline value={query.sort_order} options={[{ value: 'asc', label: 'Ascending' }, { value: 'desc', label: 'Descending' }]} onChange={value => filter('sort_order', value)} /></div>
      </div>
      <DataTable caption={title} columns={columns} rows={page.items} rowId={row => row.id} loading={loading} error={directory.error ? 500 : undefined} errorDetail={directory.error} onRetry={directory.reload}
        filtered={filtered} onClearFilters={clearFilters} emptyTitle={filtered ? 'No matching people' : platform ? 'No users yet' : 'Build your team'} emptyBody={filtered ? 'Try a different search or clear the filters to see more people.' : platform ? 'User accounts will appear here once they are created.' : 'Invite a member or import your team to get started.'}
        emptyAction={canCreate ? <Button disabled={busy || !optionsReady} onClick={() => setEditor({ row: null })}>{platform ? 'Create your first user' : 'Invite your first member'}</Button> : undefined} />
      {!loading && !directory.error && <div className={styles.pagination}><Pager count={page.items.length} from={page.from} limit={query.limit} hasPrevious={directory.pageIndex > 0} hasNext={page.has_more} busy={busy} onPrevious={() => directory.setPageIndex(directory.pageIndex - 1)} onNext={() => directory.setPageIndex(directory.pageIndex + 1)} noun={platform ? 'person' : 'member'} nounPlural={platform ? 'people' : 'members'} /></div>}
      </section>
    </>}
    {editor && <PersonEditor platform={platform} row={editor.row} departments={departments} manageAdministrators={manageAdministrators} manageTenantAdministrators={manageTenantAdministrators} onSave={save} onClose={() => setEditor(undefined)} />}
    <ConfirmDialog open={!!pending} title={`${label}${pending ? ' for ' + (pending.row.display_name || pending.row.email) : ''}?`} confirmLabel={label} busy={busy} error={error}
      tone={['archive', 'disable', 'revoke'].includes(pending?.action ?? '') ? 'danger' : 'default'} onCancel={() => { if (!busy) { setPending(undefined); setError(undefined); } }} onConfirm={() => void confirm()}>
      {pending?.action === 'archive' ? 'This removes access and retains the record and audit history.' : pending?.action === 'restore' ? 'The record returns as disabled. Enable it separately after review.' : pending?.action === 'disable' ? platform ? 'This disables the account across all tenants and revokes its sessions.' : 'This removes access to this tenant.' : pending?.action === 'resend' ? 'The previous invitation link will stop working. A new invitation expires in two days.' : pending?.action === 'revoke' ? 'The invitation link will stop working immediately.' : pending?.action === 'setup' ? 'Previous setup links stop working. Share the new link privately if one is shown.' : 'This allows access within the assigned role and scope.'}
    </ConfirmDialog>
    {delivery && <Drawer open title="Share access links" onClose={() => setDelivery(undefined)} footer={<Button onClick={() => setDelivery(undefined)}>Done</Button>}>
      <p>Share these one-time links privately with {delivery.email}. They are shown only here. Account setup expires at the configured account-action limit; tenant invitations expire in two days.</p>
      {delivery.setupToken && <TextField label="Account setup link" readOnly value={typeof window === 'undefined' ? '' : window.location.origin + '/account/setup#token=' + encodeURIComponent(delivery.setupToken)} onFocus={event => event.target.select()} />}
      {delivery.invitationToken && <TextField label="Invitation link" readOnly value={typeof window === 'undefined' ? '' : window.location.origin + '/invitations/accept#token=' + encodeURIComponent(delivery.invitationToken)} onFocus={event => event.target.select()} />}
      {delivery.setupToken && delivery.invitationToken && <p>The recipient sets a password first, signs in, then accepts the tenant invitation.</p>}
    </Drawer>}
  </div>;
}
