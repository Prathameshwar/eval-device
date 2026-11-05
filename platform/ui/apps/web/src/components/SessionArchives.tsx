'use client';

import { useEffect, useRef, useState } from 'react';
import { Button, ChevronRightIcon, DownloadIcon, InfoIcon, Modal, Notice, DocumentIcon, RefreshIcon } from '@pms/ui';
import { listArchives, readArchive, archiveTurns, type Archive, type ArchiveTurn } from '@/lib/session-archive-actions';
import { callAction } from '@/lib/call-action';
import { ConversationMessage, SessionDate, SessionEmpty, SessionLoading, SessionStatus } from './SessionPresentation';
import styles from './SessionQueueWorkspace.module.css';

const kinds: Record<string, string> = { microphone: 'Trainee audio', patient_audio: 'Patient audio', video: 'Camera video' };

export function SessionRecordings({ contextId, archive }: { contextId: string; archive: Archive }) {
  const recordings = archive.items.filter(item => item.kind !== 'turn');
  return <section className={styles.detailSection} aria-label="Session recordings"><div className={styles.sectionHeading}><h3>Recordings</h3><span className={styles.countBadge}>{recordings.length} {recordings.length === 1 ? 'segment' : 'segments'}</span></div>
            <p className={styles.sectionDescription}>Private audio and enabled camera video. Downloads remain available until your organization's retention deadline.</p>
            {!recordings.length ? <SessionEmpty title="No recording segments yet">Only captured media is listed. The device may still be uploading, or media capture may not have been enabled.</SessionEmpty>
              : <ul className={styles.recordingGrid}>{recordings.map(item => <li key={item.id} className={styles.recordingCard}>
                <DocumentIcon size={20} /><h4>{kinds[item.kind] ?? 'Recording'}</h4><p>Segment {item.sequence + 1} · {(item.byte_size / 1048576).toFixed(1)} MB</p>
                {item.available ? <a href={'/api/session-recordings?context=' + encodeURIComponent(contextId) + '&archive=' + archive.id + '&item=' + item.id}><DownloadIcon size={16} />Download recording</a>
                  : <p>Pending upload or retention expired</p>}
              </li>)}</ul>}
          </section>;
}

