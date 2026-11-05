'use client';

import Link from 'next/link';
import { useRef, useState, type FormEvent } from 'react';
import { ArrowRightIcon, Button, Checkbox, EmailField, Notice, PasswordField, isEmailLike } from '@pms/ui';
import { signIn as signInAction } from '@/lib/actions';

type SignInFn = (email: string, password: string, remember: boolean) => Promise<{ error: string } | void>;

export function LoginForm({ signIn = signInAction }: { signIn?: SignInFn }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const pending = useRef(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (pending.current || needsRefresh) return;
    setNotice(undefined);
    const next: { email?: string; password?: string } = {};
    if (!email.trim()) next.email = 'Enter your email address.';
    else if (!isEmailLike(email)) next.email = 'That does not look like an email address.';
    if (!password) next.password = 'Enter your password.';
    else if (password.length > 1024) next.password = 'Passwords must not exceed 1024 characters.';
    setErrors(next);
    if (Object.keys(next).length) return;
    pending.current = true;
    setSubmitting(true);
    try {
      const result = await signIn(email.trim(), password, remember);
      if (!result?.error) return; // The server action navigates on success.
      setNotice(result.error);
    } catch (error) {
      if (error instanceof Error && error.name === 'UnrecognizedActionError') {
        setPassword('');
        setNeedsRefresh(true);
        setNotice('The platform was updated while this page was open. Refresh the page, then sign in again.');
      } else {
        setNotice('Unable to connect. Please try again.');
      }
    }
    pending.current = false;
    setSubmitting(false);
  }

  return (
    <section className="pms-auth__card">
      <header className="pms-auth__head">
        <h1 className="pms-h1">Sign in</h1>
        <p className="pms-auth__sub">Use your organisation account to continue.</p>
      </header>
      {notice ? <div className="pms-auth__alert"><Notice tone="danger" title="Sign-in failed" onDismiss={() => setNotice(undefined)}>{notice}</Notice></div> : null}
      {needsRefresh ? <Button type="button" block onClick={() => window.location.reload()}>Refresh page</Button> : null}
      <form onSubmit={onSubmit} noValidate>
        <EmailField label="Email address" value={email} onChange={(value) => { setEmail(value); setErrors((previous) => ({ ...previous, email: undefined })); }}
          error={errors.email} placeholder="you@hospital.org" autoFocus required />
        <PasswordField label="Password" purpose="current" value={password}
          onChange={(event) => { setPassword(event.target.value); setErrors((previous) => ({ ...previous, password: undefined })); }}
          error={errors.password} action={<Link className="pms-link" href="/forgot-password">Forgot password?</Link>} required />
        <div className="pms-auth__row"><Checkbox checked={remember} onChange={(event) => setRemember(event.target.checked)}>Keep me signed in</Checkbox></div>
        <div className="pms-auth__submit"><Button type="submit" block disabled={needsRefresh} loading={submitting} loadingLabel="Signing in…">Sign in<ArrowRightIcon size={16} /></Button></div>
      </form>
      <p className="pms-fine">Use the password you chose during setup or from your account invitation.</p>
    </section>
  );
}
