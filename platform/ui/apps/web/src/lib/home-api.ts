import 'server-only';
import { apiRequest } from './api';
import { sessionToken } from './session';
import type { SessionUser } from './session-user';
import { timestamp, type HomeData } from './home';

type Session = { id: string; created_at: string; status: string; scenario_title?: string };
const count = (value: number) => value.toLocaleString('en-GB');
export async function loadHome(user: SessionUser): Promise<HomeData> {
  const token = await sessionToken();
  if (user.contextId === 'platform') {
    const [stats, report, audit] = await Promise.all([
      apiRequest<{ total_devices: number; live_devices: number; total_tenants: number; inactive_tenants: number; awaiting_enrollment: number; offline_after_seconds: number }>('/platform/dashboard-stats', { token }),
      apiRequest<{ items: { label: string; value: string }[] }>('/platform/reports/devices-by-tenant?limit=10', { token }),
      apiRequest<{ items: { id: string; event_type: string; occurred_at: string }[] }>('/platform/audit?limit=6&sort_by=occurred_at&sort_order=desc', { token }),
    ]);
    return {
      cards: [
        { id: 'devices', label: 'Total devices', value: count(stats.total_devices), footnote: 'Current devices in unarchived tenants' },
        { id: 'live', label: 'Live devices', value: count(stats.live_devices), footnote: `Operational; seen within ${stats.offline_after_seconds} seconds`, tone: 'success' },
        { id: 'tenants', label: 'Total tenants', value: count(stats.total_tenants), footnote: `${stats.awaiting_enrollment} awaiting enrolment` },
        { id: 'licences', label: 'Inactive tenants', value: count(stats.inactive_tenants), footnote: 'Unarchived tenants awaiting activation or suspended', tone: stats.inactive_tenants ? 'warn' : 'default' },
      ],
      tenants: report.items,
      activity: audit.items.map(row => ({ id: row.id, primary: row.event_type.replaceAll('.', ' '), meta: timestamp(row.occurred_at) })),
    };
  }
  const base = `/organizations/${encodeURIComponent(user.contextId!) }`;
  const sessions = Promise.all([
    apiRequest<{ items: Session[] }>(base + '/training/sessions' + (user.role === 'org_admin' ? '' : '?mine=true'), { token }),
    apiRequest<{ items: Session[] }>(base + '/practice-sessions?limit=6', { token }),
  ]).then(([earlier, practice]) => ({ items: [...earlier.items, ...practice.items].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 6) }));
  if (user.role === 'org_admin') {
    const [stats, recent] = await Promise.all([
      apiRequest<{ devices: { total: number; live: number }; members: { active: number; pending: number }; offline_after_seconds: number; subscription: { plan: { name: string }; remaining: { devices: number } }; health_shares: NonNullable<HomeData['health']> }>(base + '/dashboard-stats', { token }),
      sessions,
    ]);
    return {
      cards: [
        { id: 'devices', label: 'Devices', value: count(stats.devices.total), footnote: 'Current devices; excludes retired' },
        { id: 'live', label: 'Live devices', value: count(stats.devices.live), footnote: `Operational; seen within ${stats.offline_after_seconds} seconds`, tone: 'success' },
        { id: 'members', label: 'Active members', value: count(stats.members.active), footnote: `${stats.members.pending} invitations pending` },
        { id: 'licence', label: 'Subscription plan', value: stats.subscription.plan.name, footnote: `${stats.subscription.remaining.devices} device slots available` },
      ],
      activity: sessionRows(recent.items), health: stats.health_shares,
    };
  }
  const [stats, recent] = await Promise.all([
    apiRequest<{ sessions: number; hours_practiced: number; average_score: number | null; awaiting_review: number }>(base + '/training/stats', { token }),
    sessions,
  ]);
  return {
    cards: [
      { id: 'sessions', label: 'My sessions', value: count(stats.sessions), footnote: 'Retained sessions in your current scope' },
      { id: 'hours', label: 'Hours practised', value: count(stats.hours_practiced), footnote: 'Recorded time in completed sessions' },
      { id: 'score', label: 'Average score', value: stats.average_score === null ? 'Not scored' : `${stats.average_score}%`, footnote: 'Completed sessions with rubric feedback' },
      { id: 'reviews', label: 'Awaiting review', value: count(stats.awaiting_review), footnote: 'Completed sessions without feedback' },
    ],
    activity: sessionRows(recent.items),
  };
}
function sessionRows(rows: Session[]) {
  return rows.slice(0, 6).map(row => ({ id: row.id, primary: row.scenario_title ?? `Session ${row.id.slice(0, 8)}`, meta: timestamp(row.created_at), figure: row.status }));
}
