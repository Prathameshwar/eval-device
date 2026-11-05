'use client';

import Link from 'next/link';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, EmailField, Notice, PasswordField, TextField, isEmailLike } from '@pms/ui';
import { completeInitialSetup, verifyInstallationKey, type SetupDetails, type SetupResult } from '@/lib/setup-actions';

type Props = {
  verifyKey?: (key: string) => Promise<SetupResult>;
  complete?: (details: SetupDetails) => Promise<SetupResult>;
};
const STEPS = ['Installation', 'Administrator', 'Review'];

export function InitialSetup({ verifyKey = verifyInstallationKey, complete = completeInitialSetup }: Props) {
  const [step, setStep] = useState(0);
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState(false);
  const pending = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, [step, closed]);

  function clearSecrets() { setKey(''); setPassword(''); setConfirm(''); }
  function change(field: string) { setErrors((old) => ({ ...old, [field]: '' })); }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    setNotice(undefined);
    const next: Record<string, string> = {};
    if (step === 0 && (!key.trim() || key.trim().length > 512)) next.key = 'Enter your installation key.';
    if (step === 1) {
      if (!name.trim() || name.trim().length > 256) next.name = 'Enter a name of up to 256 characters.';
      if (!isEmailLike(email) || email.trim().length > 320) next.email = 'Enter a valid email address.';
      if (password.length < 12 || password.length > 1024) next.password = 'Use 12–1024 characters for your password.';
      if (confirm !== password || !confirm) next.confirm = 'The passwords must match.';
    }
    setErrors(next);
    if (Object.keys(next).length) return;
    if (step === 1) { setStep(2); return; }
    pending.current = true;
    setBusy(true);
    try {
      const result = step === 0 ? await verifyKey(key.trim()) : await complete({
        display_name: name.trim(), email: email.trim(), password, installation_key: key.trim(),
      });
      if (result.code === 'setup_completed') { clearSecrets(); setClosed(true); }
      else if (result.error) {
        setNotice(result.error);
        if (result.code === 'invalid_setup_key') { setKey(''); setStep(0); }
        if (result.code === 'invalid_password' || result.code === 'invalid_request') setStep(1);
      } else if (result.completed) {
        if (step === 0) setStep(1);
        else { clearSecrets(); setStep(3); }
      }
    } catch { setNotice('Unable to connect. Please try again.'); }
    finally { pending.current = false; setBusy(false); }
  }

  if (step === 3 || closed) return <section className="pms-auth__card">
    <header className="pms-auth__head">
      <h1 className="pms-h1 pms-setup__heading" ref={heading} tabIndex={-1}>{closed ? 'Setup is already complete' : 'Your platform is ready'}</h1>
      <p className="pms-auth__sub">{closed ? 'An administrator has already been created for this installation.' : `Sign in with ${email.trim()} to start managing your platform.`}</p>
    </header>
    <Notice tone="success" title={closed ? 'Initial setup is closed' : 'Administrator created'}>
      {closed ? 'Use the existing administrator account to continue.' : 'You can now add tenants, manage users, and configure your devices.'}
    </Notice>
    <p className="pms-auth__alt"><Link className="pms-link" href="/login" prefetch={false}>Continue to sign in</Link></p>
  </section>;

  return <section className="pms-auth__card">
    <ol className="pms-setup__steps" aria-label="Setup progress">
      {STEPS.map((label, index) => <li key={label} aria-current={step === index ? 'step' : undefined}>
        <span aria-hidden="true">{index + 1}</span>{label}
      </li>)}
    </ol>
    <header className="pms-auth__head">
      <h1 className="pms-h1 pms-setup__heading" ref={heading} tabIndex={-1}>{['Set up your platform', 'Create your administrator', 'Review and finish'][step]}</h1>
      <p className="pms-auth__sub">{[
        'Welcome to AI Evaluator. Verify this installation to get started.',
        'Choose the account that will manage your platform.',
        'Check your details before creating the first platform administrator.',
      ][step]}</p>
    </header>
    {notice ? <div className="pms-auth__alert"><Notice tone="danger" title="Setup could not continue">{notice}</Notice></div> : null}
    <form className="pms-setup__form" onSubmit={submit} noValidate>
      {step === 0 ? <>
        <TextField label="Installation key" type="password" autoComplete="off" spellCheck={false} value={key} maxLength={512}
          onChange={(event) => { setKey(event.target.value); change('key'); }} error={errors.key} disabled={busy} required
          hint="Use PMS_INITIAL_SETUP_KEY from your private API deployment settings. This key authorizes first-time setup." />
        <p className="pms-fine">Your administrator name and password are chosen in the next step.</p>
      </> : null}
      {step === 1 ? <>
        <TextField label="Full name" autoComplete="name" value={name} maxLength={256} required error={errors.name}
          onChange={(event) => { setName(event.target.value); change('name'); }} />
        <EmailField label="Email address" value={email} maxLength={320} required error={errors.email}
          onChange={(value) => { setEmail(value); change('email'); }} hint="This is the address you will use to sign in." />
        <PasswordField label="Password" purpose="new" value={password} maxLength={1024} required error={errors.password}
          onChange={(event) => { setPassword(event.target.value); change('password'); }} hint="Use at least 12 characters. A long, unique passphrase works well." />
        <PasswordField label="Confirm password" purpose="new" showStrength={false} value={confirm} maxLength={1024} required error={errors.confirm}
          onChange={(event) => { setConfirm(event.target.value); change('confirm'); }} />
      </> : null}
      {step === 2 ? <>
        <dl className="pms-setup__review">
          <div><dt>Name</dt><dd>{name.trim()}</dd></div>
          <div><dt>Email address</dt><dd>{email.trim()}</dd></div>
          <div><dt>Role</dt><dd>Platform administrator</dd></div>
        </dl>
        <p className="pms-fine">Setup closes after this account is created. Keep your sign-in details somewhere safe.</p>
      </> : null}
      <div className="pms-auth__submit"><Button type="submit" block loading={busy} loadingLabel={step === 0 ? 'Verifying…' : 'Creating administrator…'}>
        {step === 0 ? 'Verify installation' : step === 1 ? 'Review details' : 'Create administrator'}
      </Button></div>
      {step > 0 ? <div className="pms-auth__row"><Button type="button" variant="ghost" disabled={busy} onClick={() => { setStep(step - 1); setNotice(undefined); }}>Back</Button></div> : null}
    </form>
  </section>;
}
