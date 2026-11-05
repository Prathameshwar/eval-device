'use client';

import Link from 'next/link';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Button, CalendarIcon, Card, CardBody, CheckCircleIcon, ChevronLeftIcon, ChevronRightIcon, ClockIcon,
  ConfirmDialog, CopyIcon, EditIcon, EmptyState, ErrorState,
  Menu, Notice, PageHeader, TrashIcon,
  useFormatters, useGranted, useToast,
} from '@pms/ui';
import { TenantIcon } from './icons-product';
import { DepartmentEditor } from './DepartmentEditor';
import { useDepartmentDirectory } from './DepartmentDirectoryProvider';
import { DepartmentStatusBadge } from './DepartmentStatusBadge';
import type { Department } from '@/lib/department-directory';

function DetailCard({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <Card>
      <header className="pms-card__header">
        <div className="pms-card__heading">
          <span className="pms-card__icon" aria-hidden="true">{icon}</span>
          <h2 className="pms-card__title">{title}</h2>
        </div>
      </header>
      <CardBody>{children}</CardBody>
    </Card>
  );
}

export function DepartmentDetails({ departmentId }: { departmentId: string }) {
  const { rows, save, archive, savedDepartment, setSavedDepartment } = useDepartmentDirectory();
  const department = rows.find((row) => row.id === departmentId);
  const granted = useGranted();
  const format = useFormatters();
  const toast = useToast();
  
  const [editing, setEditing] = useState<Department | null>(null);
  const [archiving, setArchiving] = useState<Department | null>(null);
  const [archiveError, setArchiveError] = useState<string>();
  const [copyFailed, setCopyFailed] = useState(false);
  
  const root = useRef<HTMLDivElement>(null);
  const identifier = useRef<HTMLElement>(null);

  const canManage = granted('org.departments.manage') || granted('platform.organizations.manage');

  useEffect(() => {
    const heading = root.current?.querySelector('h1');
    heading?.setAttribute('tabindex', '-1');
    heading?.focus({ preventScroll: true });
    const scroller = root.current?.closest('.pms-main');
    if (scroller) scroller.scrollTop = 0;
    setCopyFailed(false);
  }, [departmentId]);

  const back = <Link href="/departments" className="pms-btn pms-btn--ghost"><ChevronLeftIcon size={16} />Back to departments</Link>;
  const breadcrumb = (
    <nav aria-label="Breadcrumb" className="pms-console__breadcrumbs">
      <ol>
        <li><Link href="/departments" className="pms-console__back-link"><ChevronLeftIcon size={16} />Back to departments</Link></li>
        <li><ChevronRightIcon size={14} /><span aria-current="page">Department details</span></li>
      </ol>
    </nav>
  );

  if (!canManage) return <div className="pms-page"><ErrorState status={403} /></div>;
  
  if (!department) return (
    <div className="pms-page pms-console__tenant-view" ref={root}>
      {breadcrumb}
      <PageHeader title="Department not available" overline="Platform" />
      <EmptyState icon={<TenantIcon size={28} />} title="This department is not in the current preview"
        body="A department created in another tab, or before a reload, is not retained. Return to the directory to choose an available department." action={back} />
    </div>
  );

  const canEdit = canManage && !department.archived_at;

  async function copyId() {
    if (!department) return;
    try {
      await navigator.clipboard.writeText(department.id);
      setCopyFailed(false);
      toast.success('The full department ID is ready to paste.', { title: 'Department ID copied' });
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

  return (
    <div className="pms-page pms-console__tenant-view" ref={root}>
      {breadcrumb}
      
      <PageHeader overline="Department overview" title={department.name} lede="Department specifications, descriptions, and system record information."
        actions={<>
          {canEdit ? <Button onClick={() => setEditing(department)}><EditIcon size={16} />Edit department</Button> : null}
          <Menu label="Department actions" items={[
            { id: 'copy', label: 'Copy ID', icon: <CopyIcon size={16} /> },
            { id: 'delete', label: 'Archive', icon: <TrashIcon size={16} />, destructive: true,
              permission: 'org.departments.manage', disabledReason: department.archived_at ? 'This department is archived.' : undefined },
          ]} onSelect={(action) => {
            if (action === 'copy') void copyId();
            if (action === 'delete' && canEdit) { setArchiveError(undefined); setArchiving(department); }
          }} />
        </>} />

      <div className="pms-console__tenant-overview">
        {department.archived_at ? (
          <Notice tone="warning" title="Archived department" live="off">
            This department is archived. Editing is unavailable while the department is in an archived state.
          </Notice>
        ) : null}

        {savedDepartment?.id === department.id ? (
          <Notice tone="success" title={savedDepartment.created ? 'Department created' : 'Department updated'} onDismiss={() => setSavedDepartment(null)}>
            The saved details are shown below. Changes apply to this preview only.
          </Notice>
        ) : null}

        <Card className="pms-console__tenant-summary">
          <dl style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
            <div>
              <dt><CheckCircleIcon size={18} />Status</dt>
              <dd><DepartmentStatusBadge department={department} /></dd>
            </div>
            <div>
              <dt><CalendarIcon size={18} />Created on</dt>
              <dd><time dateTime={department.created_at}>{format.date(department.created_at.slice(0, 10))}</time></dd>
            </div>
            <div>
              <dt><ClockIcon size={18} />Last updated</dt>
              <dd><time dateTime={department.updated_at}>{format.dateTime(department.updated_at)}</time></dd>
            </div>
            <div>
              <dt><ClockIcon size={18} />Archived</dt>
              <dd>{department.archived_at ? <time dateTime={department.archived_at}>{format.dateTime(department.archived_at)}</time> : 'Active'}</dd>
            </div>
          </dl>
        </Card>

        {!department.is_active && department.status_reason ? (
          <Notice tone="info" title="Reason for inactive status" live="off">
            {department.status_reason}
          </Notice>
        ) : null}

        <div className="pms-console__tenant-view-grid">
          <div className="pms-console__tenant-view-main">
            <DetailCard title="About this department" icon={<TenantIcon size={20} />}>
              <p className="pms-console__tenant-description">{department.description?.trim() || 'No description has been added yet.'}</p>
            </DetailCard>
          </div>

          <DetailCard title="Record information" icon={<ClockIcon size={20} />}>
            <dl className="pms-console__tenant-record">
              <div>
                <dt>Department ID</dt>
                <dd>
                  <code ref={identifier} tabIndex={-1}>{department.id}</code>
                  <Button variant="ghost" onClick={() => void copyId()}><CopyIcon size={16} />Copy ID</Button>
                  {copyFailed ? <p role="alert" className="pms-hint">Clipboard access is unavailable. Select and copy the department ID above.</p> : null}
                </dd>
              </div>
              <div>
                <dt>Management Version</dt>
                <dd><code>v{department.management_version}</code></dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd><time dateTime={department.created_at}>{format.dateTime(department.created_at)}</time></dd>
              </div>
              <div>
                <dt>Last Updated</dt>
                <dd><time dateTime={department.updated_at}>{format.dateTime(department.updated_at)}</time></dd>
              </div>
            </dl>
          </DetailCard>
        </div>

        <div className="pms-console__tenant-view-footer">{back}<span className="pms-meta">Demo record. Changes reset on reload.</span></div>
      </div>

      {editing && canEdit ? (
        <DepartmentEditor department={editing} onClose={() => setEditing(null)} onSave={(draft) => {
          const result = save(draft, editing);
          if (!result.department) return result.error;
          setEditing(null);
          return undefined;
        }} />
      ) : null}

      <ConfirmDialog open={Boolean(archiving) && canManage} title={`Archive ${department.name}?`} confirmLabel="Archive department" tone="danger"
        error={archiveError} onCancel={() => setArchiving(null)} onConfirm={() => {
          if (!archiving) return;
          const error = archive(archiving);
          if (error) { setArchiveError(error); return; }
          setArchiving(null);
          toast.success('This department is archived in the preview. Its details remain available.', { title: 'Department archived' });
        }}>
        This archives the department and marks it inactive. Historical records remain preserved. Changes apply only to this preview.
      </ConfirmDialog>
    </div>
  );
}
