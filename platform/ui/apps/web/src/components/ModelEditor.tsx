'use client';

import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import {
  Button, CheckIcon, ConfirmDialog, Drawer,
  Notice, Select, TextField, ClockIcon, ActivityIcon,
} from '@pms/ui';
import { ModelIcon } from './icons-product';
import { PROVIDER_LABELS } from './provider-labels';
import type { ModelDefinition, ModelCategory } from '@/lib/model-directory';
import type { ProviderOption } from '@/lib/model-actions';
import {
  modelDraft, MODEL_FIELD_LIMITS, operationsForCategories, validateModelDraft,
  type ModelDraft, type ModelField,
} from '@/lib/model-editor';

const CATEGORY_OPTIONS: { value: ModelCategory; label: string }[] = [
  { value: 'text', label: 'Text Processing' },
  { value: 'conversation', label: 'Dialogue/Conversation' },
  { value: 'asr', label: 'Automatic Speech Recognition (ASR)' },
  { value: 'tts', label: 'Text To Speech (TTS)' },
  { value: 'vision', label: 'Computer Vision' },
  { value: 'video', label: 'Video Indexing' },
  { value: 'ocr', label: 'OCR' },
  { value: 'embedding', label: 'Embedding' },
  { value: 'reranking', label: 'Reranking' },
  { value: 'image_generation', label: 'Image Generation' },
  { value: 'video_generation', label: 'Video Generation' },
];

