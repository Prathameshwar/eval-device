import type { ReactNode } from 'react';
import { ClockIcon, MessageIcon } from '@pms/ui';
import styles from './SessionQueueWorkspace.module.css';

const statuses: Record<string, { label: string; tone: string }> = {
  queued: { label: 'Waiting', tone: 'neutral' }, active: { label: 'In progress', tone: 'info' },
  stopping: { label: 'Stopping', tone: 'warning' }, completed: { label: 'Completed', tone: 'success' },
  cancelled: { label: 'Cancelled', tone: 'neutral' }, expired: { label: 'Expired', tone: 'neutral' },
  failed: { label: 'Interrupted', tone: 'danger' }, synced: { label: 'Fully synced', tone: 'success' },
  pending: { label: 'Sync pending', tone: 'warning' }, incomplete: { label: 'Missing capture data', tone: 'warning' },
  upload_expired: { label: 'Upload window ended', tone: 'neutral' },
  capture_started: { label: 'Capture started', tone: 'info' },
};
export function SessionStatus({ status }: { status: string }) {
  const value = statuses[status] ?? { label: status, tone: 'neutral' };
  return <span className={styles.statusBadge} data-tone={value.tone}><span aria-hidden="true" />{value.label}</span>;
}
export function SessionDate({ value, fallback = 'Not started' }: { value: string | null; fallback?: string }) {
  if (!value) return <span className={styles.muted}>{fallback}</span>;
  const date = new Date(value);
  return <time dateTime={value} className={styles.dateStamp} title={date.toLocaleString()}>
    <span>{date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
    <small>{date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</small>
  </time>;
}
export function SessionEmpty({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <div className={styles.emptyState}><span className={styles.emptyIcon}><MessageIcon size={24} /></span>
    <h3>{title}</h3><p>{children}</p>{action && <div className={styles.emptyAction}>{action}</div>}</div>;
}
export function SessionLoading({ children }: { children: ReactNode }) {
  return <div className={styles.loadingState} role="status"><ClockIcon size={20} /><span>{children}</span></div>;
}
export function ConversationMessage({ speaker, patient, children }: { speaker: string; patient?: boolean; children: ReactNode }) {
  return <div className={styles.conversationMessage} data-speaker={patient ? 'patient' : 'trainee'}>
    <span className={styles.speakerMark} aria-hidden="true">{patient ? 'P' : 'T'}</span>
    <div><strong>{speaker}</strong><p>{children}</p></div>
  </div>;
}
