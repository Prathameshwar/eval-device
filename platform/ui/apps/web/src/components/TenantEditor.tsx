'use client';

import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import {
  Badge, Button, CheckIcon, ConfirmDialog, CustomersIcon, Drawer, EmailField,
  Notice, PhoneIcon, Select, TextField,
} from '@pms/ui';
import { LicenseIcon, TenantIcon } from './icons-product';
import type { Tenant } from '@/lib/tenant-directory';
import {
  tenantDraft, TENANT_FIELD_LIMITS, validateTenantDraft,
  type TenantDraft, type TenantField,
} from '@/lib/tenant-editor';

export function TenantEditor({ tenant, plans, onSave, onClose }: {
  tenant: Tenant | null;
  plans: Readonly<Record<string, string>>;
  /** Return a recoverable message if the record can no longer be saved. */
  onSave: (draft: TenantDraft) => string | undefined | Promise<string | undefined>;
  onClose: () => void;
}) {
  const [initial] = useState(() => tenantDraft(tenant));
  const [draft, setDraft] = useState(initial);
  const [touched, setTouched] = useState<Partial<Record<TenantField, boolean>>>({});
  const [attempted, setAttempted] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [saveError, setSaveError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const formId = useId();
  const form = useRef<HTMLFormElement>(null);
  const saved = useRef(false);
  const creating = !tenant;
  const dirty = (Object.keys(draft) as (keyof TenantDraft)[]).some((key) => draft[key] !== initial[key]);
  const errors = validateTenantDraft(draft, plans, creating);
  const noPlans = Object.keys(plans).length === 0;

  useEffect(() => {
    form.current?.querySelector<HTMLInputElement>('[name="name"]')?.focus();
  }, []);

  // Keep refresh/tab-close protection limited to an actual unsaved draft.
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);

  function update<K extends keyof TenantDraft>(key: K, value: TenantDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setSaveError(undefined);
  }
  const blur = (key: TenantField) => () => {
    if (draft[key] !== initial[key]) setTouched((current) => ({ ...current, [key]: true }));
  };
  const error = (key: TenantField) => attempted || touched[key] ? errors[key] : undefined;
  const close = () => { if (busy) return; if (dirty) setDiscarding(true); else onClose(); };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saved.current || (tenant && !dirty) || discarding) return;
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
      setSaveError('Could not save the tenant. Your entries are still here; try again.');
    } finally { setBusy(false); }
  }

  return <>
    <Drawer open title={creating ? 'Create new tenant' : 'Edit tenant'} size="lg" onClose={close}
      footer={<>
        <Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button>
        <Button type="submit" form={formId} loading={busy} disabled={busy || (creating ? noPlans : !dirty)}>
          <CheckIcon size={16} />{creating ? 'Create tenant' : 'Save changes'}
        </Button>
      </>}>
      <form id={formId} ref={form} className="pms-console__tenant-form" noValidate onSubmit={submit}>
        <Notice tone="info" live="off">Changes are saved to the tenant record.</Notice>
        {saveError ? <Notice tone="danger" title="Tenant was not saved">{saveError}</Notice> : null}
        {attempted && Object.keys(errors).length ? <Notice tone="danger" title="Check the highlighted fields">Correct the details below, then save again.</Notice> : null}
        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <legend><TenantIcon size={18} />Tenant details</legend>
          <TextField label="Tenant name" optionalNote="Required" required name="name" autoComplete="organization"
            value={draft.name} maxLength={TENANT_FIELD_LIMITS.name} onChange={(e) => update('name', e.target.value)}
            onBlur={blur('name')} error={error('name')} hint="Use the name people will recognize in the tenant list." />
          <div className="pms-field">
            <div className="pms-field__row"><label className="pms-label" htmlFor={`${formId}-description`}>Description</label><span className="pms-optional">Optional</span></div>
            <textarea id={`${formId}-description`} name="description" className="pms-input pms-console__tenant-textarea"
              rows={3} maxLength={TENANT_FIELD_LIMITS.description} value={draft.description}
              onChange={(e) => update('description', e.target.value)} onBlur={blur('description')}
              aria-invalid={Boolean(error('description'))} aria-describedby={`${formId}-description-hint`} />
            <p id={`${formId}-description-hint`} className={error('description') ? 'pms-error' : 'pms-hint'}>
              {error('description') ?? `${draft.description.length} / 4,000 characters`}
            </p>
          </div>
        </fieldset>
        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <legend><CustomersIcon size={18} />Primary contact</legend>
          <TextField label="Contact name" optionalNote="Optional" autoComplete="name" name="contact_name"
            value={draft.contact_name} maxLength={TENANT_FIELD_LIMITS.contact_name}
            onChange={(e) => update('contact_name', e.target.value)} onBlur={blur('contact_name')} error={error('contact_name')} />
          <div className="pms-console__tenant-form-grid">
            <EmailField label="Contact email" optionalNote="Optional" name="contact_email" value={draft.contact_email}
              onChange={(value) => update('contact_email', value)} onBlur={blur('contact_email')} error={error('contact_email')} />
            <TextField label="Contact phone" optionalNote="Optional" name="contact_phone" type="tel" autoComplete="tel"
              leading={<PhoneIcon size={18} />} value={draft.contact_phone} maxLength={TENANT_FIELD_LIMITS.contact_phone}
              onChange={(e) => update('contact_phone', e.target.value)} onBlur={blur('contact_phone')} error={error('contact_phone')}
              hint="Include the country code, if known." />
          </div>
          <p className="pms-hint">Contact details do not create a user account or send an invitation.</p>
        </fieldset>
        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <legend><LicenseIcon size={18} />Subscription and status</legend>
          {creating ? <>
            <Select label="Subscription plan" optionalNote="Required" required name="subscription_plan_id" placeholder="Choose a plan"
              value={draft.subscription_plan_id} options={Object.entries(plans).map(([value, label]) => ({ value, label }))}
              onChange={(value) => update('subscription_plan_id', value)} onBlur={blur('subscription_plan_id')}
              error={error('subscription_plan_id')} disabled={noPlans} />
            {noPlans ? <Notice tone="warning" title="No plans available">A subscription plan is needed before a tenant can be created.</Notice> : null}
            <p className="pms-console__tenant-status-note"><Badge tone="neutral">Inactive</Badge>New tenants start inactive while their setup is completed.</p>
          </> : <>
            <TextField label="Subscription plan" value={plans[tenant.subscription_plan_id] ?? 'Plan unavailable'} readOnly
              hint="Subscription changes are separate from tenant details." />
            <Select label="Tenant status" value={String(draft.is_active)}
              options={[{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }]}
              onChange={(value) => update('is_active', value === 'true')} />
            {draft.is_active !== initial.is_active ? <Notice tone="info" live="polite">
              This changes the tenant to {draft.is_active ? 'Active' : 'Inactive'} and affects access immediately. Activation requires an assigned active administrator.
            </Notice> : null}
          </>}
        </fieldset>
      </form>
    </Drawer>
    <ConfirmDialog open={discarding} title="Discard unsaved changes?" tone="danger"
      confirmLabel="Discard changes" cancelLabel="Keep editing" onCancel={() => setDiscarding(false)} onConfirm={onClose}>
      Your entries will be lost. The tenant list will stay as it was before you opened this form.
    </ConfirmDialog>
  </>;
}