export function ModelEditor({ model, providers, onSave, onClose }: {
  model: ModelDefinition | null;
  providers: readonly ProviderOption[];
  onSave: (draft: ModelDraft) => string | undefined | Promise<string | undefined>;
  onClose: () => void;
}) {
  const [initial] = useState(() => modelDraft(model));
  const [draft, setDraft] = useState(initial);
  const [touched, setTouched] = useState<Partial<Record<ModelField, boolean>>>({});
  const [attempted, setAttempted] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [saveError, setSaveError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const formId = useId();
  const form = useRef<HTMLFormElement>(null);
  const saved = useRef(false);
  const creating = !model;
  const dirty = (Object.keys(draft) as (keyof ModelDraft)[]).some((key) => draft[key] !== initial[key]);
  const errors = validateModelDraft(draft, creating);
  const providerOptions = providers.length
    ? providers.map((provider) => ({ value: provider.id, label: PROVIDER_LABELS[provider.id] ?? provider.id.toUpperCase() }))
    : Object.entries(PROVIDER_LABELS).map(([value, label]) => ({ value, label }));

  useEffect(() => {
    form.current?.querySelector<HTMLInputElement>('[name="display_name"]')?.focus();
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);

  function update<K extends keyof ModelDraft>(key: K, value: ModelDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setSaveError(undefined);
  }

  const blur = (key: ModelField) => () => {
    if (draft[key] !== initial[key]) setTouched((current) => ({ ...current, [key]: true }));
  };

  const error = (key: ModelField) => attempted || touched[key] ? errors[key] : undefined;
  const close = () => { if (busy) return; if (dirty) setDiscarding(true); else onClose(); };

  function toggleCategory(cat: ModelCategory) {
    const active = draft.categories.includes(cat);
    const categories = active ? draft.categories.filter((c) => c !== cat) : [...draft.categories, cat];
    setDraft((current) => ({ ...current, categories, operations: operationsForCategories(categories) }));
    setSaveError(undefined);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saved.current || (model && !dirty) || discarding) return;
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
      setSaveError('Could not save the model. Your entries are still here; try again.');
    } finally { setBusy(false); }
  }

  return <>
    <Drawer open title={creating ? 'Register model' : 'Edit model'} size="lg" onClose={close}
      footer={<>
        <Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button>
        <Button type="submit" form={formId} loading={busy} disabled={busy || (!creating && !dirty)}>
          <CheckIcon size={16} />{creating ? 'Register model' : 'Save changes'}
        </Button>
      </>}>
      <form id={formId} ref={form} className="pms-console__tenant-form" noValidate onSubmit={submit}>
        <Notice tone="info" live="off">Changes are saved to the platform's shared model catalog.</Notice>
        {saveError ? <Notice tone="danger" title="Model was not saved">{saveError}</Notice> : null}
        {attempted && Object.keys(errors).length ? <Notice tone="danger" title="Check the highlighted fields">Correct the details below, then save again.</Notice> : null}

        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <legend><ModelIcon size={18} />Model specification</legend>

          <TextField label="Display name" optionalNote="Required" required name="display_name"
            value={draft.display_name} maxLength={MODEL_FIELD_LIMITS.display_name} onChange={(e) => update('display_name', e.target.value)}
            onBlur={blur('display_name')} error={error('display_name')} hint="The friendly title shown across the console (e.g. GPT-4o Flagship)." />

          {creating ? (
            <Select label="Provider" optionalNote="Required" required name="provider" options={providerOptions}
              value={draft.provider} onChange={(value) => update('provider', value)} />
          ) : (
            <TextField label="Provider" value={PROVIDER_LABELS[draft.provider] ?? draft.provider.toUpperCase()} readOnly
              hint="Provider cannot be changed after registration." />
          )}

          {creating ? (
            <TextField label="Model key" optionalNote="Required" required name="model_key"
              value={draft.model_key} maxLength={MODEL_FIELD_LIMITS.model_key} onChange={(e) => update('model_key', e.target.value)}
              onBlur={blur('model_key')} error={error('model_key')} hint="The provider's identifier for this model, e.g. gpt-4o, claude-3-5-sonnet, gemini-1.5-pro." />
          ) : (
            <TextField label="Model key" value={draft.model_key} readOnly hint="Model key cannot be changed after registration." />
          )}

          <div className="pms-field">
            <span className="pms-label">Capability categories</span>
            <span className="pms-hint" style={{ marginBottom: '8px', display: 'block' }}>Choose every category this model supports.</span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {CATEGORY_OPTIONS.map((cat) => {
                const active = draft.categories.includes(cat.value);
                return (
                  <button key={cat.value} type="button" onClick={() => toggleCategory(cat.value)}
                    aria-pressed={active}
                    className={`pms-btn ${active ? 'pms-btn--primary' : 'pms-btn--ghost'}`} style={{ fontSize: 'var(--pms-font-size-sm)', padding: '4px 12px' }}>
                    {cat.label}
                  </button>
                );
              })}
            </div>
            {errors.categories ? <p className="pms-error" style={{ marginTop: '8px' }}>{errors.categories}</p> : (
              <p className="pms-hint" style={{ marginTop: '8px' }}>Enables operations: {draft.operations.join(', ') || 'none yet'}.</p>
            )}
          </div>

          <TextField label="Publisher" optionalNote="Optional" name="publisher"
            value={draft.publisher} maxLength={MODEL_FIELD_LIMITS.publisher} onChange={(e) => update('publisher', e.target.value)}
            onBlur={blur('publisher')} error={error('publisher')} hint="e.g. OpenAI, Microsoft, Meta." />

          <TextField label="Model family" optionalNote="Optional" name="model_family"
            value={draft.model_family} maxLength={MODEL_FIELD_LIMITS.model_family} onChange={(e) => update('model_family', e.target.value)}
            onBlur={blur('model_family')} error={error('model_family')} hint="e.g. GPT-4, Llama, Gemini." />

          <TextField label="Model version" optionalNote="Optional" name="model_version"
            value={draft.model_version} maxLength={MODEL_FIELD_LIMITS.model_version} onChange={(e) => update('model_version', e.target.value)}
            onBlur={blur('model_version')} error={error('model_version')} hint="e.g. 2024-05-13, v2." />

          <div className="pms-field">
            <div className="pms-field__row">
              <label className="pms-label" htmlFor={`${formId}-description`}>Description</label>
              <span className="pms-optional">Optional</span>
            </div>
            <textarea id={`${formId}-description`} name="description" className="pms-input pms-console__tenant-textarea"
              rows={3} maxLength={MODEL_FIELD_LIMITS.description} value={draft.description}
              onChange={(e) => update('description', e.target.value)} onBlur={blur('description')}
              aria-invalid={Boolean(error('description'))} aria-describedby={`${formId}-description-hint`} />
            <p id={`${formId}-description-hint`} className={error('description') ? 'pms-error' : 'pms-hint'}>
              {error('description') ?? `${draft.description.length} / 4,000 characters`}
            </p>
          </div>
        </fieldset>

        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <legend><ActivityIcon size={18} />Adapter{!creating ? ' and lifecycle' : ''}</legend>
          <Select label="Adapter availability" value={draft.adapter_status}
            options={[
              { value: 'available', label: 'Adapter active' },
              { value: 'unavailable', label: 'No adapter yet' },
            ]}
            onChange={(value) => update('adapter_status', value as 'available' | 'unavailable')}
            hint="Whether the processing runtime has an adapter implemented for this model." />

          {!creating ? (
            <Select label="Lifecycle status" value={draft.lifecycle}
              options={[
                { value: 'active', label: 'Active' },
                { value: 'deprecated', label: 'Deprecated' },
              ]}
              onChange={(value) => update('lifecycle', value as 'active' | 'deprecated')}
              hint="Retiring a model is a separate, dedicated action from the catalog." />
          ) : null}
        </fieldset>

        {!creating ? (
          <fieldset disabled={busy} className="pms-console__tenant-fieldset">
            <legend><ClockIcon size={18} />Record information</legend>
            <p className="pms-hint">Record version v{model.version}. Registered {model.created_at.slice(0, 10)}.</p>
          </fieldset>
        ) : null}
      </form>
    </Drawer>
    <ConfirmDialog open={discarding} title="Discard unsaved changes?" tone="danger"
      confirmLabel="Discard changes" cancelLabel="Keep editing" onCancel={() => setDiscarding(false)} onConfirm={onClose}>
      Your entries will be lost. The model catalog will stay as it was before you opened this form.
    </ConfirmDialog>
  </>;
}
