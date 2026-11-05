'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { Button, ChevronDownIcon, ChevronRightIcon, ChevronUpIcon, ClockIcon, CloseIcon, ConfirmDialog, CustomersIcon,
  DragHandleIcon, EditIcon, MonitorIcon, Notice, PageHeader, PlusIcon, RefreshIcon, SearchIcon, Select,
  Tabs, tabButtonId, TextField, TrashIcon, useDialogA11y } from '@pms/ui';
import { historyOptions, type SessionOptions } from '@/lib/history-actions';
import { callAction } from '@/lib/call-action';
import type { ApiResult } from '@/lib/directory-api';
import {
  readQueue, queueLearners, planSessions, changeQueue, editQueuedSession, endQueuedSession,
  type Assignment, type QueuedSession, type SessionQueue,
} from '@/lib/session-queue-actions';
import { sessionLanguage } from '@/lib/session-start';
import styles from './SessionQueueWorkspace.module.css';
import { RecordingDetails } from './SessionArchives';
import { SessionHistory } from './SessionHistory';
import { SessionDetails } from './SessionDetails';
import { SessionDate, SessionEmpty, SessionLoading, SessionStatus } from './SessionPresentation';

function Modal({ title, onClose, children, planner = false, busy = false }: {
  title: string; onClose: () => void; children: React.ReactNode; planner?: boolean; busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const { panelRef, onKeyDown } = useDialogA11y({ open: true, onClose, dismissible: !busy });
  useEffect(() => { ref.current?.showModal(); }, []);
  useEffect(() => { ref.current?.querySelector('h2')?.focus(); }, [title]);
  return <dialog ref={ref} className={`${styles.dialog} ${planner ? styles.plannerDialog : ''}`}
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }} aria-labelledby={titleId}>
    <div ref={panelRef} className={styles.dialogSurface} tabIndex={-1} onKeyDown={onKeyDown}>
    <div className={styles.dialogHeader}><h2 id={titleId} tabIndex={-1}>{title}</h2>
      <Button variant="ghost" disabled={busy} aria-label="Close panel" onClick={onClose}><CloseIcon size={20} /></Button></div>
    {children}
    </div>
  </dialog>;
}

