import type { SessionUser } from './session-user';

export type ActivityEvent = {
  id: string; organization_id: string | null; department_id: string | null; device_id: string | null;
  actor_type: 'user' | 'device' | 'system'; actor_user_id: string | null;
  category: 'audit' | 'operational'; event_type: string; severity: 'info' | 'warning' | 'error';
  entity_type: string | null; entity_id: string | null; run_id: string | null; source_event_id: string | null;
  occurred_at: string; received_at: string; details: Record<string, unknown>; details_redacted: boolean; expires_at: string;
};
export type LogCategory = ActivityEvent['category'] | 'all';
export type LogQuery = {
  q: string; category: LogCategory; severity: string; actor_type: string;
  organization_id: string; device_id: string; since: string; until: string;
  sort_by: 'occurred_at' | 'received_at' | 'event_type'; sort_order: 'asc' | 'desc'; limit: number;
};
export const LOG_PAGE_LIMITS = [25, 50, 100] as const;
export function logCategories(user: SessionUser): LogCategory[] {
  if (user.contextId === 'platform') return user.permissions.includes('platform.audit.read') ? ['audit'] : [];
  if (!user.contextId) return [];
  const audit = user.permissions.includes('org.audit.read');
  const activity = user.permissions.includes('org.activity.read');
  return audit && activity ? ['all', 'audit', 'operational'] : audit ? ['audit'] : activity ? ['operational'] : [];
}
export const defaultLogQuery = (category: LogCategory): LogQuery => ({
  q: '', category, severity: '', actor_type: '', organization_id: '', device_id: '', since: '', until: '',
  sort_by: 'occurred_at', sort_order: 'desc', limit: 25,
});
export const CATEGORY_LABELS = { all: 'All categories', audit: 'Audit', operational: 'Operational' };

/** Day filters use explicit UTC boundaries; the through-day is inclusive. */
export function logDate(value: string, end = false): string | undefined {
  if (!value) return undefined;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Invalid date');
  const date = new Date(value + 'T00:00:00.000Z');
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) throw new Error('Invalid date');
  if (end) date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString();
}
