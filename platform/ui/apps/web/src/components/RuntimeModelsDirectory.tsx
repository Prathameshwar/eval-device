'use client';
import { useEffect, useRef, useState } from 'react';
import { Badge, Button, ConfirmDialog, Notice, Select, TextField, useCan } from '@pms/ui';
import { deleteModel, listModels, testModel } from '@/lib/direct-model-actions';
import { MODEL_LABELS, type ModelKind, type RuntimeModel } from '@/lib/direct-model-types';
import { RuntimeModelEditor } from './RuntimeModelEditor';
import { SettingsBreadcrumbs } from './SettingsBreadcrumbs';

export function RuntimeModelsDirectory() {
  const canManage = useCan("platform.settings.manage");
  const [models, setModels] = useState<RuntimeModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState('all');
  const [location, setLocation] = useState('all');
  const [status, setStatus] = useState('all');
  const [editor, setEditor] = useState<{ kind: ModelKind; model?: RuntimeModel }>();
  const [deleting, setDeleting] = useState<RuntimeModel>();
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState<string>();
  const testInProgress = useRef(false);
  useEffect(() => {
    let live = true; setLoading(true); setError(undefined);
    void listModels().then(result => { if (!live) return; if (result.error !== undefined) setError(result.error); else setModels(result.value); })
      .catch(() => { if (live) setError('Unable to load models. Try again.'); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [reload]);
  const rows = models.filter(row => (kind === 'all' || row.kind === kind) && (location === 'all' || row.location === location)
    && (status === 'all' || row.is_active === (status === 'active')) && `${row.name} ${row.model_key} ${row.provider}`.toLowerCase().includes(search.toLowerCase().trim()));
  async function remove() {
    if (!deleting || busy) return;
    setBusy(true); setError(undefined);
    try { const result = await deleteModel(deleting.id, deleting.revision);
      if (result.error !== undefined) { setError(result.error); return; }
      setNotice('Model deleted.'); setReload(n => n + 1);
    } catch { setError('Unable to confirm deletion. Reload the list.'); }
    finally { setBusy(false); setDeleting(undefined); }
  }
  async function check(row: RuntimeModel) {
    if (testInProgress.current) return;
    testInProgress.current = true; setTesting(row.id); setError(undefined); setNotice(undefined);
    try {
      const result = await testModel(row.id, row.revision);
      if (result.error !== undefined) setError(`${row.name}: ${result.error}`);
      else setNotice(`${row.name}: connection check passed for revision ${result.value.revision}. Credentials and API access were checked; device inference has not been tested.`);
    } catch { setError('Unable to complete the connection check. Try again when the service is available.'); }
    finally { testInProgress.current = false; setTesting(undefined); }
  }
  return <div className="pms-page direct-model-directory">
    <SettingsBreadcrumbs title="Models" />
    <header className="direct-model-heading"><div><h1>Models</h1><p>Add the models your devices can use.</p></div>
      {canManage && <div className="direct-model-add"><Button onClick={() => setEditor({ kind: 'llm' })}>Add LLM</Button><Button variant="ghost" onClick={() => setEditor({ kind: 'asr' })}>Add audio</Button><Button variant="ghost" onClick={() => setEditor({ kind: 'video' })}>Add video</Button></div>}
    </header>
    {error && <Notice tone="danger" action={<Button variant="ghost" onClick={() => setReload(n => n + 1)}>Reload</Button>}>{error}</Notice>}
    {notice && <p role="status" className="pms-hint">{notice}</p>}
    <div className="direct-model-filters">
      <TextField label="Search models" placeholder="Name, model or provider" value={search} onChange={event => setSearch(event.target.value)} />
      <Select label="Type" value={kind} options={[{ value: 'all', label: 'All types' }, ...Object.entries(MODEL_LABELS).map(([value, label]) => ({ value, label }))]} onChange={setKind} />
      <Select label="Location" value={location} options={[{ value: 'all', label: 'Local and cloud' }, { value: 'local', label: 'Local' }, { value: 'cloud', label: 'Cloud' }]} onChange={setLocation} />
      <Select label="Status" value={status} options={[{ value: 'all', label: 'All statuses' }, { value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }]} onChange={setStatus} />
    </div>
    {loading ? <p role="status">Loading models…</p> : rows.length ? <div className="direct-model-list" aria-label="Models">
      {rows.map(row => <article className="direct-model-row" key={row.id}>
        <div className="direct-model-identity"><h2>{row.name}</h2><p>{row.model_key}</p></div>
        <div className="direct-model-flags"><Badge>{MODEL_LABELS[row.kind]}</Badge><Badge>{row.location === 'local' ? 'Local' : 'Cloud'}</Badge>{!row.is_active && <Badge tone="warn">Inactive</Badge>}{row.organization_id && <Badge>Tenant scoped</Badge>}</div>
        {canManage && <div className="direct-model-row-actions">
          {row.location === 'cloud' && <Button variant="ghost" aria-label={`Test connection for ${row.name}`} loading={testing === row.id} disabled={!!testing || !row.is_active} onClick={() => void check(row)}>Test connection</Button>}
          <Button variant="ghost" disabled={!!testing} aria-label={`Edit ${row.name}`} onClick={() => setEditor({ kind: row.kind, model: row })}>Edit</Button><Button variant="ghost" disabled={!!testing} aria-label={`Delete ${row.name}`} onClick={() => setDeleting(row)}>Delete</Button></div>}
      </article>)}
    </div> : !error && <div className="direct-model-empty"><h2>{models.length ? 'No matching models' : 'Add your first model'}</h2><p>{models.length ? 'Adjust the search or filters.' : 'Choose LLM, audio or video above to get started.'}</p></div>}
    {!loading && <p className="pms-hint">{rows.length} {rows.length === 1 ? 'model' : 'models'}</p>}
    {editor && <RuntimeModelEditor {...editor} onClose={() => setEditor(undefined)} onSaved={() => { setEditor(undefined); setNotice('Model saved.'); setReload(n => n + 1); }} />}
    <ConfirmDialog open={!!deleting} title="Delete model?" confirmLabel="Delete model" busy={busy} onCancel={() => setDeleting(undefined)} onConfirm={() => void remove()}>Delete {deleting?.name}? Models assigned to devices must be removed from those devices first.</ConfirmDialog>
  </div>;
}
