'use client';

import Link from 'next/link';
import { useRef, useState, type FormEvent } from 'react';
import { BackIcon, Button, EmailField, Notice, isEmailLike } from '@pms/ui';
import { forgotPassword, type AccountResult } from '@/lib/actions';

export function ForgotPasswordForm({ requestReset = forgotPassword }: { requestReset?: (email: string) => Promise<AccountResult> }) {
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string>();
  const [failure, setFailure] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [requested, setRequested] = useState(false);
  const pending = useRef(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (pending.current) return;
    setRequested(false);
    setFailure(undefined);
    if (!email.trim()) { setError('Enter your email address.'); return; }
    if (!isEmailLike(email)) { setError('That does not look like an email address.'); return; }
    setError(undefined);
    pending.current = true;
    setSubmitting(true);
    try {
      const result = await requestReset(email.trim());
      if (result.error) setFailure(result.error);
      else setRequested(true);
    } catch { setFailure('Unable to connect. Please try again.'); }
    finally { pending.current = false; setSubmitting(false); }
  }

  return (
    <section className="pms-auth__card">
      <Link className="pms-link pms-auth__back" href="/login"><BackIcon size={16} />Back to sign in</Link>
      <header className="pms-auth__head"><h1 className="pms-h1">Reset password</h1><p className="pms-auth__sub">Enter the address you use to sign in.</p></header>
      {requested ? <div className="pms-auth__alert"><Notice tone="info" title="Request received">If this address belongs to an eligible account, a reset link will be emailed to it. Check your inbox and spam folder.</Notice></div> : null}
      {failure ? <div className="pms-auth__alert"><Notice tone="danger" title="Request failed">{failure}</Notice></div> : null}
      <form onSubmit={onSubmit} noValidate>
        <EmailField label="Email address" value={email} onChange={(value) => { setEmail(value); setError(undefined); }} error={error} placeholder="you@hospital.org" autoFocus required />
        <div className="pms-auth__submit"><Button type="submit" block loading={submitting} loadingLabel="Sending…">Send reset link</Button></div>
      </form>
      <p className="pms-auth__alt">Still locked out? Contact your organisation administrator. External accounts use their identity provider for password recovery.</p>
    </section>
  );
}
