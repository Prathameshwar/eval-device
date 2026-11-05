'use client';
import { BackNavigation } from './BackNavigation';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Button, CalendarIcon, Card, CardBody, CheckCircleIcon, ClockIcon,
  ConfirmDialog, CopyIcon, CustomersIcon, EditIcon, EmptyState, ErrorState,
  isEmailLike, MailIcon, Menu, Notice, PageHeader, PhoneIcon, TrashIcon,
  useFormatters, useGranted, useToast,
} from '@pms/ui';
import { LicenseIcon, TenantIcon } from './icons-product';
import { TenantAdministration } from './TenantAdministration';
import { TenantEditor } from './TenantEditor';
import { useTenantDirectory } from './TenantDirectoryProvider';
import { TenantStatusBadge } from './TenantStatusBadge';
import type { Tenant } from '@/lib/tenant-directory';

function DetailCard({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return <Card>
    <header className="pms-card__header"><div className="pms-card__heading">
      <span className="pms-card__icon" aria-hidden="true">{icon}</span>
      <h2 className="pms-card__title">{title}</h2>
    </div></header>
    <CardBody>{children}</CardBody>
  </Card>;
}

export function TenantDetails({ tenantId, initialTenant }: { tenantId: string; initialTenant?: Tenant }) {
  const { rows, plans, save, archive, savedTenant, setSavedTenant } = useTenantDirectory();
  const tenant = rows.find((row) => row.id === tenantId) ?? initialTenant;
  const granted = useGranted();
  const format = useFormatters();
  const toast = useToast();
  const [editing, setEditing] = useState<Tenant | null>(null);
  const [administrationOpen, setAdministrationOpen] = useState(false);
  const [deleting, setDeleting] = useState<Tenant | null>(null);
  const [deleteError, setDeleteError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const identifier = useRef<HTMLElement>(null);
  const canManage = granted('platform.organizations.manage');

  useEffect(() => {
    const heading = root.current?.querySelector('h1');
    heading?.setAttribute('tabindex', '-1');
    heading?.focus({ preventScroll: true });
    const scroller = root.current?.closest('.pms-main');
    if (scroller) scroller.scrollTop = 0;
    setCopyFailed(false);
  }, [tenantId]);

  const back = <BackNavigation href="/tenants" label="Back to tenants" />;

  if (!granted('platform.organizations.read')) return <div className="pms-page"><BackNavigation href="/home" label="Back to home" /><ErrorState status={403} /></div>;
  if (!tenant) return <div className="pms-page pms-console__tenant-view" ref={root}>
    {back}<PageHeader title="Tenant not available" overline="Platform" />
    <EmptyState icon={<TenantIcon size={28} />} title="This tenant is unavailable"
      body="Return to the directory to choose an available tenant." />
  </div>;

  const canEdit = canManage && !tenant.archived_at;
  const plan = plans[tenant.subscription_plan_id];
  async function copyId() {
    if (!tenant) return;
    try {
      await navigator.clipboard.writeText(tenant.id);
      setCopyFailed(false);
      toast.success('The full tenant ID is ready to paste.', { title: 'Tenant ID copied' });
    } catch {
      setCopyFailed(true);
      identifier.current?.focus();
      const selection = window.getSelection();
      if (identifier.current && selection) {
        const range = document.createRange();
        range.selectNodeContents(identifier.current);
        selection.removeAllRanges(); selection.addRange(range);
      }
    }
  }

  return <div className="pms-page pms-console__tenant-view" ref={root}>
    {back}
    <PageHeader overline="Tenant overview" title={tenant.name} lede="Tenant details, primary contact and record information."
      actions={<>
        <Button variant="ghost" aria-haspopup="dialog" onClick={() => setAdministrationOpen(true)}>Administration</Button>
        {canEdit ? <Button onClick={() => setEditing(tenant)}><EditIcon size={16} />Edit tenant</Button> : null}
        <Menu label="Tenant actions" items={[
          { id: 'copy', label: 'Copy ID', icon: <CopyIcon size={16} /> },
          { id: 'delete', label: 'Delete', icon: <TrashIcon size={16} />, destructive: true,
            permission: 'platform.organizations.manage', disabledReason: tenant.archived_at ? 'This tenant is archived.' : undefined },
        ]} onSelect={(action) => {
          if (action === 'copy') void copyId();
          if (action === 'delete' && canEdit) { setDeleteError(undefined); setDeleting(tenant); }
        }} />
      </>} />
    <div className="pms-console__tenant-overview">
      {tenant.archived_at ? <Notice tone="warning" title="Archived tenant" live="off">
        This record is retained for reference. Editing is unavailable while the tenant is archived.
      </Notice> : null}
      {savedTenant?.id === tenant.id ? <Notice tone="success" title={savedTenant.created ? 'Tenant created' : 'Tenant updated'} onDismiss={() => setSavedTenant(null)}>
        The saved details are shown below.
      </Notice> : null}
      <Card className="pms-console__tenant-summary">
        <dl>
          <div><dt><CheckCircleIcon size={18} />Status</dt><dd><TenantStatusBadge tenant={tenant} /></dd></div>
          <div><dt><LicenseIcon size={18} />Subscription plan</dt><dd>{plan ?? 'Plan unavailable'}</dd></div>
          <div><dt><CalendarIcon size={18} />Created on</dt><dd><time dateTime={tenant.created_at}>{format.date(tenant.created_at.slice(0, 10))}</time></dd></div>
        </dl>
      </Card>
      <div className="pms-console__tenant-view-grid">
        <div className="pms-console__tenant-view-main">
          <DetailCard title="About this tenant" icon={<TenantIcon size={20} />}>
            <p className="pms-console__tenant-description">{tenant.description?.trim() || 'No description has been added yet.'}</p>
          </DetailCard>
          <DetailCard title="Primary contact" icon={<CustomersIcon size={20} />}>
            <dl className="pms-console__tenant-contact">
              <div><dt><CustomersIcon size={16} />Contact name</dt><dd>{tenant.contact_name || 'Not provided'}</dd></div>
              <div><dt><MailIcon size={16} />Email address</dt><dd>
                {tenant.contact_email && isEmailLike(tenant.contact_email)
                  ? <a href={`mailto:${encodeURIComponent(tenant.contact_email)}`}>{tenant.contact_email}</a>
                  : tenant.contact_email || 'Not provided'}
              </dd></div>
              <div><dt><PhoneIcon size={16} />Phone number</dt><dd>{tenant.contact_phone || 'Not provided'}</dd></div>
            </dl>
            {!tenant.contact_name && !tenant.contact_email && !tenant.contact_phone && canEdit
              ? <Button variant="ghost" onClick={() => setEditing(tenant)}><EditIcon size={16} />Add contact details</Button> : null}
            <p className="pms-hint">The primary contact is a point of contact, not an administrator assignment.</p>
          </DetailCard>
        </div>
        <DetailCard title="Record information" icon={<ClockIcon size={20} />}>
          <dl className="pms-console__tenant-record">
            <div><dt>Tenant ID</dt><dd><code ref={identifier} tabIndex={-1}>{tenant.id}</code>
              <Button variant="ghost" onClick={() => void copyId()}><CopyIcon size={16} />Copy ID</Button>
              {copyFailed ? <p role="alert" className="pms-hint">Clipboard access is unavailable. Select and copy the tenant ID above.</p> : null}
            </dd></div>
            <div><dt>Created</dt><dd><time dateTime={tenant.created_at}>{format.dateTime(tenant.created_at)}</time></dd></div>
            <div><dt>Last updated</dt><dd><time dateTime={tenant.updated_at}>{format.dateTime(tenant.updated_at)}</time></dd></div>
            {tenant.archived_at ? <div><dt>Archived</dt><dd><time dateTime={tenant.archived_at}>{format.dateTime(tenant.archived_at)}</time></dd></div> : null}
          </dl>
        </DetailCard>
      </div>
      <div className="pms-console__tenant-view-footer"><span className="pms-meta">Saved tenant record.</span></div>
    </div>
    {administrationOpen ? <TenantAdministration tenant={tenant} onClose={() => setAdministrationOpen(false)} /> : null}
    {editing && canEdit ? <TenantEditor tenant={editing} plans={plans} onClose={() => setEditing(null)} onSave={async (draft) => {
      const result = await save(draft, editing);
      if (!result.tenant) return result.error;
      setEditing(null);
      return undefined;
    }} /> : null}
    <ConfirmDialog open={Boolean(deleting) && canManage} title={`Delete ${tenant.name}?`} confirmLabel="Delete tenant" tone="danger"
      busy={busy} error={deleteError} onCancel={() => setDeleting(null)} onConfirm={async () => {
        if (!deleting) return;
        if (busy) return;
        setBusy(true);
        const error = await archive(deleting);
        setBusy(false);
        if (error) { setDeleteError(error); return; }
        setDeleting(null);
        toast.success('This tenant is archived. Its details remain available.', { title: 'Tenant archived' });
      }}>
      This moves the tenant to Archived and marks it inactive. Its record is retained. Tenant access is suspended.
    </ConfirmDialog>
  </div>;
}
