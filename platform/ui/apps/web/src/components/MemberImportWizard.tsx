'use client';
import { BackNavigation } from './BackNavigation';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Button, FileUpload, Notice, Select } from '@pms/ui';
import { peopleDepartments } from '@/lib/people-actions';
import { commitMemberImport, memberImportHistory, readMemberImport, validateMemberImport } from '@/lib/member-import-actions';
import { IMPORT_ROLES, importOptions, importRole, type ImportOptions, type ImportSummary, type MemberImport } from '@/lib/member-imports';
import type { DepartmentOption, MemberRole } from '@/lib/people';
import styles from './MemberImportWizard.module.css';

const steps = ['Access', 'Workbook', 'Review', 'Results'];
const date = (value: string) => new Date(value).toLocaleString();
export function MemberImportWizard({ contextId, tenantName, initialId }: { contextId: string; tenantName: string; initialId?: string }) {
  const [step, setStep] = useState(0);
  const [options, setOptions] = useState<ImportOptions>({ role: 'org_user', auth_method: 'local', department_id: '' });
  const [departments, setDepartments] = useState<DepartmentOption[]>([]);
  const [ready, setReady] = useState(false);
  const [history, setHistory] = useState<ImportSummary[]>([]);
  const [historyError, setHistoryError] = useState<string>();
  const [file, setFile] = useState<File>();
  const [batch, setBatch] = useState<MemberImport>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const active = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const initial = useRef(initialId);
  useEffect(() => {
    let current = true;
    setReady(false);
    Promise.all([peopleDepartments(contextId), memberImportHistory(contextId)]).then(([depts, imports]) => {
      if (!current) return;
      if (depts.error !== undefined) setError(depts.error);
      else { setDepartments(depts.value.filter(d => d.is_active && !d.archived_at)); setReady(true); }
      if (imports.error !== undefined) setHistoryError(imports.error);
      else { setHistory(imports.value); setHistoryError(undefined); }
    }).catch(() => { if (current) setError('Unable to load import options. Please retry.'); });
    return () => { current = false; };
  }, [contextId, attempt]);
  useEffect(() => {
    let current = true;
    if (initial.current) {
      const id = initial.current;
      setBusy(true); active.current = true;
      readMemberImport(contextId, id).then(result => {
        if (!current) return;
        if (result.error !== undefined) setError(result.error);
        else receive(result.value);
      }).catch(() => { if (current) setError('Unable to load this import. Please refresh.'); })
        .finally(() => { if (current) { setBusy(false); active.current = false; } });
    }
    return () => { current = false; };
  }, [contextId]);
  useEffect(() => { heading.current?.focus(); }, [step]);
  function receive(value: MemberImport) {
    setBatch(value); setStep(value.status === 'completed' ? 3 : 2); setPage(0); setFilter('all');
    setOptions({ role: value.role, auth_method: value.auth_method, department_id: value.department_id ?? '' });
    // Keep the saved batch address on refresh, without remounting an in-flight wizard.
    window.history.replaceState(null, '', '/members/import?batch=' + value.id);
  }
  async function perform(work: () => Promise<void>) {
    if (active.current) return;
    active.current = true; setBusy(true); setError(undefined);
    try { await work(); } catch { setError('Unable to confirm the result. Reload this saved import before retrying.'); }
    finally { setBusy(false); active.current = false; }
  }
  function startOver() {
    setBatch(undefined); setFile(undefined); setStep(0); setError(undefined);
    window.history.replaceState(null, '', '/members/import');
    setAttempt(n => n + 1);
  }
  async function open(id: string) {
    await perform(async () => {
      const result = await readMemberImport(contextId, id);
      if (result.error !== undefined) setError(result.error); else receive(result.value);
    });
  }
  async function validate() {
    if (!file) return;
    await perform(async () => {
      const form = new FormData(); form.set('file', file);
      const result = await validateMemberImport(contextId, options, form);
      if (result.error !== undefined) setError(result.error); else receive(result.value);
    });
  }
  async function commit() {
    if (!batch) return;
    await perform(async () => {
      const result = await commitMemberImport(contextId, batch.id);
      if (result.error !== undefined) setError(result.error); else receive(result.value);
    });
  }
  async function download(kind: 'template' | 'errors' | 'results' | 'passwords') {
    await perform(async () => {
      const params = new URLSearchParams({ context: contextId, kind,
        ...(kind === 'template' ? Object.fromEntries(new URLSearchParams(importOptions(options))) : { id: batch!.id }) });
      const response = await fetch('/api/member-imports/download?' + params, { cache: 'no-store' });
      if (!response.ok) { const result = await response.json(); setError(result.error ?? 'Download failed. Please retry.'); return; }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url; link.download = 'member-import-' + kind + '.xlsx';
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  const rows = (batch?.rows ?? []).filter(row => filter !== 'failed' || ['invalid', 'failed'].includes(row.status));
  const expired = !!batch && Date.parse(batch.validated_until) <= Date.now();
  const department = options.department_id ? departments.find(d => d.id === options.department_id)?.name ?? 'Selected department' : 'Whole tenant';
  const context = <div className={styles.context}>{importRole(options.role)} &middot; {options.auth_method === 'local' ? 'Email and password' : 'External sign-in'} &middot; {department}</div>;
  return <div className={'pms-page ' + styles.wizard}>
    <BackNavigation href="/members" label="Back to members" />
    <header><Link className={styles.historyLink} href="/members/import/history">Import History</Link><span className={styles.eyebrow}>{tenantName}</span><h1 className={styles.heading}>Import members</h1>
      <p className={styles.muted}>Add people from Excel, with a clear review before anything is imported.</p></header>
    <ol className={styles.steps} aria-label="Import progress">{steps.map((label, index) =>
      <li key={label} aria-current={step === index ? 'step' : undefined} data-complete={index < step}><span>{String(index + 1).padStart(2, '0')}</span>{label}</li>)}</ol>
    {error && <Notice tone="danger">{error}</Notice>}
    <section className={styles.panel} aria-busy={busy}>
      <h2 ref={heading} tabIndex={-1}>{['Choose access for this batch', 'Prepare your workbook', 'Review before importing', 'Import results'][step]}</h2>
      <p className={styles.muted}>{[
        'Everyone in this workbook will receive the same role and sign-in method.',
        'Use the template below. Fill in the Members sheet, then upload the saved file.',
        'Only ready rows will be imported. Download errors to correct the remaining people separately.',
        options.auth_method === 'local'
          ? 'Successful rows created invitations. New local accounts receive the supplied or generated password and gain tenant access after accepting.'
          : 'Successful rows created invitations. People use external sign-in and gain tenant access after accepting.',
      ][step]}</p>
      <div className={styles.content}>
        {step === 0 && <>
          <div className={styles.fields}>
            <Select label="Role" value={options.role} options={IMPORT_ROLES} disabled={busy}
              onChange={role => setOptions(o => ({ ...o, role: role as MemberRole, department_id: role === 'org_admin' ? '' : o.department_id }))} />
            <Select label="Sign-in method" value={options.auth_method} disabled={busy}
              options={[{ value: 'local', label: 'Email and password' }, { value: 'oidc', label: 'External sign-in (SSO)' }]}
              onChange={auth_method => setOptions(o => ({ ...o, auth_method: auth_method as 'local' | 'oidc' }))}
              hint={options.auth_method === 'local' ? 'The workbook can supply passwords. Missing passwords are generated for new accounts; existing account passwords stay unchanged.' : 'People sign in through the configured identity provider. No local passwords are created.'} />
            <Select label="Department" value={options.department_id} loading={!ready} disabled={busy || options.role === 'org_admin'}
              options={[{ value: '', label: 'Whole tenant' }, ...departments.map(d => ({ value: d.id, label: d.name }))]}
              onChange={department_id => setOptions(o => ({ ...o, department_id }))}
              hint={options.role === 'org_admin' ? 'Tenant administrators manage the whole tenant.' : 'Optional. Applies to every person in this batch.'} />
          </div>
          {options.role === 'org_admin' && <Notice tone="warning">This role grants administrative access across this tenant. Review every person before importing.</Notice>}
          {!ready && !busy && <Button variant="ghost" onClick={() => setAttempt(n => n + 1)}>Retry options</Button>}
        </>}
        {step === 1 && <>
          {context}
          <div className={styles.download}><div><strong>Excel template</strong><p className={styles.muted}>Full name, email{options.auth_method === 'local' ? ', optional local password' : '; leave Password blank'} &middot; Up to 200 people &middot; 512 KB</p></div>
            <Button variant="ghost" disabled={busy} onClick={() => void download('template')}>Download template</Button></div>
          <FileUpload label="Upload completed workbook" accept=".xlsx" acceptLabel="Excel (.xlsx)" maxSizeBytes={512 * 1024} maxFiles={1}
            disabled={busy} items={file ? [{ id: 'workbook', name: file.name, size: file.size, status: 'pending' }] : []}
            onSelect={files => { setFile(files[0]); setError(undefined); }} onRemove={() => setFile(undefined)}
            hint={options.auth_method === 'local'
              ? 'Keep the template headings. Passwords are optional for new local accounts; leave them blank to generate secure passwords. Formulas are rejected.'
              : 'Keep the template headings. Leave Password blank for external sign-in. Formulas are rejected.'} />
        </>}
        {batch && step >= 2 && <>
          {context}
          <dl className={styles.stats}>
            <div><dt>Total rows</dt><dd>{batch.counts.total}</dd></div>
            <div><dt>{step === 2 ? 'Ready to import' : 'Successful'}</dt><dd>{step === 2 ? batch.counts.ready : batch.counts.succeeded}</dd></div>
            <div><dt>{step === 2 ? 'Needs correction' : 'Failed'}</dt><dd>{batch.counts.failed}</dd></div>
          </dl>
          {!batch.email_configured && <Notice tone="warning">Email delivery is not configured. Invitations can still be created. Use each member's Resend invitation action to obtain a link for secure sharing.{options.auth_method === 'local' ? ' Share new local passwords separately and privately.' : ''}</Notice>}
          {step === 2 && expired && <Notice tone="warning">Validation has expired. Upload the workbook again to check current access and capacity.</Notice>}
          {step === 3 && <Notice tone={batch.counts.failed ? 'warning' : 'success'}>
            {batch.counts.succeeded} invitation{batch.counts.succeeded === 1 ? '' : 's'} created{batch.counts.failed ? '; ' + batch.counts.failed + ' row(s) could not be imported.' : '.'}
            {' '}Email delivery is shown separately below.
          </Notice>}
          <div className={styles.tools}>
            <Select label="Show rows" inline value={filter} options={[{ value: 'all', label: 'All rows' }, { value: 'failed', label: 'Errors only' }]} onChange={value => { setFilter(value); setPage(0); }} />
            <div className={styles.downloadActions}>{batch.counts.failed > 0 && <Button variant="ghost" disabled={busy} onClick={() => void download('errors')}>Download errors</Button>}
              {step === 3 && <Button variant="ghost" disabled={busy} onClick={() => void download('results')}>Download results</Button>}
              {step === 3 && batch.password_count > 0 && <Button variant="ghost" disabled={busy} onClick={() => void download('passwords')}>Download passwords</Button>}</div>
          </div>
          <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th scope="col">Row</th><th scope="col">Person</th><th scope="col">Result</th></tr></thead>
            <tbody>{rows.slice(page * 10, page * 10 + 10).map(row => <tr key={row.row_number}>
              <td>{row.row_number}</td><td>{row.full_name || 'Missing name'}<small>{row.email || 'Missing email'}</small></td>
              <td><strong>{row.status === 'ready' ? 'Ready' : row.status === 'succeeded' ? 'Invitation created' : 'Needs correction'}</strong>
                {row.message && <small>{row.message}</small>}
                {step === 3 && row.password && <small>Password: <code>{row.password}</code></small>}
                {row.email_status && <small>Email: {({ pending: 'queued', sending: 'sending', sent: 'sent', failed: 'not confirmed; use Resend invitation', unknown: 'delivery unconfirmed; use Resend invitation', cancelled: 'cancelled', expired: 'queue record expired' } as Record<string, string>)[row.email_status] ?? row.email_status}</small>}
              </td></tr>)}</tbody></table>{!rows.length && <p className={styles.muted}>No rows to show.</p>}</div>
          {rows.length > 10 && <div className={styles.pager}><Button variant="ghost" disabled={page === 0} onClick={() => setPage(n => n - 1)}>Previous</Button>
            <span>Page {page + 1} of {Math.ceil(rows.length / 10)}</span><Button variant="ghost" disabled={(page + 1) * 10 >= rows.length} onClick={() => setPage(n => n + 1)}>Next</Button></div>}
          <p className={styles.muted} style={{ fontSize: 12 }}>Results available until {date(batch.expires_at)}.
            {step === 2 ? ' Validation is checked again during import.' : ' Passwords for new local accounts remain available in Import History until this date. Share them privately.'}</p>
        </>}
      </div>
      <div className={styles.actions}>
        {step === 0 && <Button disabled={busy || !ready} onClick={() => setStep(1)}>Continue</Button>}
        {step === 1 && <><Button variant="ghost" disabled={busy} onClick={() => setStep(0)}>Back</Button><Button disabled={!file || busy} loading={busy} onClick={() => void validate()}>Validate workbook</Button></>}
        {step === 2 && batch && <><Button variant="ghost" disabled={busy} onClick={() => { setBatch(undefined); setStep(1); window.history.replaceState(null, '', '/members/import'); }}>Change workbook</Button>
          <Button disabled={busy || expired || batch.counts.ready === 0} loading={busy} onClick={() => void commit()}>Import {batch.counts.ready} {batch.counts.ready === 1 ? 'member' : 'members'}</Button></>}
        {step === 3 && <><Button variant="ghost" disabled={busy} onClick={startOver}>Start another import</Button><Button variant="ghost" disabled={busy} onClick={() => batch && void open(batch.id)}>Refresh delivery</Button><Link className="pms-link" href="/members">View members</Link></>}
      </div>
    </section>
    {step === 0 && <details className={styles.history}><summary>Recent imports - results retained for 30 days</summary>
      {historyError && <Notice tone="danger">{historyError} <Button variant="ghost" onClick={() => setAttempt(n => n + 1)}>Retry history</Button></Notice>}
      {!history.length && !historyError && <p className={styles.muted}>No recent imports.</p>}
      <ul>{history.map(item => <li key={item.id}><div>{importRole(item.role)} &middot; {date(item.created_at)}
        <small>{item.status === 'completed' ? item.counts.succeeded + ' successful / ' + item.counts.failed + ' failed' : item.counts.ready + ' ready / ' + item.counts.failed + ' need correction'}</small></div>
        <Button variant="ghost" disabled={busy} onClick={() => void open(item.id)}>{item.status === 'completed' ? 'View results' : 'Review'}</Button></li>)}</ul>
    </details>}
  </div>;
}