export function RecordingDetails({ contextId, id, onClose, title = 'History & recordings' }: { contextId: string; id: string; onClose: () => void; title?: string }) {
  const [selected, setSelected] = useState<Archive>();
  const [turns, setTurns] = useState<ArchiveTurn[]>([]);
  const [offset, setOffset] = useState<number | null>(null);
  const [error, setError] = useState<string>();
  const [turnError, setTurnError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const paging = useRef(false);
  useEffect(() => {
    const epoch = ++generation.current;
    setLoading(true); setError(undefined); setTurnError(undefined); setSelected(undefined);
    setTurns([]); setOffset(null); setMore(false); paging.current = false;
    void Promise.all([callAction(() => readArchive(contextId, id)), callAction(() => archiveTurns(contextId, id))]).then(([detail, history]) => {
      if (epoch !== generation.current) return;
      setLoading(false);
      if (detail.error !== undefined) setError(detail.error); else setSelected(detail.value);
      if (history.error !== undefined) setTurnError(history.error);
      else { setTurns(history.value.items); setOffset(history.value.next_offset); }
    });
    return () => { generation.current++; };
  }, [contextId, id, revision]);
  async function loadMore() {
    if (paging.current || offset === null) return;
    const epoch = generation.current;
    paging.current = true; setMore(true); setTurnError(undefined);
    const result = await callAction(() => archiveTurns(contextId, id, offset));
    if (epoch !== generation.current) return;
    paging.current = false; setMore(false);
    if (result.error !== undefined) setTurnError(result.error);
    else { setTurns(current => [...new Map([...current, ...result.value.items].map(turn => [turn.turn_key, turn])).values()]); setOffset(result.value.next_offset); }
  }
  return <Modal open title={title} size="lg" onClose={onClose} footer={<>
    <Button variant="ghost" disabled={loading || more} onClick={() => setRevision(n => n + 1)}><RefreshIcon size={16} />Refresh details</Button>
    <Button onClick={onClose}>Done</Button>
  </>}>
    <section className={styles.detailContent} aria-label="Selected recording session">
      {loading ? <SessionLoading>Loading history and recordings…</SessionLoading>
        : error ? <Notice tone="danger" title="Could not load recording session">{error}</Notice> : selected && <>
          <div className={styles.detailHero}><div><span className={styles.overline}>{selected.assigned_session_id ? 'ASSIGNED PRACTICE' : 'STANDALONE PRACTICE'}</span>
            <h3>{selected.learner_name}</h3><p>{selected.scenario_title}</p></div><SessionStatus status={selected.sync_status} /></div>
          <dl className={styles.detailFacts}><div><dt>Recorded</dt><dd><SessionDate value={selected.created_at} /></dd></div>
            <div><dt>Saved items</dt><dd>{selected.received_items}{selected.expected_items !== null ? ` of ${selected.expected_items}` : ''}</dd></div>
            <div><dt>Capture summary</dt><dd>{selected.expected_items === null ? 'Awaiting device' : 'Received'}</dd></div>
            {selected.media_expires_at && <div><dt>Recording retention deadline</dt><dd><SessionDate value={selected.media_expires_at} /></dd></div>}
            {selected.upload_until && <div><dt>Result upload deadline</dt><dd><SessionDate value={selected.upload_until} /></dd></div>}
          </dl>
          {selected.sync_status === 'incomplete' && <Notice tone="warning" title="Some capture data is missing">Available recordings are preserved. A device interruption or local save failure prevented complete capture.</Notice>}
          {(selected.transfer_status ?? selected.sync_status) === 'pending' && <Notice tone="info" title="Uploads are still pending">Saved items are available now. The device retries remaining results and recordings while their upload and retention deadlines allow it.</Notice>}
          {(selected.transfer_status ?? selected.sync_status) === 'upload_expired' && <Notice tone="warning" title="The upload window has ended">Further uploads are no longer accepted. Available recordings remain subject to your organization's retention policy.</Notice>}
          <SessionRecordings contextId={contextId} archive={selected} />
          <section className={styles.detailSection} aria-label="Recording conversation"><div className={styles.sectionHeading}><h3>Conversation history</h3><span className={styles.countBadge}>{turns.length} {turns.length === 1 ? 'turn' : 'turns'} loaded</span></div>
            <p className={styles.sectionDescription}>Reported by the practice device, for local and cloud models.</p>
            {turnError && <Notice tone="danger" title="Could not load conversation">{turnError} Use Refresh details to try again.</Notice>}
            {!turns.length && !turnError && <SessionEmpty title="No synchronized conversation yet">Conversation turns will appear here after the device uploads them.</SessionEmpty>}
            <div className={styles.transcript}>{turns.map((turn, index) => <div key={turn.turn_key} className={styles.turnGroup}>
              <div className={styles.turnMeta}><span>Turn {index + 1} · {new Date(turn.occurred_at).toLocaleString()}</span><SessionStatus status={turn.outcome} /></div>
              <ConversationMessage speaker="Trainee">{turn.input_text}</ConversationMessage>
              <ConversationMessage speaker="Patient" patient>{turn.response_text ?? 'No completed answer'}</ConversationMessage>
            </div>)}</div>
            {offset !== null && <Button variant="ghost" loading={more} onClick={() => void loadMore()}>Load more conversation</Button>}
          </section>
        </>}
    </section>
  </Modal>;
}

export function SessionArchives({ contextId }: { contextId: string }) {
  const [rows, setRows] = useState<Archive[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  const paging = useRef(false);
  useEffect(() => {
    const epoch = ++generation.current;
    setLoading(true); setError(undefined); setRows([]); setCursor(null); setBusy(false); paging.current = false;
    void callAction(() => listArchives(contextId)).then(result => {
      if (epoch !== generation.current) return;
      setLoading(false);
      if (result.error !== undefined) setError(result.error);
      else { setRows(result.value.items); setCursor(result.value.next_cursor); }
    });
    return () => { generation.current++; };
  }, [contextId, refresh]);
  async function loadMore() {
    if (paging.current || !cursor) return;
    const epoch = generation.current;
    paging.current = true; setBusy(true); setError(undefined);
    const result = await callAction(() => listArchives(contextId, cursor));
    if (epoch !== generation.current) return;
    paging.current = false; setBusy(false);
    if (result.error !== undefined) setError(result.error);
    else { setRows(current => [...new Map([...current, ...result.value.items].map(row => [row.id, row])).values()]); setCursor(result.value.next_cursor); }
  }
  return <section aria-label="Recordings and synchronization" className={styles.viewSection}>
    <div className={styles.viewHeading}><div><h2>Recordings &amp; sync</h2><p>Find saved conversations and media from assigned or standalone practice.</p></div>
      <Button variant="ghost" disabled={busy || loading} onClick={() => setRefresh(n => n + 1)}><RefreshIcon size={16} />Refresh sync status</Button></div>
    <div className={styles.archiveNote}><InfoIcon size={18} /><p>Finishing a session and uploading its recordings are separate steps. Pending uploads resume from the device; a completed session may still be syncing.</p></div>
    {error && <Notice tone="danger" title="Could not load recordings">{error}</Notice>}
    {loading ? <SessionLoading>Loading recorded sessions…</SessionLoading> : !rows.length ? !error && <SessionEmpty title="No recorded practice yet">Sessions appear here when a connected device starts syncing its capture history.</SessionEmpty> :
      <div className={styles.tableWrap}><table className={`${styles.table} ${styles.responsiveTable}`}>
        <caption className={styles.srOnly}>Recorded practice sessions and upload status</caption>
        <thead><tr><th scope="col">Trainee</th><th scope="col">Practice</th><th scope="col">Recorded</th><th scope="col">Sync status</th><th scope="col"><span className={styles.srOnly}>Details</span></th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.id}><td data-label="Trainee"><strong>{row.learner_name}</strong>{!row.assigned_session_id && <small>Standalone practice</small>}</td>
          <td data-label="Practice">{row.scenario_title}</td><td data-label="Recorded"><SessionDate value={row.created_at} /></td>
          <td data-label="Sync status"><SessionStatus status={row.sync_status} /><small>{row.received_items} saved{row.expected_items !== null ? ` / ${row.expected_items} expected` : ' · awaiting final capture summary'}</small></td>
          <td className={styles.cellActions}><Button variant="ghost" onClick={() => setSelected(row.id)}>View history &amp; recordings<ChevronRightIcon size={16} /></Button></td></tr>)}</tbody>
      </table></div>}
    {!!rows.length && <div className={styles.pagination}><p>{rows.length} {rows.length === 1 ? 'session' : 'sessions'} loaded{cursor ? ' · More available' : ''}</p>
      {cursor && <Button variant="ghost" loading={busy} onClick={() => void loadMore()}>Load more sessions</Button>}</div>}
    {selected && <RecordingDetails key={contextId + selected} contextId={contextId} id={selected} onClose={() => setSelected(undefined)} />}
  </section>;
}
