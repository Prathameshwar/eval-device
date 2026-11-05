'use client';
import { useId, useRef, useState, type FormEvent } from 'react';
import { Button, ConfirmDialog, Modal, Notice, Select, TextField } from '@pms/ui';
import { saveModel } from '@/lib/direct-model-actions';
import { MODEL_LABELS, type ModelDraft, type ModelKind, type ModelMode, type RuntimeModel } from '@/lib/direct-model-types';

const localKeys = {
  llm: ['qwen3-4b-local', 'qwen3-1.7b-local', 'qwen3.5-4b-local', 'qwenmedic-v1-local'],
  asr: ['tiny', 'base', 'small', 'medium', 'large-v3', 'large-v3-turbo', 'whisper-medical-v1'],
  tts: ['espeak_ng'], video: ['opencv_motion'],
};
const engines = {
  llm: [{ value: 'openai', label: 'OpenAI' }, { value: 'azure_openai', label: 'Azure OpenAI' }, { value: 'anthropic', label: 'Anthropic' }, { value: 'openai_compatible', label: 'OpenAI compatible' }],
  asr: [{ value: 'azure_openai_whisper', label: 'Azure OpenAI Whisper' }, { value: 'aws_transcribe', label: 'Amazon Transcribe' }, { value: 'azure_speech', label: 'Azure Speech' }],
  tts: [{ value: 'aws_polly', label: 'Amazon Polly' }, { value: 'azure_speech', label: 'Azure Speech' }],
  video: [{ value: 'aws_rekognition', label: 'Amazon Rekognition' }, { value: 'azure_video_indexer', label: 'Azure Video Indexer' }],
};
const labels: Record<string, string> = { base_url: 'API endpoint', region: 'Region', staging_bucket: 'Private staging bucket',
  endpoint: 'Endpoint', subscription_id: 'Azure subscription ID', resource_group: 'Resource group', account_name: 'Account name',
  account_id: 'Account ID', location: 'Region', tenant_id: 'Directory ID', client_id: 'Application ID', role_arn: 'Role ARN',
  external_id: 'External ID', resource_id: 'Resource ID', api_version: 'API version', staging_prefix: 'Staging folder prefix', session_token: 'Session token', api_key: 'API key', access_key_id: 'Access key ID', secret_access_key: 'Secret access key', client_secret: 'Client secret' };
