'use client';

import { useRef, useState, type FormEvent } from 'react';
import { Button, EmailField, Modal, Notice, PasswordField, isEmailLike } from '@pms/ui';
import { changeEmail } from '@/lib/actions';

export function ChangeEmailDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const pending = useRef(false);
  function close() {
    if (pending.current) return;
    setEmail(''); setPassword(''); setError(undefined); setDone(false); onClose();
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    if (!isEmailLike(email) || !password) { setError('Enter a valid email address and your current password.'); return; }
    setError(undefined); setBusy(true); pending.current = true;
    try {
      const result = await changeEmail(email.trim(), password);
      if (result.error) setError(result.error);
      else { setPassword(''); setDone(true); }
    } catch { setError('Unable to connect. Please try again.'); }
    finally { setBusy(false); pending.current = false; }
  }
  return <Modal open={open} title="Change email address" onClose={close} busy={busy} size="sm" footer={
    <><Button variant="ghost" onClick={close} disabled={busy}>{done ? 'Close' : 'Cancel'}</Button>{!done ? <Button type="submit" form="change-email" loading={busy}>Send confirmation</Button> : null}</>
  }>{done ? <Notice tone="info" title="Confirmation requested">Check your new email address for a confirmation link. Your sign-in address changes only after you confirm it.</Notice> :
    <form id="change-email" onSubmit={submit} noValidate>
      {error ? <Notice tone="danger" title="Unable to change email">{error}</Notice> : null}
      <EmailField label="New email address" value={email} onChange={setEmail} required />
      <PasswordField label="Current password" purpose="current" value={password} onChange={(event) => setPassword(event.target.value)} required />
    </form>}
  </Modal>;
}
