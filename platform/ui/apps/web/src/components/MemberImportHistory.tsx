'use client';
import { BackNavigation } from './BackNavigation';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Button, Notice, PageHeader } from '@pms/ui';
import { memberImportHistory } from '@/lib/member-import-actions';
import { importRole, type ImportSummary } from '@/lib/member-imports';
import styles from './MemberImportWizard.module.css';

export function MemberImportHistory({ contextId }: { contextId: string }) {
  const [items, setItems] = useState<ImportSummary[]>([]);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(true);
  const load = useCallback(async () => {
    setBusy(true); setError(undefined);
    try {
      const result = await memberImportHistory(contextId);
      if (result.error !== undefined) setError(result.error);
      else setItems(result.value);
    } catch { setError('Unable to load import history. Please retry.'); }
    finally { setBusy(false); }
  }, [contextId]);
  useEffect(() => { void load(); }, [load]);
  async function download(item: ImportSummary, kind: 'results' | 'passwords') {
    setBusy(true); setError(undefined);
    try {
      const query = new URLSearchParams({ context: contextId, id: item.id, kind });
      const response = await fetch('/api/member-imports/download?' + query, { cache: 'no-store' });
      if (!response.ok) {
        const result = await response.json();
        setError(result.error ?? 'Download failed. Please retry.');
        return;
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = `member-import-${kind}-${item.id}.xlsx`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError('Download failed. Please retry.'); }
    finally { setBusy(false); }
  }
  return <div className={'pms-page ' + styles.wizard}>
    <BackNavigation href="/members" label="Back to members" />
    <PageHeader overline="Members" title="Import History" lede="Review retained imports and download results or new-account passwords for 30 days."
      actions={<><Button variant="ghost" disabled={busy} onClick={() => void load()}>Refresh</Button><Link className="pms-btn" href="/members/import">New import</Link></>} />
    {error && <Notice tone="danger">{error}</Notice>}
    {busy && !items.length ? <p role="status">Loading imports…</p> : null}
    {!items.length && !busy && !error ? <p>No retained imports.</p> : null}
    <ul className={styles.historyList}>{items.map(item => <li key={item.id}>
      <div><strong>{importRole(item.role)}</strong> · {new Date(item.created_at).toLocaleString()}
        <small>{item.status === 'completed' ? `${item.counts.succeeded} successful · ${item.counts.failed} failed` : `${item.counts.ready} ready · ${item.counts.failed} need correction`}</small>
        <small>Available until {new Date(item.expires_at).toLocaleString()}</small></div>
      <div className={styles.downloadActions}>
        <Link className="pms-btn pms-btn--ghost" href={'/members/import?batch=' + encodeURIComponent(item.id)}>{item.status === 'completed' ? 'View results' : 'Review'}</Link>
        {item.status === 'completed' && <Button variant="ghost" disabled={busy} onClick={() => void download(item, 'results')}>Download results</Button>}
        {item.password_count > 0 && <Button variant="ghost" disabled={busy} onClick={() => void download(item, 'passwords')}>Download passwords</Button>}
      </div>
    </li>)}</ul>
  </div>;
}