function initial(kind: ModelKind, location: ModelMode): ModelDraft {
  const engine = location === 'local' ? { llm: 'llm', asr: 'local_whisper', tts: 'espeak_ng', video: 'opencv_motion' }[kind] : engines[kind][0]!.value;
  const provider = location === 'local' ? kind === 'llm' ? 'local_llama_cpp' : kind === 'asr' ? 'local_whisper' : 'local' : kind === 'llm' ? engine : engine.startsWith('aws_') ? 'aws' : 'azure';
  return { name: '', kind, location, engine: kind === 'llm' ? 'llm' : engine, provider, model_key: location === 'local' ? localKeys[kind][0]! : '',
    settings: {}, defaults: {}, is_active: true };
}
export function RuntimeModelEditor({ kind, model, onClose, onSaved }: { kind: ModelKind; model?: RuntimeModel; onClose: () => void; onSaved: () => void }) {
  const formId = useId();
  const [draft, setDraft] = useState<ModelDraft>(() => model ? { name: model.name, kind: model.kind, location: model.location, provider: model.provider, engine: model.engine, model_key: model.model_key, settings: model.settings, defaults: model.defaults, is_active: model.is_active, expected_revision: model.revision } : initial(kind, 'cloud'));
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const submitting = useRef(false);
  const cloud = draft.location === 'cloud';
  const llm = draft.kind === 'llm';
  const aws = draft.provider === 'aws';
  const auth = String(draft.settings.auth_mode ?? (aws ? 'access_key' : draft.engine === 'azure_video_indexer' ? 'service_principal' : 'api_key'));
  function update(value: Partial<ModelDraft>) { setDraft(old => ({ ...old, ...value })); setDirty(true); setError(undefined); }
  function settings(key: string, value: string) { update({ settings: { ...draft.settings, [key]: value } }); }
  function reset(nextKind: ModelKind, location: ModelMode, provider?: string) {
    const next = initial(nextKind, location);
    if (provider) { next.engine = nextKind === 'llm' ? 'llm' : provider; next.provider = nextKind === 'llm' ? provider : provider.startsWith('aws_') ? 'aws' : 'azure'; }
    update({ ...next, name: draft.name }); setSecrets({});
  }
  let fields = llm ? ['base_url'] : draft.engine === 'azure_openai_whisper' ? ['endpoint'] : aws ? ['region', ...(draft.kind === 'tts' ? [] : ['staging_bucket'])] : draft.engine === 'azure_speech' ? ['region'] : ['subscription_id', 'resource_group', 'account_name', 'account_id', 'location'];
  if (!llm && auth === 'assume_role') fields = [...fields, 'role_arn', 'external_id'];
  if (!llm && auth === 'service_principal') fields = [...fields, 'tenant_id', 'client_id'];
  if (draft.engine === 'azure_speech' && auth !== 'api_key') fields = [...fields, 'endpoint', 'resource_id'];
  const optionalFields = !cloud || llm ? [] : draft.engine === 'azure_openai_whisper' ? (draft.settings.model === 'gpt-realtime-whisper' ? [] : ['api_version']) : aws && draft.kind !== 'tts' ? ['staging_prefix'] : draft.engine === 'azure_speech' && auth === 'api_key' ? ['endpoint'] : [];
  const secretFields = llm || auth === 'api_key' ? ['api_key'] : auth === 'access_key' ? ['access_key_id', 'secret_access_key', 'session_token'] : auth === 'service_principal' ? ['client_secret'] : [];
  const endpointKey = llm ? "base_url" : "endpoint";
  const freshCredentials = !model?.has_credentials || (model && (draft.settings[endpointKey] !== model.settings[endpointKey] || (!llm && auth !== model.settings.auth_mode))) || secretFields.some(key => !!secrets[key]);
  function close() { if (submitting.current) return; if (dirty) setDiscard(true); else onClose(); }
  async function save(event: FormEvent) {
    event.preventDefault(); if (submitting.current || uncertain) return;
    submitting.current = true; setBusy(true); setError(undefined);
    const values: Record<string, unknown> = cloud ? Object.fromEntries([...fields, ...optionalFields.filter(key => draft.settings[key])].map(key => [key, draft.settings[key] ?? ''])) : {};
    if (cloud && !llm) values.auth_mode = auth;
    if (cloud && draft.engine === 'azure_openai_whisper') values.model = draft.settings.model ?? 'whisper';
    if (cloud && llm) {
      values.max_tokens = draft.settings.max_tokens ?? 1024;
      for (const key of ['token_parameter', 'stream_usage', 'instruction_role', 'model_options']) {
        if (draft.settings[key] !== undefined) values[key] = draft.settings[key];
      }
    }
    const credentials = cloud ? Object.fromEntries(secretFields.filter(key => secrets[key]).map(key => [key, secrets[key]!])) : {};
    const body: ModelDraft = { ...draft, settings: values, model_key: draft.model_key || draft.engine,
      ...(Object.keys(credentials).length ? { credentials } : {}) };
    try {
      const result = await saveModel(body, model?.id);
      if (result.error !== undefined) { setError(result.error); setUncertain(!!result.uncertain); return; }
      setSecrets({}); setDirty(false); onSaved();
    } catch { setUncertain(true); setError('Unable to confirm the save. Close and reload the list before trying again.'); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <>
    <Modal open size="md" title={`${model ? 'Edit' : 'Add'} ${MODEL_LABELS[draft.kind].toLowerCase()} model`} busy={busy} onClose={close}
      footer={<><Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button><Button form={formId} type="submit" loading={busy} disabled={uncertain || (!!model && !dirty)}>Save model</Button></>}>
      <form id={formId} onSubmit={event => void save(event)}>
        <fieldset className="direct-model-fields" disabled={busy}>
          {error && <Notice tone="danger">{error}</Notice>}
          {!model && (kind === 'asr' || kind === 'tts') && <Select label="Audio type" value={draft.kind} options={[{ value: 'asr', label: 'Speech recognition' }, { value: 'tts', label: 'Speech output' }]} onChange={value => reset(value as ModelKind, draft.location)} />}
          {!model && <div className="model-mode-control" role="group" aria-label="Model location">
            {(['local', 'cloud'] as const).map(value => <button type="button" key={value} aria-pressed={draft.location === value} onClick={() => reset(draft.kind, value)}>{value === 'local' ? 'Local' : 'Cloud'}</button>)}
          </div>}
          <TextField label="Name" value={draft.name} maxLength={100} required onChange={event => update({ name: event.target.value })} />
          {cloud ? <>
            <Select label="Provider" value={llm ? draft.provider : draft.engine} disabled={!!model} options={engines[draft.kind]} onChange={value => reset(draft.kind, 'cloud', value)} />
            {(llm || draft.engine === 'azure_openai_whisper') && <TextField label={draft.provider === 'azure_openai' || draft.engine === 'azure_openai_whisper' ? 'Deployment name' : 'Model ID'} required value={draft.model_key} maxLength={100} onChange={event => update({ model_key: event.target.value })} />}
            {!llm && draft.engine !== 'azure_openai_whisper' && <Select label="Authentication" value={auth} options={aws
              ? [{ value: 'access_key', label: 'Access keys' }, { value: 'workload_identity', label: 'Server identity' }, { value: 'assume_role', label: 'Assume role' }]
              : [{ value: 'service_principal', label: 'Application credentials' }, { value: 'workload_identity', label: 'Server identity' }, ...(draft.engine === 'azure_speech' ? [{ value: 'api_key', label: 'API key' }] : [])]}
              onChange={value => { update({ settings: { ...draft.settings, auth_mode: value } }); setSecrets({}); }} />}
            {fields.map(key => <TextField key={key} label={labels[key] ?? key} required value={String(draft.settings[key] ?? '')} maxLength={512}
              placeholder={key === 'base_url' ? draft.provider === 'openai' ? 'https://api.openai.com/v1' : draft.provider === 'anthropic' ? 'https://api.anthropic.com/v1' : draft.provider === 'azure_openai' ? 'https://your-resource.openai.azure.com/openai/v1' : 'https://your-provider.example/v1' : key === 'endpoint' && draft.engine === 'azure_openai_whisper' ? 'https://your-resource.openai.azure.com/openai/v1' : undefined}
              hint={key === 'base_url' || (key === 'endpoint' && draft.engine === 'azure_openai_whisper') ? 'Use an endpoint allowed by the API server.' : undefined}
              onChange={event => settings(key, event.target.value)} />)}
            {draft.engine === 'azure_openai_whisper' && <Select label="Speech model" value={String(draft.settings.model ?? 'whisper')} options={[{ value: 'whisper', label: 'Whisper' }, { value: 'gpt-realtime-whisper', label: 'Realtime Whisper' }]} onChange={value => {
              const next: ModelDraft["settings"] = { ...draft.settings, model: value }; if (value === 'gpt-realtime-whisper') delete next.api_version;
              update({ settings: next });
            }} />}
            {optionalFields.map(key => <TextField key={key} label={labels[key] ?? key} value={String(draft.settings[key] ?? '')} maxLength={512}
              hint={key === 'api_version' ? 'Optional. Leave blank for the v1 API; otherwise use a version such as 2024-06-01.' : 'Optional.'}
              onChange={event => settings(key, event.target.value)} />)}
            {llm && <TextField label="Maximum reply tokens" type="number" min={16} max={4096} required value={Number(draft.settings.max_tokens ?? 1024)} onChange={event => update({ settings: { ...draft.settings, max_tokens: Number(event.target.value) } })} />}
            {secretFields.map(key => <TextField key={key} label={labels[key] ?? key} type="password" autoComplete="new-password" required={key !== 'session_token' && !!freshCredentials} value={secrets[key] ?? ''} maxLength={llm ? 4096 : 8192}
              hint={key === 'session_token' ? 'Optional, for temporary AWS credentials. Enter all credential fields when replacing credentials.' : model?.has_credentials ? freshCredentials ? 'Enter fresh credentials for this change.' : 'Leave blank to keep the saved credential.' : undefined}
              onChange={event => { setSecrets(old => ({ ...old, [key]: event.target.value })); setDirty(true); }} />)}
          </> : <>
            <Select label="Local model" value={draft.model_key} options={localKeys[draft.kind].map(value => ({ value, label: value }))} onChange={value => update({ model_key: value })} />
            <p className="pms-hint">No endpoint or credentials needed. You can assign it now; install and run it on the device or its connected laptop before use.</p>
          </>}
          {cloud && llm && draft.provider !== 'anthropic' && <details className="direct-model-options"><summary>Conversation compatibility <span>Optional</span></summary>
            <Select label="Output token parameter" value={String(draft.settings.token_parameter ?? (['openai', 'azure_openai'].includes(draft.provider) ? 'max_completion_tokens' : 'max_tokens'))} options={[{ value: 'max_tokens', label: 'max_tokens' }, { value: 'max_completion_tokens', label: 'max_completion_tokens' }]} onChange={value => settings('token_parameter', value)} />
            <Select label="Streaming usage" value={draft.settings.stream_usage === false || (draft.settings.stream_usage === undefined && draft.provider === 'anthropic') ? 'off' : 'on'} options={[{ value: 'on', label: 'Request usage totals' }, { value: 'off', label: 'Omit optional usage request' }]} onChange={value => update({ settings: { ...draft.settings, stream_usage: value === 'on' } })} />
            <Select label="Instruction role" value={String(draft.settings.instruction_role ?? 'system')} options={[{ value: 'system', label: 'System' }, { value: 'developer', label: 'Developer' }]} onChange={value => settings('instruction_role', value)} />
          </details>}
          {(draft.kind === 'asr' || draft.kind === 'tts') && <details className="direct-model-options"><summary>Speech preferences <span>Optional</span></summary>
            <TextField label="Language" maxLength={40} placeholder="Use device language" hint={draft.engine === 'azure_openai_whisper' ? 'Use en, hi or auto.' : 'Use a provider locale such as en-IN or hi-IN.'} value={draft.defaults.language ?? ''} onChange={event => update({ defaults: event.target.value ? { ...draft.defaults, language: event.target.value } : Object.fromEntries(Object.entries(draft.defaults).filter(([key]) => key !== 'language')) })} />
            {draft.kind === 'tts' && <TextField label="Voice" maxLength={120} value={draft.defaults.voice ?? ''} onChange={event => update({ defaults: event.target.value ? { ...draft.defaults, voice: event.target.value } : Object.fromEntries(Object.entries(draft.defaults).filter(([key]) => key !== 'voice')) })} />}
            {draft.kind === 'tts' && <Select label="Audio format" value={draft.defaults.format ?? ''} options={[{ value: '', label: 'Provider default' }, ...(['mp3', 'wav', 'pcm', ...(draft.engine === 'aws_polly' ? ['ogg'] : [])]).map(value => ({ value, label: value.toUpperCase() }))]} onChange={value => update({ defaults: value ? { ...draft.defaults, format: value } : Object.fromEntries(Object.entries(draft.defaults).filter(([key]) => key !== 'format')) })} />}
          </details>}
          {model && <Select label="Status" value={draft.is_active ? 'active' : 'inactive'} options={[{ value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }]} onChange={value => update({ is_active: value === 'active' })} />}
        </fieldset>
      </form>
    </Modal>
    <ConfirmDialog open={discard} title="Discard model changes?" confirmLabel="Discard changes" onConfirm={onClose} onCancel={() => setDiscard(false)}>Your changes have not been saved.</ConfirmDialog>
  </>;
}
