'use client';
import { BackNavigation } from './BackNavigation';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Button, CalendarIcon, Card, CardBody, CheckCircleIcon, ClockIcon,
  ConfirmDialog, CopyIcon, CustomersIcon, EditIcon, EmptyState, ErrorState, isEmailLike,
  MailIcon, Menu, Notice, PageHeader, PhoneIcon, TrashIcon,
  useFormatters, useGranted, useToast, MonitorIcon, ActivityIcon,
} from '@pms/ui';
import { DeviceIcon } from './icons-product';
import { DeviceOperations } from './DeviceOperations';
import { DeviceEditor } from './DeviceEditor';
import { FleetDeviceEditor } from './FleetDeviceEditor';
import { DeviceAssociation } from './DeviceAssociation';
import { useDeviceDirectory } from './DeviceDirectoryProvider';
import { DeviceStatusBadge, DeviceConnectionBadge } from './DeviceStatusBadge';
import { deviceTypeLabel, type Device } from '@/lib/device-directory';

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

export function DeviceDetails({ deviceId, initialDevice }: { deviceId: string; initialDevice?: Device }) {
  const { rows, departments, languages, platform, associationTargets, scopeName, save, retire, savedDevice, setSavedDevice } = useDeviceDirectory();
  const device = rows.find((row) => row.id === deviceId) ?? initialDevice;
  const granted = useGranted();
  const format = useFormatters();
  const toast = useToast();

  const [editing, setEditing] = useState<Device | null>(null);
  const [retiring, setRetiring] = useState<Device | null>(null);
  const [retireError, setRetireError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  const root = useRef<HTMLDivElement>(null);
  const identifier = useRef<HTMLElement>(null);

  const canManage = granted(platform ? 'platform.organizations.manage' : 'org.devices.manage');
  const canRead = granted('org.devices.summary.read') || granted('platform.health.read') || granted('org.devices.read');

  useEffect(() => {
    const heading = root.current?.querySelector('h1');
    heading?.setAttribute('tabindex', '-1');
    heading?.focus({ preventScroll: true });
    const scroller = root.current?.closest('.pms-main');
    if (scroller) scroller.scrollTop = 0;
    setCopyFailed(false);
  }, [deviceId]);

  const back = <BackNavigation href="/devices" label="Back to devices" />;

  if (!canRead) return <div className="pms-page"><BackNavigation href="/home" label="Back to home" /><ErrorState status={403} /></div>;

  if (!device) return (
    <div className="pms-page pms-console__tenant-view" ref={root}>
      {back}
      <PageHeader title="Device not available" overline="Platform" />
      <EmptyState icon={<DeviceIcon size={28} />} title="This device is unavailable"
        body="Return to the directory to choose a device in your current scope." />
    </div>
  );

  const canEdit = canManage && device.enrollment_state !== 'retired';

  async function copyId() {
    if (!device) return;
    try {
      await navigator.clipboard.writeText(device.id);
      setCopyFailed(false);
      toast.success('The full device ID is ready to paste.', { title: 'Device ID copied' });
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
      {back}

      <PageHeader overline={scopeName} title={device.name} lede="Device system configurations, location metrics, and connection status."
        actions={<>
          {canEdit ? <Button onClick={() => setEditing(device)}><EditIcon size={16} />Edit device</Button> : null}
          <Menu label="Device actions" items={[
            { id: 'copy', label: 'Copy ID', icon: <CopyIcon size={16} /> },
            { id: 'delete', label: 'Retire', icon: <TrashIcon size={16} />, destructive: true,
              permission: platform ? 'platform.organizations.manage' : 'org.devices.manage', disabledReason: device.enrollment_state === 'retired' ? 'This device is retired.' : undefined },
          ]} onSelect={(action) => {
            if (action === 'copy') void copyId();
            if (action === 'delete' && canEdit) { setRetireError(undefined); setRetiring(device); }
          }} />
        </>} />

      <div className="pms-console__tenant-overview">
        {device.enrollment_state === 'retired' ? (
          <Notice tone="warning" title="Retired device" live="off">
            This registration has been removed. Its tenant history is retained. To use the hardware again, create a new registration and enroll it.
          </Notice>
        ) : null}

        {savedDevice?.id === device.id ? (
          <Notice tone="success" title={savedDevice.created ? 'Device created' : 'Device updated'} onDismiss={() => setSavedDevice(null)}>
            The saved details are shown below.
          </Notice>
        ) : null}

        <Card className="pms-console__tenant-summary">
          <dl style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
            <div>
              <dt><CheckCircleIcon size={18} />Enrollment</dt>
              <dd><DeviceStatusBadge device={device} /></dd>
            </div>
            <div>
              <dt><ActivityIcon size={18} />Connectivity</dt>
              <dd><DeviceConnectionBadge device={device} /></dd>
            </div>
            <div>
              <dt><CalendarIcon size={18} />Created on</dt>
              <dd><time dateTime={device.created_at}>{format.date(device.created_at.slice(0, 10))}</time></dd>
            </div>
            <div>
              <dt><ClockIcon size={18} />Last seen</dt>
              <dd>{device.last_seen_at ? <time dateTime={device.last_seen_at}>{format.dateTime(device.last_seen_at)}</time> : 'Never'}</dd>
            </div>
          </dl>
        </Card>

        <div className="pms-console__tenant-view-grid">
          <div className="pms-console__tenant-view-main">
            <DetailCard title="About this device" icon={<MonitorIcon size={20} />}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--pms-space-4)' }}>
                <div>
                  <h3 className="pms-label" style={{ marginBottom: 'var(--pms-space-1)' }}>Hardware Type</h3>
                  <p>{deviceTypeLabel(device.device_type)}</p>
                </div>
                <div>
                  <h3 className="pms-label" style={{ marginBottom: 'var(--pms-space-1)' }}>Description</h3>
                  <p className="pms-console__tenant-description">{device.summary_only ? 'Details require a tenant context with device read access.' : device.description?.trim() || 'No description has been added yet.'}</p>
                </div>
                <div>
                  <h3 className="pms-label" style={{ marginBottom: 'var(--pms-space-1)' }}>Location</h3>
                  <p>{device.summary_only ? 'Details unavailable in this context' : device.location || 'No location configured.'}</p>
                </div>
              </div>
            </DetailCard>

            <DetailCard title="Primary contact" icon={<CustomersIcon size={20} />}>
              {device.summary_only ? <p className="pms-hint">Details require a tenant context with device read access.</p> : <>
                <dl className="pms-console__tenant-contact">
                  <div><dt><CustomersIcon size={16} />Contact name</dt><dd>{device.contact_name || 'Not provided'}</dd></div>
                  <div><dt><MailIcon size={16} />Email address</dt><dd>
                    {device.contact_email && isEmailLike(device.contact_email)
                      ? <a href={`mailto:${encodeURIComponent(device.contact_email)}`}>{device.contact_email}</a>
                      : device.contact_email || 'Not provided'}
                  </dd></div>
                  <div><dt><PhoneIcon size={16} />Phone number</dt><dd>{device.contact_phone || 'Not provided'}</dd></div>
                </dl>
                {!device.contact_name && !device.contact_email && !device.contact_phone && canEdit
                  ? <Button variant="ghost" onClick={() => setEditing(device)}><EditIcon size={16} />Add contact details</Button> : null}
              </>}
            </DetailCard>

            <DetailCard title="Assignments & Configuration" icon={<ActivityIcon size={20} />}>
              <dl className="pms-console__tenant-contact">
                <div>
                  <dt><MonitorIcon size={16} />Department</dt>
                  <dd>{device.department_id ? (device.department_name ?? departments[device.department_id] ?? device.department_id) : 'No department assigned'}</dd>
                </div>

              </dl>
              {!device.summary_only && !device.department_id && canEdit ? (
                <Button variant="ghost" onClick={() => setEditing(device)}><EditIcon size={16} />Assign department</Button>
              ) : null}
            </DetailCard>
          </div>

          <DetailCard title="Record information" icon={<ClockIcon size={20} />}>
            <dl className="pms-console__tenant-record">
              <div>
                <dt>Device ID</dt>
                <dd>
                  <code ref={identifier} tabIndex={-1}>{device.id}</code>
                  <Button variant="ghost" onClick={() => void copyId()}><CopyIcon size={16} />Copy ID</Button>
                  {copyFailed ? <p role="alert" className="pms-hint">Clipboard access is unavailable. Select and copy the device ID above.</p> : null}
                </dd>
              </div>
              <div>
                <dt>Device unique ID</dt>
                <dd>{device.device_unique_id}</dd>
              </div>
              <div>
                <dt>Administrative status</dt>
                <dd>{device.is_active ? 'Active' : 'Inactive'}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd><time dateTime={device.created_at}>{format.dateTime(device.created_at)}</time></dd>
              </div>
              {device.registered_at ? (
                <div>
                  <dt>Registered</dt>
                  <dd><time dateTime={device.registered_at}>{format.dateTime(device.registered_at)}</time></dd>
                </div>
              ) : null}
              {device.enrolled_at ? (
                <div>
                  <dt>Enrolled</dt>
                  <dd><time dateTime={device.enrolled_at}>{format.dateTime(device.enrolled_at)}</time></dd>
                </div>
              ) : null}
            </dl>
          </DetailCard>
        </div>

        <DeviceAssociation key={'association-' + device.id} device={device} />
        <DeviceOperations key={'operations-' + device.id} device={device} />
        <div className="pms-console__tenant-view-footer"><span className="pms-meta">Saved device record.</span></div>
      </div>

      {editing && canEdit && platform ? <FleetDeviceEditor device={editing} tenants={associationTargets ?? {}} languages={languages ?? {}} onClose={() => setEditing(null)} onSave={async draft => {
        const result = await save(draft, editing); if (!result.device) return result.error; setEditing(null);
      }} /> : null}
      {editing && canEdit && !platform ? (
        <DeviceEditor device={editing} departments={departments} languages={languages} onClose={() => setEditing(null)} onSave={async (draft) => {
          const result = await save(draft, editing);
          if (!result.device) return result.error;
          setEditing(null);
          return undefined;
        }} />
      ) : null}

      <ConfirmDialog open={Boolean(retiring) && canManage} title={`Retire ${device.name}?`} confirmLabel="Retire device" tone="danger"
        busy={busy} error={retireError} onCancel={() => setRetiring(null)} onConfirm={async () => {
          if (!retiring) return;
          if (busy) return;
          setBusy(true);
          const error = await retire(retiring);
          setBusy(false);
          if (error) { setRetireError(error); return; }
          setRetiring(null);
          toast.success('This device is retired. Its details remain visible.', { title: 'Device retired' });
        }}>
        This removes the registration and marks it inactive. It cannot be reactivated. Its historical record is retained. Existing device credentials will be revoked.
      </ConfirmDialog>
    </div>
  );
}
