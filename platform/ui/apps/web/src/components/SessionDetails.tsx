'use client';

import { useEffect, useRef, useState } from 'react';
import { Button, Modal, Notice, RefreshIcon } from '@pms/ui';
import { callAction } from '@/lib/call-action';
import { practiceSessionResult, type SessionResult } from '@/lib/session-queue-actions';
import { archiveTurns, readArchive, type Archive, type ArchiveTurn } from '@/lib/session-archive-actions';
import { sessionLanguage } from '@/lib/session-start';
import { ConversationMessage, SessionDate, SessionEmpty, SessionLoading, SessionStatus } from './SessionPresentation';
import styles from './SessionQueueWorkspace.module.css';
import { SessionRecordings } from './SessionArchives';

function SessionCapture({ contextId, id }: { contextId: string; id: string }) {
  const [archive, setArchive] = useState<Archive>();
  const [error, setError] = useState<string>();
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    setArchive(undefined); setError(undefined);
    void callAction(() => readArchive(contextId, id)).then(response => {
      if (!live) return;
      if (response.error !== undefined) setError(response.error); else setArchive(response.value);
    });
    return () => { live = false; };
  }, [contextId, id, revision]);
  return <>
    {error ? <Notice tone="danger" title="Could not load recording status" action={<Button variant="ghost" onClick={() => setRevision(n => n + 1)}>Refresh recording status</Button>}>{error}</Notice>
      : !archive ? <SessionLoading>Loading recording status…</SessionLoading> : <>
        <section aria-label="Session synchronization" className={styles.detailSection}>
          <div className={styles.sectionHeading}><h3>Recording sync</h3><SessionStatus status={archive.sync_status} /></div>
          <dl className={styles.detailFacts}>
            <div><dt>Saved items</dt><dd>{archive.received_items}{archive.expected_items !== null ? ` / ${archive.expected_items} expected` : ' · awaiting final capture summary'}</dd></div>
            <div><dt>Capture summary</dt><dd>{archive.capture_status === 'incomplete' ? 'Missing capture data' : archive.expected_items === null ? 'Awaiting device' : 'Received'}</dd></div>
          </dl>
          <p className={styles.sectionDescription}>Completion means the session ended. Sync status describes uploads; saved items include conversation turns and recording segments.</p>
          <Button variant="ghost" onClick={() => setRevision(n => n + 1)}><RefreshIcon size={16} />Refresh recording status</Button>
        </section>
        <SessionRecordings contextId={contextId} archive={archive} />
      </>}
  </>;
}

function ArchivedConversation({ contextId, id, learner }: { contextId: string; id: string; learner: string }) {
  const [turns, setTurns] = useState<ArchiveTurn[]>([]);
  const [offset, setOffset] = useState<number | null>(null);
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const paging = useRef(false);
  useEffect(() => {
    const epoch = ++generation.current;
    setLoading(true); setError(undefined); setTurns([]); setOffset(null); paging.current = false;
    void callAction(() => archiveTurns(contextId, id)).then(response => {
      if (epoch !== generation.current) return;
      setLoading(false);
      if (response.error !== undefined) setError(response.error);
      else { setTurns(response.value.items); setOffset(response.value.next_offset); }
    });
    return () => { generation.current++; };
  }, [contextId, id, revision]);
  async function loadMore() {
    if (paging.current || offset === null) return;
    const epoch = generation.current;
    paging.current = true; setLoading(true); setError(undefined);
    const response = await callAction(() => archiveTurns(contextId, id, offset));
    if (epoch !== generation.current) return;
    paging.current = false; setLoading(false);
    if (response.error !== undefined) setError(response.error);
    else {
      setTurns(current => [...new Map([...current, ...response.value.items].map(turn => [turn.turn_key, turn])).values()]);
      setOffset(response.value.next_offset);
    }
  }
  return <>
    <p className={styles.sectionDescription}>Conversation saved with this session's recordings. Recording uploads have their own sync status.</p>
    {error && <Notice tone="danger" title="Could not load saved conversation" action={<Button variant="ghost" onClick={() => setRevision(n => n + 1)}>Try again</Button>}>{error}</Notice>}
    {loading && !turns.length && <SessionLoading>Loading saved conversation…</SessionLoading>}
    {!loading && !error && !turns.length && <SessionEmpty title="Conversation upload pending">The session has ended, but no saved turns have arrived yet. Refresh details after the device syncs.</SessionEmpty>}
    <div className={styles.transcript}>{turns.map(turn => <div key={turn.turn_key} className={styles.turnGroup}>
      <ConversationMessage speaker={learner}>{turn.input_text}</ConversationMessage>
      <ConversationMessage speaker="Patient" patient>{turn.response_text ?? 'No completed answer'}</ConversationMessage>
    </div>)}</div>
    {offset !== null && <Button variant="ghost" loading={loading} onClick={() => void loadMore()}>Load more conversation</Button>}
    {!loading && !error && <Button variant="ghost" onClick={() => setRevision(n => n + 1)}><RefreshIcon size={16} />Refresh conversation</Button>}
  </>;
}

