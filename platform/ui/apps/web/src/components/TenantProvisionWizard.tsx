'use client';
import { BackNavigation } from './BackNavigation';

import Link from 'next/link';
import { useRef, useState } from 'react';
import { Button, Notice, Select, TextField, isEmailLike, normalizeEmail } from '@pms/ui';
import { listDevices } from '@/lib/device-actions';
import { DEFAULT_DEVICE_QUERY, DEVICE_TYPES, type Device } from '@/lib/device-directory';
import { findAdministrators, provisionTenant, type ProvisionAdminChoice, type ProvisionDeviceChoice } from '@/lib/tenant-actions';
import { tenantDraft, validateTenantDraft } from '@/lib/tenant-editor';
import { useTenantDirectory } from './TenantDirectoryProvider';
import styles from './TenantProvisionWizard.module.css';

type Person = { id: string; display_name: string; email: string };
const steps = ['Tenant', 'Device', 'Administrator', 'Review'];

export function TenantProvisionWizard() {
  const { activePlans } = useTenantDirectory();
  const [step, setStep] = useState(0);
  const [tenant, setTenant] = useState(() => tenantDraft(null));
  const [tenantAttempted, setTenantAttempted] = useState(false);
  const [deviceMode, setDeviceMode] = useState<'new' | 'existing'>('new');
  const [deviceName, setDeviceName] = useState('');
  const [deviceUniqueId, setDeviceUniqueId] = useState('');
  const [deviceType, setDeviceType] = useState<'manikin' | 'laptop'>('manikin');
  const [deviceQuery, setDeviceQuery] = useState('');
  const [devices, setDevices] = useState<Device[]>([]);
  const [devicesSearched, setDevicesSearched] = useState(false);
  const [chosenDevice, setChosenDevice] = useState<Device>();
  const [adminMode, setAdminMode] = useState<'new' | 'existing'>('new');
  const [adminName, setAdminName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [adminQuery, setAdminQuery] = useState('');
  const [people, setPeople] = useState<Person[]>([]);
  const [peopleSearched, setPeopleSearched] = useState(false);
  const [chosenAdmin, setChosenAdmin] = useState<Person>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [completed, setCompleted] = useState<{ tenantId: string; deviceId: string }>();
  function field<K extends keyof typeof tenant>(key: K, value: (typeof tenant)[K]) {
    setTenant(current => ({ ...current, [key]: value }));
  }
  const tenantErrors = validateTenantDraft(tenant, activePlans, true);
  function next() {
    setError(undefined);
    if (step === 0) {
      setTenantAttempted(true);
      if (Object.keys(tenantErrors).length) {
        setError('Enter a tenant name and choose an active subscription plan. Check any contact details.'); return;
      }
    }
    if (step === 1 && (deviceMode === 'new' ? !deviceName.trim() || !deviceUniqueId.trim() || deviceUniqueId.trim().length > 50 : !chosenDevice?.management_etag)) {
      setError('Enter a device name and unique ID (up to 50 characters), or select a current device to transfer.'); return;
    }
    if (step === 2 && (adminMode === 'new'
      ? !adminName.trim() || !isEmailLike(normalizeEmail(adminEmail)) || adminPassword.length < 12 || adminPassword.length > 1024 || adminPassword !== confirmPassword
      : !chosenAdmin)) {
      setError('Complete the administrator details. New passwords must have 12–1024 characters and match.'); return;
    }
    setStep(current => current + 1);
  }
  async function searchDevices() {
    if (!deviceQuery.trim() || busy) return;
    setBusy(true); setError(undefined); setChosenDevice(undefined); setDevices([]); setDevicesSearched(false);
    try {
      const result = await listDevices('platform', {
        ...DEFAULT_DEVICE_QUERY, q: deviceQuery.trim(), enrollment_state: 'current', limit: 25,
      });
      if (result.error !== undefined) setError(result.error);
      else { setDevices(result.value.items.filter(row => !!row.management_etag)); setDevicesSearched(true); }
    } catch { setError('Unable to search devices. Try again.'); }
    finally { setBusy(false); }
  }
  async function searchPeople() {
    if (!adminQuery.trim() || busy) return;
    setBusy(true); setError(undefined); setChosenAdmin(undefined); setPeople([]); setPeopleSearched(false);
    try {
      const result = await findAdministrators(adminQuery.trim());
      if (result.error !== undefined) setError(result.error);
      else { setPeople(result.value); setPeopleSearched(true); }
    } catch { setError('Unable to search users. Try again.'); }
    finally { setBusy(false); }
  }
  async function finish() {
    if (submitting.current || completed) return;
    submitting.current = true;
    setBusy(true); setError(undefined);
    const device: ProvisionDeviceChoice = deviceMode === 'new'
      ? { kind: 'new', name: deviceName.trim(), device_unique_id: deviceUniqueId.trim(), device_type: deviceType }
      : { kind: 'existing', device_id: chosenDevice!.id, expected_etag: chosenDevice!.management_etag! };
    const administrator: ProvisionAdminChoice = adminMode === 'new'
      ? { kind: 'new', display_name: adminName.trim(), email: normalizeEmail(adminEmail), password: adminPassword }
      : { kind: 'existing', user_id: chosenAdmin!.id };
    try {
      const result = await provisionTenant(tenant, device, administrator);
      if (result.error !== undefined) {
        submitting.current = false;
        setError(result.error + ' Check the tenant list before retrying if the request timed out.'); return;
      }
      setAdminPassword(''); setConfirmPassword('');
      setCompleted({ tenantId: result.value.tenant.id, deviceId: result.value.device.id });
    } catch {
      submitting.current = false;
      setError('Unable to confirm the result. Check the tenant list before retrying.');
    } finally {
      setBusy(false);
    }
  }
  return <div className={'pms-page ' + styles.wizard}>
    <BackNavigation href="/tenants" label="Back to tenants" />
    <h1>Create tenant</h1>
    <p>Set up the tenant, one device, its first administrator, and clinical starters. Cases include presentation and symptoms, history, and eight vitals. All records are saved together.</p>
    {completed ? <section className={styles.panel}>
      <Notice tone="success" title="Tenant active">{tenant.name} and its administrator are ready. Three clinical specialties are active. The Alex patient profile and two editable cases are inactive until tenant review and activation. Two published scenarios are available in the desktop app as system starters, without tenant clinician approval. Chest discomfort in English is the tenant default; each user saves their own desktop Practice selection. Enroll the device and configure its models before device training.</Notice>
      <div className={styles.actions}><Link className="pms-btn" href={'/tenants/' + completed.tenantId}>View tenant</Link>
        <Link className="pms-btn pms-btn--ghost" href={'/devices/' + completed.deviceId}>View device</Link></div>
    </section> : <>
      <ol className={styles.steps} aria-label="Tenant setup progress">{steps.map((label, index) =>
        <li key={label} aria-current={step === index ? 'step' : undefined}>{index + 1}. {label}</li>)}</ol>
      {error && <Notice tone="danger">{error}</Notice>}
      <section className={styles.panel} aria-busy={busy}>
        {step === 0 && <div className={styles.fields}>
          <h2>Tenant details</h2>
          <TextField label="Tenant name" required maxLength={256} value={tenant.name} onChange={event => field('name', event.target.value)} error={tenantAttempted ? tenantErrors.name : undefined} />
          <Select label="Subscription plan" required value={tenant.subscription_plan_id}
            options={[{ value: '', label: 'Choose a plan' }, ...Object.entries(activePlans).map(([value, label]) => ({ value, label }))]}
            onChange={value => field('subscription_plan_id', value)} error={tenantAttempted ? tenantErrors.subscription_plan_id : undefined} />
          <TextField label="Description" maxLength={4000} value={tenant.description} onChange={event => field('description', event.target.value)} />
          <TextField label="Contact name" maxLength={256} value={tenant.contact_name} onChange={event => field('contact_name', event.target.value)} />
          <TextField label="Contact email" type="email" value={tenant.contact_email} onChange={event => field('contact_email', event.target.value)} error={tenantAttempted ? tenantErrors.contact_email : undefined} />
          <TextField label="Contact phone" maxLength={80} value={tenant.contact_phone} onChange={event => field('contact_phone', event.target.value)} />
        </div>}
        {step === 1 && <div className={styles.fields}>
          <h2>Device</h2>
          <Select label="Device choice" value={deviceMode} options={[{ value: 'new', label: 'Create a new device' }, { value: 'existing', label: 'Transfer an existing device' }]}
            disabled={busy} onChange={value => { setDeviceMode(value as typeof deviceMode); setChosenDevice(undefined); }} />
          {deviceMode === 'new' ? <>
            <TextField label="Device name" required maxLength={256} value={deviceName} onChange={event => setDeviceName(event.target.value)} />
            <TextField label="Device unique ID" required maxLength={50} value={deviceUniqueId} onChange={event => setDeviceUniqueId(event.target.value)} hint="Unique across the platform. Cannot be changed after registration." />
            <Select label="Device type" required value={deviceType} options={[...DEVICE_TYPES]} onChange={value => setDeviceType(value as typeof deviceType)} />
          </> : <>
            <Notice tone="info">Transfer keeps the device unique ID, retires the old registration, and requires fresh enrollment for this tenant. History stays with the source tenant.</Notice>
            <form onSubmit={event => { event.preventDefault(); void searchDevices(); }} className={styles.search}>
              <TextField label="Find device by name or ID" type="search" disabled={busy} value={deviceQuery}
                onChange={event => { setDeviceQuery(event.target.value); setChosenDevice(undefined); setDevices([]); setDevicesSearched(false); }} />
              <Button type="submit" variant="ghost" disabled={busy || !deviceQuery.trim()}>Search</Button>
            </form>
            <div role="group" aria-label="Existing devices">{devices.map(row => <label key={row.id} className={styles.choice}>
              <input type="radio" name="device" checked={chosenDevice?.id === row.id} onChange={() => setChosenDevice(row)} />
              <span>{row.name}<small>{row.organization_name ?? row.organization_id} · {row.id}</small></span>
            </label>)}</div>
            {devicesSearched && !devices.length && <p>No current devices found. Try a different name or ID.</p>}
          </>}
        </div>}
        {step === 2 && <div className={styles.fields}>
          <h2>Tenant administrator</h2>
          <Select label="Administrator choice" value={adminMode} options={[{ value: 'new', label: 'Create an administrator' }, { value: 'existing', label: 'Select an existing user' }]}
            disabled={busy} onChange={value => { setAdminMode(value as typeof adminMode); setChosenAdmin(undefined); }} />
          {adminMode === 'new' ? <>
            <TextField label="Full name" required maxLength={256} value={adminName} onChange={event => setAdminName(event.target.value)} />
            <TextField label="Email" required type="email" value={adminEmail} onChange={event => setAdminEmail(event.target.value)} />
            <TextField label="Password" required type="password" autoComplete="new-password" value={adminPassword} onChange={event => setAdminPassword(event.target.value)} />
            <TextField label="Confirm password" required type="password" autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} />
            <p className="pms-hint">Use 12–1024 characters. Share the password privately with this administrator.</p>
          </> : <>
            <form onSubmit={event => { event.preventDefault(); void searchPeople(); }} className={styles.search}>
              <TextField label="Find user by name or email" type="search" disabled={busy} value={adminQuery}
                onChange={event => { setAdminQuery(event.target.value); setChosenAdmin(undefined); setPeople([]); setPeopleSearched(false); }} />
              <Button type="submit" variant="ghost" disabled={busy || !adminQuery.trim()}>Search</Button>
            </form>
            <div role="group" aria-label="Existing users">{people.map(person => <label key={person.id} className={styles.choice}>
              <input type="radio" name="administrator" checked={chosenAdmin?.id === person.id} onChange={() => setChosenAdmin(person)} />
              <span>{person.display_name}<small>{person.email}</small></span>
            </label>)}</div>
            {peopleSearched && !people.length && <p>No active, verified users found. Try another name or email.</p>}
          </>}
        </div>}
        {step === 3 && <div className={styles.fields}>
          <h2>Review and finish</h2>
          <dl className={styles.review}>
            <div><dt>Tenant</dt><dd>{tenant.name} · {activePlans[tenant.subscription_plan_id]}</dd></div>
            <div><dt>Device</dt><dd>{deviceMode === 'new' ? `${deviceName} · ${DEVICE_TYPES.find(type => type.value === deviceType)?.label}` : `${chosenDevice?.name} · transfer with fresh enrollment`}</dd></div>
            <div><dt>Device unique ID</dt><dd>{deviceMode === 'new' ? deviceUniqueId.trim() : chosenDevice?.device_unique_id}</dd></div>
            <div><dt>Administrator</dt><dd>{adminMode === 'new' ? `${adminName} · ${adminEmail}` : `${chosenAdmin?.display_name} · ${chosenAdmin?.email}`}</dd></div>
            <div><dt>Initial status</dt><dd>Active tenant and device; device enrollment pending</dd></div>
            <div><dt>Patient profile</dt><dd>Fictional starter profile, inactive until tenant review</dd></div>
            <div><dt>Clinical specialties</dt><dd>Cardiology, Nephrology, Respiratory Medicine; active</dd></div>
            <div><dt>Editable cases</dt><dd>Chest discomfort interview, Wheeze interview; inactive until tenant review</dd></div>
            <div><dt>Published scenarios</dt><dd>Two active system starters in English and Hindi; no tenant clinician approval</dd></div>
            <div><dt>Desktop Practice default</dt><dd>Chest discomfort in English; each user saves their own selection</dd></div>
          </dl>
          <Notice tone="info">Published starters are available to select in the desktop app without activating the editable catalog cases. Review and activate the patient profile and cases before using them in catalog-based practice. Device training requires enrollment and model configuration.</Notice>
        </div>}
        <div className={styles.actions}>
          {step > 0 && <Button variant="ghost" disabled={busy} onClick={() => { setError(undefined); setStep(step - 1); }}>Back</Button>}
          {step < 3 ? <Button disabled={busy} onClick={next}>Continue</Button>
            : <Button loading={busy} disabled={busy} onClick={() => void finish()}>Finish setup</Button>}
        </div>
      </section>
    </>}
  </div>;
}
