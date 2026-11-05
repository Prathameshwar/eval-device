'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, CopyIcon, Modal, Notice, TextField, useGranted } from '@pms/ui';
import { changeDeviceLifecycle, issueEnrollment, readDevice, readDeviceConfiguration } from '@/lib/device-actions';
import { DeviceStateDialog } from './DeviceStateDialog';
import type { Device } from '@/lib/device-directory';
import { useDeviceDirectory } from './DeviceDirectoryProvider';

export function DeviceOperations({ device }: { device: Device }) {
  const granted = useGranted();
  const { remember, contextId, platform } = useDeviceDirectory();
  const manage = granted(platform ? 'platform.organizations.manage' : 'org.devices.manage');
  const configure = granted('org.configuration.read') && !device.summary_only;
  const [changingState, setChangingState] = useState(false);
  const [config, setConfig] = useState<{ language: string; operational: boolean; applied: boolean; modelsAssigned: boolean }>();
  const [configError, setConfigError] = useState<string>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<'enrollment' | 'revoke'>();
  const [enrollment, setEnrollment] = useState<{ enrollment_token: string; expires_at: string; contextId: string; deviceId: string }>();
  const [copyStatus, setCopyStatus] = useState<'copied' | 'failed'>();
  const tokenField = useRef<HTMLDivElement>(null);
  const pending = useRef(false);
  const visibleEnrollment = manage && !platform && device.is_active && device.enrollment_state !== 'retired'
    && enrollment?.contextId === contextId && enrollment.deviceId === device.id ? enrollment : undefined;
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setConfig(undefined);
    setConfigError(undefined);
    if (configure) void readDeviceConfiguration(contextId, device.id).then(result => {
      if (!active) return;
      if (result.error !== undefined) setConfigError(result.error); else setConfig(result.value);
    }).catch(() => { if (active) setConfigError('Unable to read the effective configuration.'); });
    return () => { active = false; };
  }, [contextId, device.id, device.management_etag, configure, revision]);
  useEffect(() => {
    if (!manage || platform || !device.is_active || device.enrollment_state === 'retired'
      || enrollment?.contextId !== contextId || enrollment.deviceId !== device.id) {
      setEnrollment(undefined); return;
    }
    if (!enrollment) return;
    const timer = setTimeout(() => setEnrollment(undefined), Math.max(0, Date.parse(enrollment.expires_at) - Date.now()));
    return () => clearTimeout(timer);
  }, [enrollment, device.is_active, device.enrollment_state, device.id, contextId, manage, platform]);
  async function refresh() {
    const result = await readDevice(contextId, device.id);
    if (result.error !== undefined) { setError(result.error); return; }
    remember(result.value);
    setError(undefined);
    setRevision(value => value + 1);
  }
  async function refreshStatus() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true); setError(undefined);
    try { await refresh(); }
    catch { setError('Unable to refresh device status. Try again.'); }
    finally { setBusy(false); pending.current = false; }
  }
  async function apply() {
    if (pending.current || !confirm) return;
    pending.current = true;
    setBusy(true); setError(undefined); setEnrollment(undefined); setCopyStatus(undefined);
    try {
      if (confirm === 'enrollment') {
        const result = await issueEnrollment(contextId, device.id, device.management_etag);
        if (result.error !== undefined) { setError(result.error); return; }
        setConfirm(undefined);
        setEnrollment({ ...result.value, contextId, deviceId: device.id });
        try { await refresh(); }
        catch { setError('The token was issued, but device status could not be refreshed. You can still copy the token.'); }
      } else {
        const result = await changeDeviceLifecycle(contextId, device.id, 'revoke', device.management_etag);
        if (result.error !== undefined) { setError(result.error); return; }
        remember(result.value);
      }
      setConfirm(undefined);
    } catch { setError('Unable to confirm the result. Refresh the device before trying again.'); }
    finally { setBusy(false); pending.current = false; }
  }
  async function copyToken() {
    if (!visibleEnrollment || Date.parse(visibleEnrollment.expires_at) <= Date.now()) return;
    try {
      await navigator.clipboard.writeText(visibleEnrollment.enrollment_token);
      setCopyStatus('copied');
    } catch {
      setCopyStatus('failed');
      const field = tokenField.current?.querySelector('input');
      field?.focus(); field?.select();
    }
  }
  return <Card><CardHeader title="Enrollment and configuration" /><CardBody>
    <p>Credential status: {device.credential_status?.replaceAll('_', ' ') ?? 'Unavailable'}</p>
    {device.credential_status === 'not_issued' ? <p>A device credential is created after the Desktop App or device agent uses an enrollment token. Until then, this status is expected, even after a token is issued.</p> : null}
    {config ? <dl>
      <dt>Effective language</dt><dd>{config.language}</dd>
      <dt>Models</dt><dd>{config.modelsAssigned ? 'Assigned' : 'Not assigned'}</dd>
      <dt>Device acknowledgement</dt><dd>{config.applied ? 'Current configuration applied' : 'Awaiting device acknowledgement'}</dd>
    </dl> : configure && !configError ? <p role="status">Loading configuration…</p> : null}
    {configure && configError ? <Notice tone="warning">{configError}</Notice> : null}
    {error && !confirm && !visibleEnrollment ? <Notice tone="danger">{error}</Notice> : null}
    <Button variant="ghost" disabled={busy} onClick={() => void refreshStatus()}>Refresh device status</Button>
    {manage && device.enrollment_state !== 'retired' ? <>
      {!platform && <Button disabled={busy || !device.is_active} onClick={() => { setError(undefined); setConfirm('enrollment'); }}>Issue enrollment token</Button>}
      <Button variant="ghost" disabled={busy} onClick={() => setChangingState(true)}>{device.is_active ? 'Deactivate device' : 'Activate device'}</Button>
      <Button variant="danger" disabled={busy} onClick={() => { setError(undefined); setConfirm('revoke'); }}>Revoke device access</Button>
      {!platform && !device.is_active ? <p>Activate the device before issuing an enrollment token.</p> : null}
    </> : null}
    {visibleEnrollment ? <Modal open title="Enrollment token ready" size="sm" onClose={() => setEnrollment(undefined)} footer={<>
      <Button variant="ghost" onClick={() => setEnrollment(undefined)}>Close and hide token</Button>
      <Button onClick={() => void copyToken()}><CopyIcon size={16} />Copy token</Button>
    </>}>
      <p>Use these details to enroll <strong>{device.name}</strong> in the Desktop App or device agent.</p>
      <p>The device credential becomes active after successful enrollment.</p>
      {error ? <Notice tone="warning">{error}</Notice> : null}
      <TextField label="Device ID" value={device.id} readOnly autoComplete="off" onFocus={event => event.currentTarget.select()} />
      <div ref={tokenField}><TextField label="Enrollment token" value={visibleEnrollment.enrollment_token} readOnly autoComplete="off" spellCheck={false} onFocus={event => event.currentTarget.select()} /></div>
      <p>Copy this token before closing. It can be used once and expires at {new Date(visibleEnrollment.expires_at).toLocaleString()}. It is hidden after expiry or when you leave this page. To replace a hidden token, issue a new one.</p>
      {copyStatus === 'copied' ? <Notice tone="success">Enrollment token copied.</Notice> : null}
      {copyStatus === 'failed' ? <Notice tone="warning">Clipboard access is unavailable. Select and copy the enrollment token above.</Notice> : null}
    </Modal> : null}
    {changingState && <DeviceStateDialog key={device.management_etag} device={device} onClose={() => setChangingState(false)} />}
    <ConfirmDialog open={!!confirm} title={confirm === 'enrollment' ? 'Issue an enrollment token?' : 'Revoke device access?'} tone="danger" busy={busy} error={error}
      confirmLabel={confirm === 'enrollment' ? 'Issue token' : 'Revoke access'} onConfirm={() => void apply()} onCancel={() => setConfirm(undefined)}>
      {confirm === 'enrollment' ? 'This replaces any previous enrollment token and immediately invalidates the existing device credential. The device must enrol again.' : 'This invalidates device credentials and any pending enrollment token. The device must enrol again before it can connect.'}
    </ConfirmDialog>
  </CardBody></Card>;
}
