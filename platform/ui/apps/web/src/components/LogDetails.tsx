'use client';
import { BackNavigation } from './BackNavigation';
import { useEffect, useRef, useState } from 'react';
import { Button, CopyIcon, Notice, PageHeader, useFormatters, useToast } from '@pms/ui';
import { readLog } from '@/lib/log-actions';
import { CATEGORY_LABELS, type ActivityEvent } from '@/lib/log-directory';
import type { SessionUser } from '@/lib/session-user';
import { LogSeverityBadge } from './LogStatusBadge';

export function LogDetails({ logId, user }: { logId: string; user: SessionUser }) {
  const [log, setLog] = useState<ActivityEvent>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [copyFailed, setCopyFailed] = useState(false);
  const root = useRef<HTMLDivElement>(null); const identifier = useRef<HTMLElement>(null);
  const format = useFormatters(); const toast = useToast();
  useEffect(() => {
    let active = true; setLoading(true); setError(undefined); setLog(undefined); setCopyFailed(false);
    void readLog(user.contextId!, logId).then(result => { if (active) { setLog(result.value); setError(result.error); } })
      .catch(() => { if (active) setError('Unable to load this log. Try again.'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [user.contextId, logId, revision]);
  useEffect(() => {
    if (loading) return;
    const heading = root.current?.querySelector('h1'); heading?.setAttribute('tabindex', '-1'); heading?.focus({ preventScroll: true });
  }, [loading]);
  async function copy() {
    if (!log) return;
    try { await navigator.clipboard.writeText(log.id); setCopyFailed(false); toast.success('Log ID copied.'); }
    catch { setCopyFailed(true); identifier.current?.focus(); }
  }
  return <div className="pms-page" ref={root}>
    <BackNavigation href="/logs" label="Back to logs" />
    <PageHeader title={loading ? 'Loading log...' : log?.event_type ?? 'Log not available'} overline={user.contextId === 'platform' ? 'Platform audit' : user.tenant?.name ?? 'Tenant activity'}
      lede="Recorded event metadata. Audit and activity records are read-only."
      actions={<><Button variant="ghost" disabled={loading} onClick={() => setRevision(n => n + 1)}>Refresh log</Button>{log && <Button onClick={() => void copy()}><CopyIcon size={16} />Copy log ID</Button>}</>} />
    {loading && <p role="status">Loading event details...</p>}
    {error && <Notice tone="danger" title="Unable to load log">{error}<p>The record may have expired or be outside your current access scope.</p><Button variant="ghost" onClick={() => setRevision(n => n + 1)}>Retry</Button></Notice>}
    {log && <>
      <LogSeverityBadge severity={log.severity} />
      <dl className="pms-console__tenant-contact">{[
        ['Category', CATEGORY_LABELS[log.category]], ['Actor', log.actor_type], ['Actor user ID', log.actor_user_id],
        ['Occurred', format.dateTime(log.occurred_at)], ['Received', format.dateTime(log.received_at)],
        ['Tenant ID', log.organization_id ?? 'Platform'], ['Department ID', log.department_id], ['Device ID', log.device_id],
        ['Entity type', log.entity_type], ['Entity ID', log.entity_id], ['Processing run ID', log.run_id],
        ['Source event ID', log.source_event_id], ['Retained until', format.dateTime(log.expires_at)],
      ].filter(([, value]) => value).map(([name, value]) => <div key={name}><dt>{name}</dt><dd style={{ overflowWrap: 'anywhere' }}>{value}</dd></div>)}</dl>
      <h2>Event details</h2>
      {log.details_redacted && <Notice tone="info">Only metadata intended for logs is displayed. Other payload fields have been omitted.</Notice>}
      <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 480, overflow: 'auto' }}>{JSON.stringify(log.details, null, 2)}</pre>
      <h2>Log ID</h2><code ref={identifier} tabIndex={-1} style={{ overflowWrap: 'anywhere' }}>{log.id}</code>
      {copyFailed && <p role="alert">Clipboard unavailable. Select and copy the log ID above.</p>}
    </>}
  </div>;
}
