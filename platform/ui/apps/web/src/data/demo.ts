/**
 * Every number on every dashboard, in one file.
 *
 * All of it is invented. It exists so the layout can be judged against realistic shapes — a
 * four-digit device count, a tenant name long enough to wrap, a score with one decimal — and so
 * that connecting the API is a change to one module rather than a hunt through three dashboards.
 *
 * Figures are **strings**, not numbers. `StatTile`, `ListRow` and `BarChart` all require that,
 * for the reason the package states: a formatted figure is presentation, and a `number` that
 * crosses into a component is a rounding decision made in the wrong place. Percentages and
 * shares, which are ratios rather than figures, stay numbers — `Meter` takes 0–1.
 */

import type { RoleCode } from '@/lib/roles';

/** The bell's count. Static: there is nothing to open yet, so the number is furniture. */
export const NOTIFICATION_COUNT = 3;

export type StatCard = {
  id: string;
  label: string;
  value: string;
  footnote: string;
  /** `success` and `danger` are load-bearing here: they mark the tile that needs acting on. */
  tone?: 'default' | 'brand' | 'success' | 'warn' | 'danger';
  emphasis?: boolean;
};

export type ActivityRow = {
  id: string;
  primary: string;
  meta: string;
  tone?: 'neutral' | 'brand' | 'success' | 'warn' | 'danger' | 'info';
  figure?: string;
};

export type HealthRow = {
  id: string;
  label: string;
  meta: string;
  /** 0–1, for `Meter`. */
  share: number;
  tone: 'success' | 'warn' | 'danger';
};

/* ─────────────── platform admin ─────────────── */

export const PLATFORM_STATS: readonly StatCard[] = [
  {
    id: 'devices',
    label: 'Total devices',
    value: '1,284',
    footnote: '18 enrolled this month',
  },
  {
    id: 'live',
    label: 'Live devices',
    value: '947',
    footnote: '73.8% reporting in the last 5 minutes',
    tone: 'success',
  },
  {
    id: 'tenants',
    label: 'Total tenants',
    value: '36',
    footnote: '2 awaiting first enrolment',
  },
  {
    id: 'licences',
    label: 'Expired licences',
    value: '4',
    footnote: '3 more expire within 30 days',
    tone: 'danger',
    emphasis: true,
  },
];

export const DEVICES_BY_TENANT: readonly { label: string; value: string }[] = [
  { label: 'Northside', value: '312' },
  { label: 'Cavell', value: '268' },
  { label: 'Riverbend', value: '201' },
  { label: 'St Ellis', value: '174' },
  { label: 'Ashford', value: '139' },
  { label: 'Others', value: '190' },
];

export const PLATFORM_ACTIVITY: readonly ActivityRow[] = [
  { id: 'a1', primary: 'Riverbend Institute licence expired', meta: 'Today, 09:14 · 201 devices affected', tone: 'danger' },
  { id: 'a2', primary: 'Cavell Teaching Hospital enrolled 12 devices', meta: 'Today, 08:02 · by r.desai@cavell.example', tone: 'success' },
  { id: 'a3', primary: 'Model qwen2.5-7b promoted to default', meta: 'Yesterday, 17:45 · platform configuration', tone: 'brand' },
  { id: 'a4', primary: 'Ashford College added an administrator', meta: 'Yesterday, 11:20 · 1 invitation sent', tone: 'neutral' },
];

/* ─────────────── tenant admin ─────────────── */

export const TENANT_ADMIN_STATS: readonly StatCard[] = [
  { id: 'devices', label: 'Devices', value: '312', footnote: '4 enrolled this week' },
  { id: 'live', label: 'Live devices', value: '286', footnote: '26 offline for over an hour', tone: 'success' },
  { id: 'members', label: 'Active members', value: '148', footnote: '9 invitations pending' },
  {
    id: 'licence',
    label: 'Licence expires in',
    value: '21 days',
    footnote: 'Renewal not yet requested',
    tone: 'warn',
    emphasis: true,
  },
];

export const TENANT_DEVICE_HEALTH: readonly HealthRow[] = [
  { id: 'h1', label: 'Reporting normally', meta: '286 devices', share: 0.917, tone: 'success' },
  { id: 'h2', label: 'Degraded audio input', meta: '17 devices', share: 0.054, tone: 'warn' },
  { id: 'h3', label: 'Offline over 24 hours', meta: '9 devices', share: 0.029, tone: 'danger' },
];

export const TENANT_ADMIN_ACTIVITY: readonly ActivityRow[] = [
  { id: 's1', primary: 'Cardiology — chest pain, Alex', meta: 'Today, 10:32 · Priya Nair', figure: '84%', tone: 'success' },
  { id: 's2', primary: 'Respiratory — cough, Meera', meta: 'Today, 09:58 · Arjun Rao', figure: '71%', tone: 'brand' },
  { id: 's3', primary: 'Nephrology — swelling, Ravi', meta: 'Yesterday, 16:40 · Sana Qureshi', figure: '62%', tone: 'warn' },
  { id: 's4', primary: 'Cardiology — palpitations, Dev', meta: 'Yesterday, 15:05 · Priya Nair', figure: '90%', tone: 'success' },
];

/* ─────────────── tenant user ─────────────── */

export const TENANT_USER_STATS: readonly StatCard[] = [
  { id: 'sessions', label: 'My sessions', value: '24', footnote: '3 completed this week' },
  { id: 'hours', label: 'Hours practised', value: '11.5', footnote: 'Across 6 scenarios', tone: 'brand' },
  { id: 'score', label: 'Average score', value: '78%', footnote: 'Up 4 points on last month', tone: 'success' },
  {
    id: 'reviews',
    label: 'Awaiting review',
    value: '2',
    footnote: 'Submitted more than 3 days ago',
    tone: 'warn',
    emphasis: true,
  },
];

export const TENANT_USER_SESSIONS: readonly ActivityRow[] = [
  { id: 'u1', primary: 'Cardiology — chest pain, Alex', meta: 'Today, 10:32 · 14 turns · reviewed', figure: '84%', tone: 'success' },
  { id: 'u2', primary: 'Respiratory — cough, Meera', meta: 'Monday, 14:11 · 11 turns · reviewed', figure: '76%', tone: 'success' },
  /* No `figure`: an unreviewed session has no score. An em-dash in the column would be read as
   * punctuation or skipped entirely, and "awaiting review" in the meta line is the actual fact. */
  { id: 'u3', primary: 'Nephrology — swelling, Ravi', meta: 'Last Friday, 09:20 · 9 turns · awaiting review', tone: 'warn' },
];

/** The four cards each role's dashboard leads with. */
export const STATS_BY_ROLE: Record<RoleCode, readonly StatCard[]> = {
  platform_admin: PLATFORM_STATS,
  org_admin: TENANT_ADMIN_STATS,
  org_user: TENANT_USER_STATS,
};
