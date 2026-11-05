'use client';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { Button, ConfirmDialog, Modal, Notice, Select } from '@pms/ui';
import { deviceModels, saveDeviceModels } from '@/lib/direct-model-actions';
import { MODEL_LABELS, type DeviceChoices, type ModelKind, type ModelMode, type Selection } from '@/lib/direct-model-types';

const kinds = Object.keys(MODEL_LABELS) as ModelKind[];
export function DeviceModelDialog({ deviceId, onClose, onSaved }: {
  deviceId: string; onClose: () => void; onSaved: (name: string) => void;
}) {
  const formId = useId();
  const [data, setData] = useState<DeviceChoices>();
  const [selection, setSelection] = useState<Selection>();
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  useEffect(() => {
    let live = true;
    setLoading(true); setError(undefined); setData(undefined); setSelection(undefined); setDirty(false); setUncertain(false);
    void deviceModels(deviceId).then(result => {
      if (!live) return;
      if (result.error !== undefined) { setError(result.error); return; }
      setData(result.value); setSelection(result.value.selection); setDirty(false); setUncertain(false);
    }).catch(() => { if (live) setError('Unable to load models. Try again.'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [deviceId, reload]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const eligible = data?.configuration_allowed !== false && data?.device.is_active && data.device.enrollment_state !== 'retired';
  const valid = selection && selection.mode !== 'mixed' && kinds.every(kind => {
    const id = selection[`${kind}_model_id`];
    return !id || data?.models.some(row => row.id === id && row.available && row.kind === kind && row.location === selection.mode);
  });
  function close() { if (submitting.current) return; if (dirty) setDiscard(true); else onClose(); }
  function mode(value: ModelMode) {
    if (!selection || value === selection.mode) return;
    const next = { ...selection, mode: value };
    for (const kind of kinds) {
      const id = next[`${kind}_model_id`];
      if (!data?.models.some(row => row.id === id && row.location === value)) next[`${kind}_model_id`] = null;
    }
    setSelection(next); setDirty(true); setError(undefined);
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (loading || !selection || selection.mode === 'mixed' || !data || data.device.id !== deviceId || !valid || !eligible || submitting.current || uncertain) return;
    submitting.current = true; setBusy(true); setError(undefined);
    const revisions = Object.fromEntries(kinds.flatMap(kind => {
      const row = data.models.find(model => model.id === selection[`${kind}_model_id`]);
      return row ? [[row.id, row.revision]] : [];
    }));
    try {
      const { version, ...values } = selection;
      const result = await saveDeviceModels(deviceId, { ...values, mode: selection.mode, expected_version: version, model_revisions: revisions });
      if (result.error !== undefined) { setError(result.error); setUncertain(!!result.uncertain); return; }
      setDirty(false); onSaved(data.device.name);
    } catch { setUncertain(true); setError('The save result is uncertain. Reload to check the saved selections.'); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <>
    <Modal open size="md" title="Configure model" busy={busy} onClose={close}
      footer={<><Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button>
        <Button type="submit" form={formId} loading={busy} disabled={loading || !dirty || !valid || !eligible || uncertain}>Save</Button></>}>
      <div className="direct-device-models">
        {loading ? <p role="status">Loading models…</p> : <>
          {error && <Notice tone="danger" action={<Button variant="ghost" disabled={busy} onClick={() => setReload(n => n + 1)}>Reload</Button>}>{error}</Notice>}
          {data && selection && <>
            <p className="direct-device-name">{data.device.name}</p>
            {!eligible ? <Notice tone="info">{data.configuration_blocked_reason ?? (data.device.enrollment_state === 'retired' ? 'This registration is retired. Configure the current device registration.' : 'Activate this device before changing its models.')}</Notice> :
              <form id={formId} onSubmit={event => void save(event)}>
                <fieldset disabled={busy} className="direct-model-fields">
                  <div className="model-mode-control" role="group" aria-label="Run models on">
                    {(['local', 'cloud'] as const).map(value => <button type="button" key={value} aria-pressed={selection.mode === value} onClick={() => mode(value)}>{value === 'local' ? 'Local' : 'Cloud'}</button>)}
                  </div>
                  <p className="pms-hint">{selection.mode === 'local' ? 'Choose a configured local model. Install and run it on the device or its connected laptop before use.' : selection.mode === 'cloud' ? 'Runs through your configured cloud providers.' : 'Your existing mixed setup is preserved. Choose Local or Cloud to change it.'}</p>
                  {kinds.map(kind => {
                    const id = selection[`${kind}_model_id`] ?? '';
                    const rows = data.models.filter(row => row.kind === kind && (selection.mode === 'mixed' || row.location === selection.mode));
                    return <Select key={kind} label={MODEL_LABELS[kind]} value={id}
                      options={[{ value: '', label: 'None' }, ...rows.filter(row => row.available || row.id === id).map(row => ({ value: row.id, label: row.name + (row.available ? '' : ' — unavailable'), disabled: !row.available })),
                        ...(id && !rows.some(row => row.id === id) ? [{ value: id, label: 'Selected model unavailable', disabled: true }] : [])]}
                      hint={!rows.some(row => row.available) ? `No active ${selection.mode === 'mixed' ? '' : selection.mode + ' '}models configured. Add one in Models.` : undefined}
                      onChange={value => { setSelection({ ...selection, [`${kind}_model_id`]: value || null }); setDirty(true); setError(undefined); }} />;
                  })}
                  <p className="pms-hint">Choose None for anything this device does not need.</p>
                </fieldset>
              </form>}
          </>}
        </>}
      </div>
    </Modal>
    <ConfirmDialog open={discard} title="Discard model changes?" confirmLabel="Discard changes" onConfirm={onClose} onCancel={() => setDiscard(false)}>Your changes have not been saved.</ConfirmDialog>
  </>;
}
