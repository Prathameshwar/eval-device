'use client';

import { useId, type ReactNode } from 'react';
import { Button, Notice } from '@pms/ui';
import styles from './TenantAdministration.module.css';

/** The final step stays inside the task, with the draft available through Back. */
export function TenantTaskReview({ title, details, children, backLabel, confirmLabel, onBack, onConfirm, busy, error, danger = false }: {
  title: string; details: { label: string; value: string }[]; children: ReactNode;
  backLabel: string; confirmLabel: string; onBack: () => void; onConfirm: () => void;
  busy: boolean; error?: string; danger?: boolean;
}) {
  const titleId = useId();
  return <section className={`${styles.card} ${styles.taskForm}`} aria-labelledby={titleId} aria-busy={busy}>
    <h4 id={titleId}>{title}</h4>
    <dl className={styles.reviewDetails}>
      {details.map(detail => <div key={detail.label}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>)}
    </dl>
    {children}
    {error && <Notice tone="danger" title="Unable to complete this action">{error}</Notice>}
    <div className={styles.taskActions}>
      <Button variant="ghost" disabled={busy} onClick={onBack}>{backLabel}</Button>
      <Button variant={danger ? 'danger' : 'primary'} loading={busy} loadingLabel="Saving…" onClick={onConfirm}>{confirmLabel}</Button>
    </div>
  </section>;
}
