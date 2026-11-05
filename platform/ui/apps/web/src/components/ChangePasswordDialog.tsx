'use client';

import Link from 'next/link';
import { useRef, useState, type FormEvent } from 'react';
import { Button, Modal, Notice, PasswordField } from '@pms/ui';
import { changePassword, type AccountResult } from '@/lib/actions';

export function ChangePasswordDialog({ open, email, onClose, updatePassword = changePassword }: {
  open: boolean; email: string; onClose: () => void;
  updatePassword?: (current: string, next: string) => Promise<AccountResult>;
}) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const pending = useRef(false);

  function close(): void {
    if (pending.current) return;
    setCurrent(''); setNext(''); setConfirm(''); setError(undefined); setDone(false);
    onClose();
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (pending.current) return;
    if (!current || !next || !confirm) { setError('Fill in all three fields.'); return; }
    if (next.length < 12 || next.length > 1024) { setError('Use a password between 12 and 1024 characters.'); return; }
    if (next !== confirm) { setError('The new password and its confirmation do not match.'); return; }
    if (next === current) { setError('The new password must be different from the current one.'); return; }
    setError(undefined); pending.current = true; setBusy(true);
    try {
      const result = await updatePassword(current, next);
      if (result.error) setError(result.error);
      else { setCurrent(''); setNext(''); setConfirm(''); setDone(true); }
    } catch { setError('Unable to connect. Please try again.'); }
    finally { pending.current = false; setBusy(false); }
  }

  return (
    <Modal open={open} title="Change password" onClose={close} busy={busy} size="sm" footer={
      done ? <Link className="pms-link" href="/login">Sign in again</Link> : <>
        <Button variant="ghost" onClick={close} disabled={busy}>Cancel</Button>
        <Button type="submit" form="change-password" loading={busy} loadingLabel="Saving…">Update password</Button>
      </>
    }>
      {done ? <Notice tone="info" title="Password changed">Your sessions have been signed out. Sign in again with your new password.</Notice> :
        <form id="change-password" onSubmit={onSubmit} noValidate>
          {error ? <Notice tone="danger" title="Check the form">{error}</Notice> : null}
          <PasswordField label="Current password" purpose="current" value={current} onChange={(event) => setCurrent(event.target.value)} required />
          <PasswordField label="New password" purpose="new" value={next} onChange={(event) => setNext(event.target.value)} avoid={[email]} hint="Use 12–1024 characters. Avoid common passwords." required />
          <PasswordField label="Confirm new password" purpose="new" showStrength={false} value={confirm} onChange={(event) => setConfirm(event.target.value)} required />
        </form>}
    </Modal>
  );
}
