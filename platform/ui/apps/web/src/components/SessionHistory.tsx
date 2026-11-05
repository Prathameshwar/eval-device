'use client';

import { useEffect, useRef, useState } from 'react';
import { Button, ChevronRightIcon, Notice, RefreshIcon } from '@pms/ui';
import { callAction } from '@/lib/call-action';
import { sessionHistory, type SessionHistoryEntry } from '@/lib/session-queue-actions';
import { sessionLanguage } from '@/lib/session-start';
import { SessionDate, SessionEmpty, SessionLoading, SessionStatus } from './SessionPresentation';
import styles from './SessionQueueWorkspace.module.css';

export function SessionHistory({ contextId, onInspect }: { contextId: string; onInspect: (id: string, kind: 'assigned' | 'standalone') => void }) {
  const [rows, setRows] = useState<SessionHistoryEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string>();
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const paging = useRef(false);
  useEffect(() => {
    const epoch = ++generation.current;
    setLoading(true); setError(undefined); setMore(false); paging.current = false;
    setRows([]); setCursor(null);
    void callAction(() => sessionHistory(contextId)).then(response => {
      if (epoch !== generation.current) return;
      setLoading(false);
      if (response.error !== undefined) setError(response.error);
      else { setRows(response.value.items); setCursor(response.value.next_cursor); }
    });
    return () => { generation.current++; };
  }, [contextId, revision]);
  async function loadMore() {
    if (paging.current || !cursor) return;
    const epoch = generation.current;
    paging.current = true; setMore(true); setError(undefined);
    const response = await callAction(() => sessionHistory(contextId, cursor));
    if (epoch !== generation.current) return;
    paging.current = false; setMore(false);
    if (response.error !== undefined) setError(response.error);
    else { setRows(current => [...new Map([...current, ...response.value.items].map(row => [row.kind + row.id, row])).values()]); setCursor(response.value.next_cursor); }
  }
  return <section aria-label="Practice session history" className={styles.viewSection}>
    <div className={styles.viewHeading}><div><h2>Session history</h2><p>Assigned and standalone practice, with conversations, recordings and upload status together.</p></div>
      <Button variant="ghost" disabled={loading || more} onClick={() => setRevision(n => n + 1)}><RefreshIcon size={16} />Refresh history</Button></div>
    {error && <Notice tone="danger" title="Could not load session history">{error}</Notice>}
    {loading ? <SessionLoading>Loading session history…</SessionLoading>
      : !rows.length ? !error && <SessionEmpty title="No session history yet">Assigned sessions and captured standalone practice will appear here.</SessionEmpty>
      : <div className={styles.tableWrap}><table className={`${styles.table} ${styles.responsiveTable}`}>
        <caption className={styles.srOnly}>Practice session history and synchronization</caption>
        <thead><tr><th scope="col">Trainee</th><th scope="col">Practice</th><th scope="col">Session status</th><th scope="col">Recording sync</th><th scope="col">Saved items</th><th scope="col">Date</th><th scope="col"><span className={styles.srOnly}>Details</span></th></tr></thead>
        <tbody>{rows.map(row => {
          const session = row.session, archive = row.archive;
          const status = session?.status ?? (archive?.outcome === 'interrupted' ? 'failed' : archive?.outcome ?? 'capture_started');
          return <tr key={row.kind + row.id}>
            <td data-label="Trainee"><strong>{session?.learner_name ?? archive?.learner_name ?? 'No trainee assigned'}</strong>{row.kind === 'standalone' && <small>Standalone practice</small>}</td>
            <td data-label="Practice">{session?.scenario_title ?? archive?.scenario_title}{session && <small>{sessionLanguage(session.language)} · {session.duration_seconds / 60} min</small>}</td>
            <td data-label="Session status"><SessionStatus status={status} /></td>
            <td data-label="Recording sync">{archive ? <SessionStatus status={archive.sync_status} /> : <span>No capture received</span>}</td>
            <td data-label="Saved items">{archive ? <>{archive.received_items} saved{archive.expected_items !== null ? ` / ${archive.expected_items} expected` : ' · awaiting capture summary'}</> : '—'}</td>
            <td data-label="Date"><SessionDate value={session?.created_at ?? archive?.created_at ?? null} /></td>
            <td className={styles.cellActions}><Button variant="ghost" onClick={() => onInspect(row.id, row.kind)}>View session<ChevronRightIcon size={16} /></Button></td>
          </tr>;
        })}</tbody>
      </table></div>}
    {!!rows.length && <div className={styles.pagination}><p>{rows.length} {rows.length === 1 ? 'session' : 'sessions'} loaded{cursor ? ' · More available' : ''}</p>
      {cursor && <Button variant="ghost" loading={more} loadingLabel="Loading sessions…" onClick={() => void loadMore()}>Load more sessions</Button>}</div>}
  </section>;
}