export function SessionDetails({ contextId, id, onClose, onRecordings }: {
  contextId: string; id: string; onClose: () => void; onRecordings: () => void;
}) {
  const [result, setResult] = useState<SessionResult>();
  const [error, setError] = useState<string>();
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    setResult(undefined); setError(undefined);
    void callAction(() => practiceSessionResult(contextId, id)).then(response => {
      if (!live) return;
      if (response.error !== undefined) setError(response.error);
      else setResult(response.value);
    });
    return () => { live = false; };
  }, [contextId, id, revision]);
  const session = result?.session;
  return <Modal open title="Session details" size="lg" onClose={onClose} footer={<>
    <Button variant="ghost" onClick={onClose}>Close details</Button>
    <Button onClick={onRecordings}>Back to session history</Button>
  </>}>
    <div className={styles.detailContent}>
      {error ? <Notice tone="danger" title="Could not load session" action={<Button variant="ghost" onClick={() => setRevision(n => n + 1)}><RefreshIcon size={16} />Try again</Button>}>{error}</Notice>
        : !result || !session ? <SessionLoading>Loading session details…</SessionLoading> : <>
          <div className={styles.detailHero}><div><span className={styles.overline}>TRAINEE</span><h3>{session.learner_name}</h3><p>{session.scenario_title}</p></div>
            <SessionStatus status={session.status} /></div>
          <dl className={styles.detailFacts}>
            <div><dt>Language</dt><dd>{sessionLanguage(session.language)}</dd></div>
            <div><dt>Planned duration</dt><dd>{session.duration_seconds / 60} min</dd></div>
            <div><dt>Queued</dt><dd><SessionDate value={session.created_at} /></dd></div>
            <div><dt>Started</dt><dd><SessionDate value={session.started_at} /></dd></div>
            <div><dt>Ended</dt><dd><SessionDate value={session.ended_at} fallback="Not ended" /></dd></div>
            <div><dt>Assignment expires</dt><dd><SessionDate value={session.expires_at} /></dd></div>
          </dl>
          <section aria-label="Session conversation" className={styles.detailSection}>
            <div className={styles.sectionHeading}><h3>Conversation</h3><span className={styles.countBadge}>{!result.messages.length && result.archive_id ? 'Saved archive' : `${result.messages.length} ${result.messages.length === 1 ? 'message' : 'messages'}`}</span></div>
            {result.provenance === 'client_reported' && !!result.messages.length && <p className={styles.sectionDescription}>Conversation reported by the practice device. Recording uploads have their own sync status.</p>}
            {!result.messages.length && result.archive_id ? <ArchivedConversation key={contextId + result.archive_id} contextId={contextId} id={result.archive_id} learner={session.learner_name} />
              : !result.messages.length ? <SessionEmpty title="No saved conversation yet">Completion records that the session ended. Conversation uploads may still be pending, reporting may have been disabled, or saved results may have expired. Refresh session details after the device uploads its saved results.</SessionEmpty>
              : <div className={styles.transcript}>{result.messages.map((message, index) => <ConversationMessage key={index}
                speaker={message.role === 'user' ? session.learner_name : 'Patient'} patient={message.role !== 'user'}>{message.content}</ConversationMessage>)}</div>}
          </section>
          {result.archive_id && <SessionCapture key={contextId + result.archive_id} contextId={contextId} id={result.archive_id} />}
        </>}
    </div>
  </Modal>;
}
