'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, Notice, PasswordField, TextField } from '@pms/ui';
import { joinInvitation } from '@/lib/invitation-actions';

export function InvitationForm({ signedInEmail }: { signedInEmail?: string }) {
  const router = useRouter();
  const [token, setToken] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [signIn, setSignIn] = useState(!signedInEmail);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string>();
  const initialized = useRef(false);
  const pending = useRef(false);
  const generation = useRef(0);
  useEffect(() => {
    function read() {
      const url = new URL(window.location.href);
      const raw = new URLSearchParams(url.hash.slice(1)).get('token') ?? url.searchParams.get('token') ?? '';
      if (initialized.current && !raw) return;
      initialized.current = true; generation.current += 1; pending.current = false;
      setBusy(false); setDone(false); setError(undefined); setPassword('');
      setToken(/^inv_[A-Za-z0-9_-]{20,252}$/.test(raw) ? raw : '');
      url.hash = ''; url.searchParams.delete('token');
      window.history.replaceState(null, '', url.pathname + url.search);
      router.replace(url.pathname + url.search, { scroll: false });
      setReady(true);
    }
    read(); window.addEventListener('hashchange', read);
    return () => window.removeEventListener('hashchange', read);
  }, [router]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current || !token) return;
    pending.current = true; setBusy(true); setError(undefined);
    const attempt = generation.current;
    try {
      const result = await joinInvitation(token, signIn ? { email, password } : undefined);
      if (attempt !== generation.current) return;
      setPassword('');
      if (result.error !== undefined) setError(result.error);
      else { setToken(''); setDone(true); }
    } catch { if (attempt === generation.current) setError('Unable to connect. Try again.'); }
    finally { if (attempt === generation.current) { pending.current = false; setBusy(false); } }
  }
  return <section className="pms-auth__card">
    <h1 className="pms-h1">Accept invitation</h1>
    {done ? <><Notice tone="success">Invitation accepted. Your tenant access is ready.</Notice><Link href="/home">Continue to your tenant</Link></>
      : !ready ? <p role="status">Loading invitation...</p> : !token ? <Notice tone="danger">Open the complete invitation link. If it has expired, ask your administrator to resend it.</Notice>
      : <form onSubmit={event => void submit(event)} style={{ display: 'grid', gap: 20 }}>
        {error && <Notice tone="danger">{error}</Notice>}
        {signIn ? <>
          <p>Use the account that received this invitation. New local accounts must first complete their password setup email.</p>
          <TextField label="Email address" type="email" required autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} />
          <PasswordField label="Password" purpose="current" required value={password} onChange={e => setPassword(e.target.value)} />
          <p>For an external identity, sign in through your configured identity provider, then reopen this invitation link.</p>
        </> : <><p>Accept as {signedInEmail}.</p><Button variant="ghost" disabled={busy} onClick={() => setSignIn(true)}>Use another local account</Button></>}
        <Button type="submit" loading={busy} disabled={busy}>{signIn ? 'Sign in and accept' : 'Accept invitation'}</Button>
      </form>}
  </section>;
}
