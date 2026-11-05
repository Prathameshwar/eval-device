import type { StatCard, ActivityRow, HealthRow } from '@/data/demo';

export type HomeData = {
  cards: StatCard[];
  activity: ActivityRow[];
  tenants?: { label: string; value: string }[];
  health?: HealthRow[];
};
export function timestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? 'Unknown time' : date.toLocaleString('en-GB', { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short' }) + ' UTC';
}