function Planner({ contextId, deviceId, options, edit, revision, onClose, onSaved }: {
  contextId: string; deviceId: string; options: SessionOptions; edit?: QueuedSession; revision: number;
  onClose: () => void; onSaved: (queue: SessionQueue, deviceId: string) => void;
}) {
  const first = options.scenarios[0];
  const [defaults, setDefaults] = useState<Assignment>(edit ?? { learner_id: '', scenario_id: first?.id ?? '',
    language: first?.languages[0] ?? '', duration_seconds: 300 });
  const [people, setPeople] = useState<{ id: string; name: string }[]>();
  const [rows, setRows] = useState<Assignment[]>(edit ? [edit] : []);
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [targetDeviceId, setTargetDeviceId] = useState(deviceId);
  const [confirming, setConfirming] = useState(false);
  const [changingDevice, setChangingDevice] = useState(false);
  const knownPeople = useRef(new Map<string, string>());
  const targetDevice = options.devices.find(row => row.id === targetDeviceId);
  const formId = useId();
  const visiblePeople = people?.filter(person => person.name.toLowerCase().includes(search.trim().toLowerCase()));
  const totalMinutes = rows.reduce((sum, row) => sum + row.duration_seconds / 60, 0);
  const request = useRef<{ content: string; key: string } | undefined>(undefined);
  // Polling must not make an open, stale edit appear current.
  const editRevision = useRef(revision);
  const submitting = useRef(false);
  useEffect(() => {
    let live = true;
    setPeople(undefined); setError(undefined);
    void callAction(() => queueLearners(contextId, targetDeviceId)).then(result => {
      if (!live) return;
      if (result.error !== undefined) setError(result.error);
      else {
        for (const person of result.value) knownPeople.current.set(person.id, person.name);
        setPeople(result.value.sort((a, b) => a.name.localeCompare(b.name)));
      }
    });
    return () => { live = false; };
  }, [contextId, targetDeviceId]);

  function changeDevice() {
    setConfirming(false); setChangingDevice(true); setError(undefined);
  }
  function validDraft() {
    if (!rows.length || !people || !targetDevice) return false;
    if (!edit && rows.some(row => !people.some(person => person.id === row.learner_id))) {
      setError('Some selected trainees are unavailable for this device. Remove them or choose another device.');
      return false;
    }
    if (rows.some(row => !row.learner_id || !options.scenarios.find(s => s.id === row.scenario_id)?.languages.includes(row.language)
      || !Number.isInteger(row.duration_seconds) || row.duration_seconds < 30 || row.duration_seconds > 600)) {
      setError('Choose a trainee, case, available language and duration between 0.5 and 10 minutes for every row.');
      return false;
    }
    return true;
  }

  function settings(value: Assignment, update: (value: Assignment) => void, prefix: string) {
    const scenario = options.scenarios.find(row => row.id === value.scenario_id);
    return <div className={styles.settings}>
      <Select label="Practice case" aria-label={prefix + 'Practice case'} value={value.scenario_id} required
        options={options.scenarios.map(row => ({ value: row.id, label: row.title }))}
        onChange={scenario_id => { const languages = options.scenarios.find(row => row.id === scenario_id)?.languages ?? [];
          update({ ...value, scenario_id, language: languages.includes(value.language) ? value.language : languages[0] ?? '' }); }} />
      <Select label="Language" aria-label={prefix + 'Language'} value={value.language} required
        options={(scenario?.languages ?? []).map(code => ({ value: code, label: sessionLanguage(code) }))}
        onChange={language => update({ ...value, language })} />
      <TextField label="Minutes" aria-label={prefix + 'Minutes'} type="number" min={0.5} max={10} step={0.5} required
        value={String(value.duration_seconds / 60)} onChange={event => update({ ...value, duration_seconds: Number(event.target.value) * 60 })} />
    </div>;
  }
  function moveDraft(index: number, direction: number) {
    setRows(current => {
      const next = [...current];
      const target = index + direction;
      if (target < 0 || target >= next.length) return current;
      [next[index], next[target]] = [next[target]!, next[index]!];
      return next;
    });
  }
  async function save() {
    if (submitting.current || !validDraft() || (!edit && !confirming)) return;
    const items = rows.map(({ learner_id, scenario_id, language, duration_seconds }) => ({ learner_id, scenario_id, language, duration_seconds }));
    const content = JSON.stringify({ device_id: targetDeviceId, items });
    if (request.current?.content !== content) request.current = { content, key: crypto.randomUUID() };
    submitting.current = true; setBusy(true); setError(undefined);
    const result = await callAction(() => edit
      ? editQueuedSession(contextId, targetDeviceId, edit.id, { ...items[0]!, expected_revision: editRevision.current })
      : planSessions(contextId, targetDeviceId, { request_key: request.current!.key, items }));
    submitting.current = false; setBusy(false);
    if (result.error !== undefined) setError(result.error);
    else onSaved(result.value, targetDeviceId);
  }
  if (confirming) return <Modal title="Confirm device assignment" planner busy={busy} onClose={onClose}>
    <div className={styles.plannerIntro}><p>Review the device and sessions before adding them to its queue.</p></div>
    <div className={styles.plannerBody}>
      <section className={styles.assignmentTarget} aria-label="Assignment device">
        <MonitorIcon size={24} /><div><span>Assign to device</span><h3>{targetDevice?.name}</h3>
          <p>Device ID: {targetDeviceId}</p></div>
        <Button variant="ghost" disabled={busy} onClick={changeDevice}>Change device</Button>
      </section>
      <ol className={styles.assignmentReview} aria-label="Sessions to assign">{rows.map(row => <li key={row.learner_id}>
        <strong>{knownPeople.current.get(row.learner_id) ?? 'Trainee'}</strong>
        <span>{options.scenarios.find(scenario => scenario.id === row.scenario_id)?.title}</span>
        <span>{sessionLanguage(row.language)} · {row.duration_seconds / 60} min</span>
      </li>)}</ol>
      <p className={styles.helper}>The trainee starts with Begin session in Human-test on this device.</p>
    </div>
    <div className={styles.panelFooter}>
      {error && <Notice tone="danger" title="Could not save sessions">{error}</Notice>}
      <div className={styles.footerRow}><p className={styles.selectionSummary}>
        <strong>{rows.length} {rows.length === 1 ? 'session' : 'sessions'}</strong><span>{totalMinutes} min of planned practice</span>
      </p><div className={styles.actions}>
        <Button variant="ghost" disabled={busy} onClick={() => { setConfirming(false); setError(undefined); }}>Back</Button>
        <Button loading={busy} loadingLabel="Adding sessions…" onClick={() => void save()}>Confirm & add to queue</Button>
      </div></div>
    </div>
  </Modal>;
  return <Modal title={edit ? 'Edit waiting session' : 'Plan sessions'} planner busy={busy} onClose={onClose}>
    <div className={styles.plannerIntro}>
      <p>{edit ? 'Update the practice settings for this trainee.' : 'Choose trainees and prepare their practice, in the order you want.'}</p>
      {changingDevice && !edit ? <Select label="Assign to device" value={targetDeviceId} disabled={busy} autoFocus
        options={options.devices.map(row => ({ value: row.id, label: row.name }))}
        onChange={value => { if (value !== targetDeviceId) { setPeople(undefined); setTargetDeviceId(value); setError(undefined); } }} />
        : <div className={styles.actions}><span className={styles.deviceChip}><MonitorIcon size={16} /><span>Device: <strong>{targetDevice?.name}</strong></span></span>
          {!edit && <Button variant="ghost" disabled={busy} onClick={changeDevice}>Change device</Button>}</div>}
    </div>
    <form id={formId} className={styles.plannerForm} onSubmit={event => {
      event.preventDefault();
      if (edit) void save();
      else if (validDraft()) { setError(undefined); setConfirming(true); }
    }}>
      <div className={styles.plannerBody}>
        <fieldset disabled={busy} className={styles.planner} aria-label="Session assignments">
          {!edit && <section className={styles.defaults} aria-label="Default practice settings">
            <div className={styles.sectionHeading}><h3>Default practice settings</h3><span className={styles.sectionNote}>For new selections</span></div>
            {settings(defaults, setDefaults, '')}
            <p className={styles.helper}>Applied to trainees you select next. You can adjust each session below.</p>
          </section>}
          <div className={edit ? styles.editGrid : styles.plannerGrid}>
            {!edit && <section className={styles.traineePicker} aria-label="Choose trainees">
              <div className={styles.sectionHeading}><h3>Choose trainees</h3><span className={styles.countBadge}>{rows.length} / 50</span></div>
              <TextField label="Find trainees" placeholder="Search by name" leading={<SearchIcon size={16} />}
                value={search} onChange={event => setSearch(event.target.value)} />
              <div className={styles.people} role="group" aria-label="Available trainees">
                {!people ? <p className={styles.pickerMessage} role="status">{error ? 'Trainees could not be loaded. Close and try again.' : 'Loading trainees…'}</p>
                  : !people.length ? <p className={styles.pickerMessage}>No active trainees available for this device.</p>
                  : !visiblePeople?.length ? <p className={styles.pickerMessage} role="status">No trainees match “{search.trim()}”. Try another name.</p>
                  : visiblePeople.map(person => {
                    const selected = rows.some(row => row.learner_id === person.id);
                    return <label key={person.id} className={styles.person} data-selected={selected}>
                      <input type="checkbox" checked={selected} disabled={rows.length >= 50 && !selected}
                        onChange={event => setRows(current => event.target.checked ? [...current, { ...defaults, learner_id: person.id }]
                          : current.filter(row => row.learner_id !== person.id))} />
                      <span className={styles.personName}>{person.name}</span>
                      {selected && <span className={styles.selectedLabel} aria-hidden="true">Added</span>}
                    </label>;
                  })}
              </div>
              <p className={styles.helper}>{rows.length >= 50 ? '50 trainees selected. Remove one to add another.' : 'Select trainees in the order they will practise.'}</p>
            </section>}
            <section className={styles.queuePreview} aria-label={edit ? 'Assignment' : 'Planned session order'}>
              <div className={styles.sectionHeading}><h3>{edit ? 'Assignment' : 'Session order'}</h3>
                {!edit && <span className={styles.countBadge} role="status">{rows.length} selected</span>}</div>
              {!rows.length && <div className={styles.queueEmpty}><span className={styles.emptyIcon}><CustomersIcon size={28} /></span>
                <h4>Your queue starts here</h4><p>Select trainees to add their sessions.<br />Then adjust settings or change the order.</p></div>}
              <div className={styles.draftList}>{rows.map((row, index) => {
                const name = knownPeople.current.get(row.learner_id) ?? edit?.learner_name ?? 'Trainee';
                return <section key={row.learner_id} className={styles.draftRow} aria-label={`Session ${index + 1}: ${name}`}>
                  <div className={styles.draftHeading}><span className={styles.orderNumber}>{index + 1}</span><h4>{name}</h4>
                    {!edit && <div className={styles.draftActions}>
                      <Button variant="ghost" disabled={index === 0} aria-label={`Move trainee ${index + 1} up`} title="Move earlier" onClick={() => moveDraft(index, -1)}><ChevronUpIcon size={16} /></Button>
                      <Button variant="ghost" disabled={index === rows.length - 1} aria-label={`Move trainee ${index + 1} down`} title="Move later" onClick={() => moveDraft(index, 1)}><ChevronDownIcon size={16} /></Button>
                      <Button variant="ghost" aria-label={`Remove trainee ${index + 1}`} title="Remove trainee" onClick={() => setRows(rows.filter((_, i) => i !== index))}><TrashIcon size={16} /></Button>
                    </div>}
                  </div>
                  {settings(row, next => setRows(rows.map((item, i) => i === index ? next : item)), `Trainee ${index + 1} · `)}
                </section>;
              })}</div>
            </section>
          </div>
          <aside className={styles.timingNote} aria-label="Session timing">
            <ClockIcon size={18} /><div><p><strong>Ready for 24 hours.</strong> Sessions expire 24 hours after being queued, even if started. Editing or reordering does not extend this.</p>
              <p>The practice timer starts when the trainee clicks <strong>Begin session</strong> in Human-test.</p></div>
          </aside>
        </fieldset>
      </div>
      <div className={styles.panelFooter}>
        {error && <Notice tone="danger" title="Could not save sessions">{error}</Notice>}
        <div className={styles.footerRow}><p className={styles.selectionSummary}>
          <strong>{rows.length ? `${rows.length} ${rows.length === 1 ? 'session' : 'sessions'}` : 'No trainees selected'}</strong>
          <span>{rows.length ? `${totalMinutes} min of planned practice` : 'Select a trainee to continue'}</span>
        </p><div className={styles.actions}><Button variant="ghost" disabled={busy} onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={busy} loadingLabel="Saving sessions…" disabled={!rows.length || !people || !targetDevice}>
            {!edit && <PlusIcon size={16} />}{edit ? 'Save changes' : `Add ${rows.length} to queue`}</Button></div></div>
      </div>
    </form>
  </Modal>;
}

