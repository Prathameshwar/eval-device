'use client';
import { useId, useState, type FormEvent } from 'react';
import { Button, ConfirmDialog, Drawer, Notice, Select, TextField } from '@pms/ui';
import type { Plan, Subscription, SubscriptionDraft } from '@/lib/subscriptions';

const inputDate = (value: string | null) => value ? new Date(value).toISOString().slice(0, 19) : '';
export function SubscriptionEditor({ row, plans, onSave, onClose }: {
  row: Subscription; plans: Plan[]; onSave: (draft: SubscriptionDraft) => Promise<string | undefined>; onClose: () => void;
}) {
  const initial = { plan: row.subscription_plan_id, status: row.status, start: inputDate(row.starts_at), end: inputDate(row.ends_at), reference: row.reference ?? '', notes: row.notes ?? '' };
  const [draft, setDraft] = useState(initial); const [busy, setBusy] = useState(false); const [error, setError] = useState<string>(); const [discard, setDiscard] = useState(false);
  const form = useId(); const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  function close() { if (busy) return; if (dirty) setDiscard(true); else onClose(); }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    const start = draft.start ? new Date(draft.start + 'Z') : null; const end = draft.end ? new Date(draft.end + 'Z') : null;
    if ((start && !Number.isFinite(start.getTime())) || (end && !Number.isFinite(end.getTime())) || (start && end && end <= start)) { setError('The end must be after the start.'); return; }
    setBusy(true); setError(undefined);
    try { setError(await onSave({ subscription_plan_id: draft.plan, subscription_status: draft.status,
      subscription_starts_at: draft.start === initial.start ? row.starts_at : start?.toISOString() ?? null, subscription_ends_at: draft.end === initial.end ? row.ends_at : end?.toISOString() ?? null,
      subscription_reference: draft.reference.trim() || null, subscription_notes: draft.notes.trim() || null })); }
    catch { setError('Unable to confirm the result. Refresh before retrying.'); } finally { setBusy(false); }
  }
  const choices = plans.filter(plan => plan.is_active || plan.id === row.subscription_plan_id);
  return <>
    <Drawer open title={'Edit or renew ' + row.organization_name} onClose={close} footer={<><Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button><Button form={form} type="submit" loading={busy} disabled={!dirty}>Save subscription</Button></>}>
      <form id={form} onSubmit={submit}>
        {error && <Notice tone="danger">{error}</Notice>}
        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <Select label="Subscription plan" value={draft.plan} options={choices.map(p => ({ value: p.id, label: p.name + (p.is_active ? '' : ' (unavailable for new assignments)') }))} onChange={plan => setDraft(current => ({ ...current, plan }))} />
          <Select label="Recorded status" value={draft.status} options={['active', 'suspended', 'cancelled'].map(value => ({ value, label: value.charAt(0).toUpperCase() + value.slice(1) }))} onChange={status => setDraft(current => ({ ...current, status: status as Subscription['status'] }))} />
          <TextField label="Starts at (UTC)" type="datetime-local" step="1" value={draft.start} onChange={e => setDraft(current => ({ ...current, start: e.target.value }))} hint="Leave blank for no start restriction." />
          <TextField label="Ends at (UTC)" type="datetime-local" step="1" value={draft.end} onChange={e => setDraft(current => ({ ...current, end: e.target.value }))} hint="End is exclusive. Leave blank for no expiry. Extend this date to record a renewal." />
          <TextField label="Manual reference" maxLength={256} value={draft.reference} onChange={e => setDraft(current => ({ ...current, reference: e.target.value }))} hint="Optional internal reference. Do not enter payment credentials." />
          <TextField label="Internal notes" maxLength={2000} value={draft.notes} onChange={e => setDraft(current => ({ ...current, notes: e.target.value }))} hint="Visible only to platform administrators." />
          <Notice tone="info">Status and dates are tracked only. They do not block processing. Existing plan seat limits still apply; no payment is collected.</Notice>
        </fieldset>
      </form>
    </Drawer>
    <ConfirmDialog open={discard} title="Discard subscription changes?" confirmLabel="Discard changes" onConfirm={onClose} onCancel={() => setDiscard(false)}>Your changes have not been saved.</ConfirmDialog>
  </>;
}

export function SubscriptionPlanEditor({ plan, onSave, onClose }: { plan: Plan; onSave: (plan: Plan) => Promise<string | undefined>; onClose: () => void }) {
  const [draft, setDraft] = useState(plan); const [busy, setBusy] = useState(false); const [error, setError] = useState<string>(); const [confirm, setConfirm] = useState(false); const [discard, setDiscard] = useState(false);
  const form = useId(); const dirty = JSON.stringify(draft) !== JSON.stringify(plan);
  function close() { if (busy) return; if (dirty) setDiscard(true); else onClose(); }
  async function save() { if (busy) return; setBusy(true); setError(undefined); try { const result = await onSave(draft); setError(result); } catch { setError('Unable to confirm the result. Refresh before retrying.'); } finally { setBusy(false); } }
  return <>
    <Drawer open title={'Edit ' + plan.name + ' plan'} onClose={close} footer={<><Button variant="ghost" disabled={busy} onClick={close}>Cancel</Button><Button form={form} type="submit" disabled={busy || !dirty}>Review plan changes</Button></>}>
      <form id={form} onSubmit={event => { event.preventDefault(); setConfirm(true); }}>
        <fieldset disabled={busy} className="pms-console__tenant-fieldset">
          <TextField label="Plan name" required maxLength={256} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} />
          <TextField label="Price amount" required type="number" min="0" max="999999999999.99" step="0.01" value={draft.price_amount} onChange={e => setDraft({ ...draft, price_amount: e.target.value })} />
          <Select label="Currency" value={draft.currency} options={['INR', 'USD'].map(value => ({ value, label: value }))} onChange={value => setDraft({ ...draft, currency: value as Plan['currency'] })} />
          <Select label="Billing period" value={draft.billing_period} options={['unspecified', 'monthly', 'annual', 'one_time'].map(value => ({ value, label: value.replaceAll('_', ' ') }))} onChange={value => setDraft({ ...draft, billing_period: value as Plan['billing_period'] })} />
          <TextField label="User seats" required type="number" min="1" max="1000000" step="1" value={draft.max_users} onChange={e => setDraft({ ...draft, max_users: Number(e.target.value) })} />
          <TextField label="Device seats" required type="number" min="1" max="1000000" step="1" value={draft.max_devices} onChange={e => setDraft({ ...draft, max_devices: Number(e.target.value) })} />
          <Select label="Available for new assignments" value={String(draft.is_active)} options={[{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }]} onChange={value => setDraft({ ...draft, is_active: value === 'true' })} />
          <Notice tone="warning">Changes apply to every tenant assigned this plan. Lower limits must fit existing usage. Currency changes do not convert the amount. Prices are informational; this does not charge anyone.</Notice>
        </fieldset>
      </form>
    </Drawer>
    <ConfirmDialog open={confirm} title="Apply catalog changes?" confirmLabel="Save plan" busy={busy} error={error} onConfirm={() => void save()} onCancel={() => { setConfirm(false); setError(undefined); }}>Update {plan.name} for every assigned tenant?</ConfirmDialog>
    <ConfirmDialog open={discard} title="Discard plan changes?" confirmLabel="Discard changes" onConfirm={onClose} onCancel={() => setDiscard(false)}>Your changes have not been saved.</ConfirmDialog>
  </>;
}
