'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, Notice, PasswordField } from '@pms/ui';
import { completeAccountAction, type AccountResult } from '@/lib/actions';

export type AccountPurpose = 'setup' | 'password-reset' | 'email-change';
const TITLES: Record<AccountPurpose, string> = { setup: 'Set up your password', 'password-reset': 'Choose a new password', 'email-change': 'Confirm email change' };

export function AccountActionForm({ purpose, complete = completeAccountAction }: {
  purpose: AccountPurpose;
  complete?: (purpose: string, token: string, password?: string) => Promise<AccountResult>;
}) {
  const router = useRouter();
  const [token, setToken] = useState('');
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const pending = useRef(false);
  const initialized = useRef(false);
  const generation = useRef(0);
  const passwordAction = purpose !== 'email-change';

  useEffect(() => {
    function readLink() {
      const url = new URL(window.location.href);
      const raw = new URLSearchParams(url.hash.slice(1)).get('token') ?? url.searchParams.get('token') ?? '';
      if (initialized.current && !raw) return;
      initialized.current = true;
      generation.current += 1;
      pending.current = false;
      setBusy(false); setDone(false); setError(undefined); setPassword(''); setConfirm('');
      setToken(/^act_[A-Za-z0-9_-]{20,508}$/.test(raw) ? raw : '');
      url.hash = ''; url.searchParams.delete('token');
      // Keep Next's canonical URL clean too: action refreshes must not restore the fragment.
      window.history.replaceState(null, '', url.pathname + url.search);
      router.replace(url.pathname + url.search, { scroll: false });
      setReady(true);
    }
    readLink();
    window.addEventListener('hashchange', readLink);
    return () => window.removeEventListener('hashchange', readLink);
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current || !token) return;
    if (passwordAction && (password.length < 12 || password.length > 1024)) { setError('Use a password between 12 and 1024 characters.'); return; }
    if (passwordAction && password !== confirm) { setError('The passwords do not match.'); return; }
    setError(undefined); pending.current = true; setBusy(true);
    const attempt = generation.current;
    try {
      const result = await complete(purpose, token, passwordAction ? password : undefined);
      if (attempt !== generation.current) return;
      if (result.error) setError(result.error);
      else { setDone(true); setToken(''); setPassword(''); setConfirm(''); }
    } catch { if (attempt === generation.current) setError('Unable to connect. Please try again.'); }
    finally { if (attempt === generation.current) { pending.current = false; setBusy(false); } }
  }

  return <section className="pms-auth__card">
    <header className="pms-auth__head"><h1 className="pms-h1">{TITLES[purpose]}</h1></header>
    {done ? <Notice tone="info" title="Account updated">Sign in using your updated account details. Previous sessions have been signed out.</Notice> :
      !ready ? <p role="status">Loading account link…</p> : !token ?
        <Notice tone="danger" title="Account link unavailable">Open the complete link from your email. If it has expired, request another link.</Notice> :
        <form onSubmit={submit} noValidate>
          {error ? <Notice tone="danger" title="Unable to update account">{error}</Notice> : null}
          {passwordAction ? <>
            <PasswordField label="New password" purpose="new" value={password} onChange={(event) => setPassword(event.target.value)} hint="Use 12–1024 characters. Avoid common passwords." required />
            <PasswordField label="Confirm new password" purpose="new" showStrength={false} value={confirm} onChange={(event) => setConfirm(event.target.value)} required />
          </> : <p>Confirm that you want to use this email address to sign in. This will sign out your existing sessions.</p>}
          <div className="pms-auth__submit"><Button type="submit" block loading={busy} loadingLabel="Updating…">{passwordAction ? 'Save password' : 'Confirm email change'}</Button></div>
        </form>}
    <p className="pms-auth__alt"><Link className="pms-link" href="/login">Back to sign in</Link>{purpose === 'password-reset' ? <> · <Link className="pms-link" href="/forgot-password">Request another reset link</Link></> : null}</p>
  </section>;
}