export function SessionQueueWorkspace({ contextId, initialPlan = false, canManage = true }: {
  contextId: string; initialPlan?: boolean; canManage?: boolean;
}) {
  const [options, setOptions] = useState<SessionOptions>();
  const [deviceId, setDeviceId] = useState('');
  const [queue, setQueue] = useState<SessionQueue>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [planner, setPlanner] = useState(initialPlan);
  const [editing, setEditing] = useState<QueuedSession>();
  const [ending, setEnding] = useState<QueuedSession>();
  const [inspecting, setInspecting] = useState<string>();
  const [inspectingArchive, setInspectingArchive] = useState<string>();
  const [tab, setTab] = useState<'queue' | 'history'>(canManage ? 'queue' : 'history');
  const [reload, setReload] = useState(0);
  const drag = useRef<string | undefined>(undefined);
  const mutating = useRef(false);
  const generation = useRef(0);
  const panelId = useId();
  useEffect(() => {
    if (!canManage) return;
    let live = true;
    void callAction(() => historyOptions(contextId)).then(response => {
      if (!live) return;
      if (response.error !== undefined) setError(response.error);
      else { setOptions(response.value); setDeviceId(current => current || response.value.devices[0]?.id || ''); }
    });
    return () => { live = false; };
  }, [contextId, canManage, reload]);
  useEffect(() => {
    setQueue(undefined);
    const epoch = ++generation.current;
    if (!deviceId || !canManage) return;
    let live = true;
    async function refresh() {
      if (mutating.current) return;
      const response = await callAction(() => readQueue(contextId, deviceId));
      if (!live || epoch !== generation.current || mutating.current) return;
      if (response.error !== undefined) setError(response.error);
      else setQueue(current => !current || response.value.revision >= current.revision ? response.value : current);
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => { live = false; clearInterval(timer); };
  }, [contextId, deviceId, canManage, reload]);
  async function mutate(action: () => Promise<ApiResult<SessionQueue>>) {
    if (mutating.current) return;
    mutating.current = true; setBusy(true); setError(undefined);
    const response = await callAction(action);
    mutating.current = false; setBusy(false);
    if (response.error !== undefined) setError(response.error);
    else { setQueue(response.value); setEnding(undefined); }
  }
  const waiting = queue?.items.filter(row => row.status === 'queued') ?? [];
  const active = queue?.items.find(row => ['active', 'stopping'].includes(row.status));
  function move(id: string, to: number) {
    if (!queue || to < 0 || to >= waiting.length) return;
    const order = waiting.map(row => row.id);
    const from = order.indexOf(id);
    if (from < 0 || from === to) return;
    order.splice(from, 1); order.splice(to, 0, id);
    void mutate(() => changeQueue(contextId, deviceId, { expected_revision: queue.revision, order, paused: queue.paused }));
  }
  return <div className={'pms-page ' + styles.page}>
    <PageHeader overline="Practice" title="Sessions" lede="Prepare each practice session. Follow the queue, then review conversations and recordings."
      actions={canManage ? <Button disabled={!deviceId || !queue || !options?.scenarios.length || busy} onClick={() => setPlanner(true)}><PlusIcon size={18} />Plan sessions</Button> : undefined} />
    {error && !ending && <Notice tone="danger" title="Sessions need attention" action={<Button variant="ghost" onClick={() => { setError(undefined); setReload(n => n + 1); }}><RefreshIcon size={16} />Refresh</Button>}>{error}</Notice>}
    <div className={styles.tabBar}>
      <Tabs label="Session views" panelId={panelId} active={tab} onChange={id => setTab(id as typeof tab)} tabs={[
        ...(canManage ? [{ id: 'queue', label: 'Device queue' }] : []),
        { id: 'history', label: 'Session history' },
      ]} />
    </div>
    <div id={panelId} role="tabpanel" aria-labelledby={tabButtonId(tab, panelId)} className={styles.tabPanel}>
    {tab === 'queue' && <section className={styles.viewSection} aria-label="Device session queue">
      <div className={styles.deviceToolbar}><Select label="Practice device" aria-label="Device" value={deviceId} disabled={busy || planner || !!editing || !!ending}
        options={options?.devices.length ? options.devices.map(row => ({ value: row.id, label: row.name })) : [{ value: '', label: 'No enrolled device available' }]}
        loading={!options && !error} onChange={id => { setDeviceId(id); setError(undefined); }} />
        {queue && <div className={styles.connectionInfo}><span className={styles.connectionBadge} data-connected={queue.connected}>
          <span aria-hidden="true" />{queue.connected ? 'Human-test connected' : 'Device offline'}</span>
          <span>Queue updates automatically</span></div>}
      </div>
      {!options ? !error && <SessionLoading>Loading devices and practice cases…</SessionLoading>
        : !deviceId ? <SessionEmpty title="Connect a practice device">Enroll and activate a device to start planning sessions.</SessionEmpty>
        : !queue ? !error && <SessionLoading>Loading session queue…</SessionLoading> : <>
          <div className={styles.queueOverview}>
            <section className={styles.currentCard} aria-label="Active session">
              <div className={styles.currentHeading}><span className={styles.overline}>CURRENT PRACTICE</span>
                {active ? <SessionStatus status={active.status} /> : <span className={styles.countBadge}>{queue.runtime_state === 'standalone' ? 'Unassigned' : 'No active session'}</span>}</div>
              {active ? <><h2>{active.learner_name}</h2><p className={styles.practiceTitle}>{active.scenario_title}</p>
                <div className={styles.practiceMeta}><span>{sessionLanguage(active.language)}</span><span><ClockIcon size={15} />{active.duration_seconds / 60} min</span></div>
                <dl className={styles.currentDates}><div><dt>Started</dt><dd><SessionDate value={active.started_at} /></dd></div>
                  <div><dt>Assignment expires</dt><dd><SessionDate value={active.expires_at} /></dd></div></dl>
                {active.status === 'stopping' && <p role="status" className={styles.inlineHelp}>Stopping — awaiting device confirmation</p>}
                <div className={styles.actions}><Button variant="ghost" onClick={() => setInspecting(active.id)}>View session<ChevronRightIcon size={16} /></Button>
                  <Button variant="danger" disabled={busy || active.status === 'stopping'} onClick={() => { setError(undefined); setEnding(active); }}>End session</Button></div></>
                : <><span className={styles.currentIcon}><MonitorIcon size={28} /></span>
                  <h2>{queue.runtime_state === 'standalone' ? 'Standalone practice' : !queue.connected ? 'Waiting for the device' : queue.paused ? 'Queue is paused' : 'Ready for the next trainee'}</h2>
                  <p className={styles.currentDescription}>{queue.runtime_state === 'standalone' ? 'No trainee assigned. Queued sessions wait until this practice finishes.'
                    : !queue.connected ? 'Open Human-test and connect this device. You can prepare its queue while it is offline.'
                    : queue.paused ? 'Resume the queue when you are ready for the next trainee.' : 'The next trainee starts with Begin session in Human-test.'}</p></>}
            </section>
            <aside className={styles.queueSummary} aria-label="Queue summary"><h3>Up next</h3>
              <div className={styles.summaryNumbers}><div><strong>{waiting.length}</strong><span>Waiting sessions</span></div>
                <div><strong>{waiting.reduce((sum, row) => sum + row.duration_seconds / 60, 0)}<small> min</small></strong><span>Planned practice</span></div></div>
              {waiting[0] ? <div className={styles.nextTrainee}><span>Next trainee</span><strong>{waiting[0].learner_name}</strong><p>{waiting[0].scenario_title}</p></div>
                : <p className={styles.sectionDescription}>Add trainees to prepare their practice in advance.</p>}
              <p className={styles.expiryHint}><ClockIcon size={16} /><span>Assignments expire after 24 hours, whether started or waiting.</span></p>
            </aside>
          </div>
          <section aria-label="Waiting sessions" className={styles.queueSection}>
            <div className={styles.viewHeading}><div><h2>Waiting queue <span className={styles.countBadge}>{waiting.length}</span></h2>
              <p>Move trainees into order and adjust their practice before they begin.</p></div>
              <Button variant="ghost" disabled={busy} onClick={() => void mutate(() => changeQueue(contextId, deviceId, {
                expected_revision: queue.revision, order: waiting.map(row => row.id), paused: !queue.paused,
              }))}>{queue.paused ? 'Resume queue' : 'Pause queue'}</Button></div>
            {queue.paused && <Notice tone="info" title="Queue paused">The active session can finish. Waiting sessions will not begin until the queue resumes.</Notice>}
            {!waiting.length ? <SessionEmpty title="No sessions waiting" action={<Button variant="ghost" disabled={!options.scenarios.length || busy} onClick={() => setPlanner(true)}><PlusIcon size={16} />Add trainees</Button>}>
              Plan a session for each trainee. Human-test can also run standalone practice without an assignment.</SessionEmpty>
              : <><p className={styles.inlineHelp}>Drag a row or use its arrows to change the order. Every assignment expires 24 hours after it was added.</p>
                <div className={styles.tableWrap}><table className={`${styles.table} ${styles.responsiveTable}`}>
                  <caption className={styles.srOnly}>Waiting sessions in practice order</caption>
                  <thead><tr><th scope="col">Order</th><th scope="col">Trainee</th><th scope="col">Practice</th><th scope="col">Expires</th><th scope="col">Manage</th></tr></thead>
                  <tbody>{waiting.map((row, index) => <tr key={row.id} draggable={!busy}
                    onDragStart={() => { drag.current = row.id; }} onDragEnd={() => { drag.current = undefined; }} onDragOver={event => event.preventDefault()}
                    onDrop={event => { event.preventDefault(); if (drag.current) move(drag.current, index); drag.current = undefined; }}>
                    <td data-label="Order"><span className={styles.queuePosition}><DragHandleIcon size={16} />{String(index + 1).padStart(2, '0')}</span></td>
                    <td data-label="Trainee"><strong>{row.learner_name}</strong></td>
                    <td data-label="Practice">{row.scenario_title}<small>{sessionLanguage(row.language)} · {row.duration_seconds / 60} min</small></td>
                    <td data-label="Expires"><SessionDate value={row.expires_at} /></td>
                    <td className={styles.cellActions}><div className={styles.queueActions}>
                      <div className={styles.orderActions}><Button variant="ghost" disabled={busy || index === 0} aria-label={`Move ${row.learner_name} up`} title="Move earlier" onClick={() => move(row.id, index - 1)}><ChevronUpIcon size={16} /></Button>
                        <Button variant="ghost" disabled={busy || index === waiting.length - 1} aria-label={`Move ${row.learner_name} down`} title="Move later" onClick={() => move(row.id, index + 1)}><ChevronDownIcon size={16} /></Button></div>
                      <Button variant="ghost" disabled={busy} onClick={() => setEditing(row)}><EditIcon size={15} />Edit</Button>
                      <Button variant="ghost" disabled={busy} onClick={() => { setError(undefined); setEnding(row); }}><TrashIcon size={15} />Remove</Button>
                    </div></td>
                  </tr>)}</tbody></table></div></>}
          </section>
        </>}
    </section>}
    {tab === 'history' && <SessionHistory key={contextId} contextId={contextId} onInspect={(id, kind) => {
      if (kind === 'standalone') setInspectingArchive(id); else setInspecting(id);
    }} />}
    </div>
    {(planner || editing) && options && deviceId && queue && <Planner key={contextId} contextId={contextId} deviceId={deviceId} options={options} edit={editing} revision={queue.revision}
      onClose={() => { setPlanner(false); setEditing(undefined); }} onSaved={(value, targetDeviceId) => {
        setDeviceId(targetDeviceId);
        setQueue(current => targetDeviceId !== deviceId || !current || value.revision >= current.revision ? value : current);
        setPlanner(false); setEditing(undefined); setError(undefined);
      }} />}
    {ending && <ConfirmDialog open title={ending.status === 'queued' ? 'Remove waiting session?' : 'End this session?'} tone="danger" busy={busy} error={error}
      cancelLabel="Keep session" confirmLabel={ending.status === 'queued' ? 'Remove session' : 'End session'} onCancel={() => { setEnding(undefined); setError(undefined); }}
      onConfirm={() => void mutate(() => endQueuedSession(contextId, deviceId, ending.id))}>
      <p><strong>{ending.learner_name}</strong> · {ending.scenario_title}</p>
      <p>{ending.status === 'queued' ? 'This assignment will be cancelled. Other waiting sessions keep their order.' : 'Human-test will stop this session. The next trainee must click Begin session before practice starts.'}</p>
    </ConfirmDialog>}
    {inspecting && <SessionDetails key={contextId + inspecting} contextId={contextId} id={inspecting} onClose={() => setInspecting(undefined)}
      onRecordings={() => { setInspecting(undefined); setTab('history'); }} />}
    {inspectingArchive && <RecordingDetails key={contextId + inspectingArchive} contextId={contextId} id={inspectingArchive} title="Session details" onClose={() => setInspectingArchive(undefined)} />}
  </div>;
}
