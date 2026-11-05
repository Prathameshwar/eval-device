'use client';

import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import {
  Badge, Button, CheckIcon, ConfirmDialog, Drawer,
  Notice, Select, TextField,
} from '@pms/ui';
import { TenantIcon } from './icons-product';
import type { Department } from '@/lib/department-directory';
import {
  departmentDraft, DEPARTMENT_FIELD_LIMITS, validateDepartmentDraft,
  type DepartmentDraft, type DepartmentField,
} from '@/lib/department-editor';

export function DepartmentEditor({ department, onSave, onClose }: {
  department: Department | null;
  onSave: (draft: DepartmentDraft) => string | undefined;
  onClose: () => void;
}) {
  const [initial] = useState(() => departmentDraft(department));
  const [draft, setDraft] = useState(initial);
  const [touched, setTouched] = useState<Partial<Record<DepartmentField, boolean>>>({});
  const [attempted, setAttempted] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [saveError, setSaveError] = useState<string>();
  const formId = useId();
  const form = useRef<HTMLFormElement>(null);
  const saved = useRef(false);
  const creating = !department;
  const dirty = (Object.keys(draft) as (keyof DepartmentDraft)[]).some((key) => draft[key] !== initial[key]);
  const errors = validateDepartmentDraft(draft);

  useEffect(() => {
    form.current?.querySelector<HTMLInputElement>('[name="name"]')?.focus();
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);

  function update<K extends keyof DepartmentDraft>(key: K, value: DepartmentDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setSaveError(undefined);
  }

  const blur = (key: DepartmentField) => () => {
    if (draft[key] !== initial[key]) setTouched((current) => ({ ...current, [key]: true }));
  };

  const error = (key: DepartmentField) => attempted || touched[key] ? errors[key] : undefined;
  const close = () => { if (dirty) setDiscarding(true); else onClose(); };

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saved.current || (department && !dirty) || discarding) return;
    setAttempted(true);
    if (Object.keys(errors).length) {
      requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    saved.current = true;
    try {
      const message = onSave(draft);
      if (message) { saved.current = false; setSaveError(message); }
    } catch {
      saved.current = false;
      setSaveError('Could not save this preview. Your entries are still here; try again.');
    }
  }

  return <>
    <Drawer open title={creating ? 'Create new department' : 'Edit department'} size="lg" onClose={close}
      footer={<>
        <Button variant="ghost" onClick={close}>Cancel</Button>
        <Button type="submit" form={formId} disabled={creating ? false : !dirty}>
          <CheckIcon size={16} />{creating ? 'Create department' : 'Save changes'}
        </Button>
      </>}>
      <form id={formId} ref={form} className="pms-console__tenant-form" noValidate onSubmit={submit}>
        <Notice tone="info" live="off">Changes apply to this preview only and reset when you reload or leave Departments.</Notice>
        {saveError ? <Notice tone="danger" title="Department was not saved">{saveError}</Notice> : null}
        {attempted && Object.keys(errors).length ? <Notice tone="danger" title="Check the highlighted fields">Correct the details below, then save again.</Notice> : null}
        
        <fieldset className="pms-console__tenant-fieldset">
          <legend><TenantIcon size={18} />Department details</legend>
          <TextField label="Department name" optionalNote="Required" required name="name"
            value={draft.name} maxLength={DEPARTMENT_FIELD_LIMITS.name} onChange={(e) => update('name', e.target.value)}
            onBlur={blur('name')} error={error('name')} hint="Use a distinct clinical or training name." />
          
          <div className="pms-field">
            <div className="pms-field__row">
              <label className="pms-label" htmlFor={`${formId}-description`}>Description</label>
              <span className="pms-optional">Optional</span>
            </div>
            <textarea id={`${formId}-description`} name="description" className="pms-input pms-console__tenant-textarea"
              rows={3} maxLength={DEPARTMENT_FIELD_LIMITS.description} value={draft.description}
              onChange={(e) => update('description', e.target.value)} onBlur={blur('description')}
              aria-invalid={Boolean(error('description'))} aria-describedby={`${formId}-description-hint`} />
            <p id={`${formId}-description-hint`} className={error('description') ? 'pms-error' : 'pms-hint'}>
              {error('description') ?? `${draft.description.length} / 4,000 characters`}
            </p>
          </div>
        </fieldset>

        <fieldset className="pms-console__tenant-fieldset">
          <legend><TenantIcon size={18} />Status and reason</legend>
          <Select label="Department status" value={String(draft.is_active)}
            options={[
              { value: 'true', label: 'Active' },
              { value: 'false', label: 'Inactive' }
            ]}
            onChange={(value) => update('is_active', value === 'true')} />

          {!draft.is_active ? (
            <TextField label="Status reason" optionalNote="Optional" name="status_reason"
              value={draft.status_reason} maxLength={DEPARTMENT_FIELD_LIMITS.status_reason}
              onChange={(e) => update('status_reason', e.target.value)} onBlur={blur('status_reason')}
              error={error('status_reason')} hint="Explain why the department is currently inactive." />
          ) : null}
        </fieldset>
      </form>
    </Drawer>
    <ConfirmDialog open={discarding} title="Discard unsaved changes?" tone="danger"
      confirmLabel="Discard changes" cancelLabel="Keep editing" onCancel={() => setDiscarding(false)} onConfirm={onClose}>
      Your entries will be lost. The department list will stay as it was before you opened this form.
    </ConfirmDialog>
  </>;
}
