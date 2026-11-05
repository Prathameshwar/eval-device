'use client';

import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import {
  Button, CheckIcon, ConfirmDialog, Drawer, EmailField,
  Notice, PhoneIcon, Select, TextField, MonitorIcon, ActivityIcon, CustomersIcon,
} from '@pms/ui';
import { deviceTypeLabel, type Device } from '@/lib/device-directory';
import {
  deviceDraft, DEVICE_FIELD_LIMITS, validateDeviceDraft,
  type DeviceDraft, type DeviceField,
} from '@/lib/device-editor';

export function DeviceEditor({ device, departments, languages = {}, onSave, onClose }: {
  device: Device | null;
  departments: Readonly<Record<string, string>>;

  languages?: Readonly<Record<string, string>>;
  onSave: (draft: DeviceDraft) => string | undefined | Promise<string | undefined>;
  onClose: () => void;
}) {
  const [initial] = useState(() => deviceDraft(device));
  const [draft, setDraft] = useState(initial);
  const [touched, setTouched] = useState<Partial<Record<DeviceField, boolean>>>({});
  const [attempted, setAttempted] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [saveError, setSaveError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const formId = useId();
  const form = useRef<HTMLFormElement>(null);
  const saved = useRef(false);
  const creating = !device;
  const dirty = (Object.keys(draft) as (keyof DeviceDraft)[]).some((key) => draft[key] !== initial[key]);
  const errors = validateDeviceDraft(draft, departments, creating, device);

  useEffect(() => {
    form.current?.querySelector<HTMLInputElement>('[name="name"]')?.focus();
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);

  function update<K extends keyof DeviceDraft>(key: K, value: DeviceDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setSaveError(undefined);
  }

  const blur = (key: DeviceField) => () => {
    if (draft[key] !== initial[key]) setTouched((current) => ({ ...current, [key]: true }));
  };

  const error = (key: DeviceField) => attempted || touched[key] ? errors[key] : undefined;
  const close = () => { if (busy) return; if (dirty) setDiscarding(true); else onClose(); };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saved.current || (device && !dirty) || discarding) return;
    setAttempted(true);
    if (Object.keys(errors).length) {
      requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    saved.current = true;
    setBusy(true);
    try {
      const message = await onSave(draft);
      if (message) { saved.current = false; setSaveError(message); }
    } catch {
      saved.current = false;
      setSaveError('Could not save the device. Your entries are still here; try again.');
    } finally { setBusy(false); }
  }

  return <>
    <Drawer open title={creating ? 'Create new device' : 'Edit device'} size="lg" onClose={close}
      footer={<>
        <Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button>
        <Button type="submit" form={formId} loading={busy} disabled={busy || (!creating && !dirty)}>
          <CheckIcon size={16} />{creating ? 'Create device' : 'Save changes'}
        </Button>
      </>}>
      <form id={formId} ref={form} className="pms-console__tenant-form" noValidate onSubmit={submit}>
        <Notice tone="info" live="off">Device records and configuration changes are saved to your tenant.</Notice>
        {saveError ? <Notice tone="danger" title="Device was not saved">{saveError}</Notice> : null}
        {attempted && Object.keys(errors).length ? <Notice tone="danger" title="Check the highlighted fields">Correct the details below, then save again.</Notice> : null}
        
        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <legend><MonitorIcon size={18} />Device details</legend>
          <TextField label="Device name" optionalNote="Required" required name="name"
            value={draft.name} maxLength={DEVICE_FIELD_LIMITS.name} onChange={(e) => update('name', e.target.value)}
            onBlur={blur('name')} error={error('name')} hint="Use a distinct name to recognize the device easily." />
          <TextField label="Device unique ID" required={creating} readOnly={!creating} maxLength={50}
            value={draft.device_unique_id} onChange={event => { if (creating) update('device_unique_id', event.target.value); }}
            error={error('device_unique_id')} hint="Unique across the platform. Cannot be changed after registration." />
          
          {creating ? (
            <Select label="Device type" optionalNote="Required" required name="device_type" placeholder="Choose a device type"
              value={draft.device_type} options={[
                { value: 'manikin', label: 'Manikin (Physical)' },
                { value: 'laptop', label: 'Laptop (Software)' },
              ]}
              onChange={(value) => update('device_type', value as DeviceDraft['device_type'])}
              onBlur={blur('device_type')} error={error('device_type')} />
          ) : (
            <TextField label="Device type" value={deviceTypeLabel(device.device_type)} readOnly
              hint="Device hardware type cannot be modified after creation." />
          )}

          <TextField label="Location" optionalNote="Optional" name="location"
            value={draft.location} maxLength={DEVICE_FIELD_LIMITS.location} onChange={(e) => update('location', e.target.value)}
            onBlur={blur('location')} error={error('location')} hint="e.g. Floor 3, Lab A" />

          <div className="pms-field">
            <div className="pms-field__row">
              <label className="pms-label" htmlFor={`${formId}-description`}>Description</label>
              <span className="pms-optional">Optional</span>
            </div>
            <textarea id={`${formId}-description`} name="description" className="pms-input pms-console__tenant-textarea"
              rows={3} maxLength={DEVICE_FIELD_LIMITS.description} value={draft.description}
              onChange={(e) => update('description', e.target.value)} onBlur={blur('description')}
              aria-invalid={Boolean(error('description'))} aria-describedby={`${formId}-description-hint`} />
            <p id={`${formId}-description-hint`} className={error('description') ? 'pms-error' : 'pms-hint'}>
              {error('description') ?? `${draft.description.length} / 4,000 characters`}
            </p>
          </div>
        </fieldset>

        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <legend><CustomersIcon size={18} />Primary contact</legend>
          <TextField label="Contact name" optionalNote="Optional" name="contact_name"
            value={draft.contact_name} maxLength={DEVICE_FIELD_LIMITS.contact_name}
            onChange={(e) => update('contact_name', e.target.value)} onBlur={blur('contact_name')} error={error('contact_name')} />
          <div className="pms-console__tenant-form-grid">
            <EmailField label="Contact email" optionalNote="Optional" name="contact_email" value={draft.contact_email}
              onChange={(value) => update('contact_email', value)} onBlur={blur('contact_email')} error={error('contact_email')} />
            <TextField label="Contact phone" optionalNote="Optional" name="contact_phone" type="tel" autoComplete="tel"
              leading={<PhoneIcon size={18} />} value={draft.contact_phone} maxLength={DEVICE_FIELD_LIMITS.contact_phone}
              onChange={(e) => update('contact_phone', e.target.value)} onBlur={blur('contact_phone')} error={error('contact_phone')}
              hint="Include the country code, if known." />
          </div>
          <p className="pms-hint">The on-site contact for this device, not an account holder.</p>
        </fieldset>

        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <legend><ActivityIcon size={18} />Assignments and configuration</legend>
          <Select label="Department" optionalNote="Optional" name="department_id" placeholder="No department"
            value={draft.department_id} options={[
              { value: '', label: 'No department' },
              ...(device?.department_id && !departments[device.department_id] ? [{ value: device.department_id, label: (device.department_name ?? 'Current department') + ' (unavailable)' }] : []),
              ...Object.entries(departments).map(([value, label]) => ({ value, label }))
            ]}
            onChange={(value) => update('department_id', value)} onBlur={blur('department_id')}
            error={error('department_id')} />


        </fieldset>

        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <legend><ActivityIcon size={18} />Status and enrollment</legend>
          <TextField label="Enrollment state" value={creating ? 'Pending' : device.enrollment_state} readOnly
            hint="Register the device, issue an enrollment token, then enrol it from the device agent." />
          <Select label="Device status" value={String(draft.is_active)}
            options={[{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }]}
            onChange={value => update('is_active', value === 'true')} />
          <Select label="Preferred language" value={draft.preferred_language}
            options={[{ value: '', label: 'Default (English)' }, ...Object.entries(languages).map(([value, label]) => ({ value, label }))]}
            onChange={value => update('preferred_language', value)} />
          {draft.is_active !== initial.is_active ? <Notice tone="info">Inactive devices cannot start processing. Activation still requires valid enrollment and an active tenant.</Notice> : null}
        </fieldset>
      </form>
    </Drawer>
    <ConfirmDialog open={discarding} title="Discard unsaved changes?" tone="danger"
      confirmLabel="Discard changes" cancelLabel="Keep editing" onCancel={() => setDiscarding(false)} onConfirm={onClose}>
      Your entries will be lost. The device list will stay as it was before you opened this form.
    </ConfirmDialog>
  </>;
}
