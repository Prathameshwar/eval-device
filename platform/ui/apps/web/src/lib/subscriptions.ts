export type Plan = {
  id: string; code: string; name: string; price_amount: string; currency: 'INR' | 'USD';
  billing_period: 'unspecified' | 'monthly' | 'annual' | 'one_time';
  max_users: number; max_devices: number; is_active: boolean; configuration_version: number;
};
export type Subscription = {
  organization_id: string; organization_name: string; organization_is_active: boolean; organization_archived: boolean;
  subscription_plan_id: string; assigned_at: string; version: number;
  status: 'active' | 'suspended' | 'cancelled'; state: 'active' | 'scheduled' | 'expired' | 'suspended' | 'cancelled';
  starts_at: string | null; ends_at: string | null; reference?: string | null; notes?: string | null;
  enforcement: 'tracking_only'; plan: Plan;
  usage: { active_users: number; pending_invitations: number; users: number; devices: number };
  remaining: { users: number; devices: number }; over_limit: boolean;
};
export type SubscriptionQuery = { q: string; state: string; plan_id: string; limit: number };
export const DEFAULT_SUBSCRIPTION_QUERY: SubscriptionQuery = { q: '', state: 'all', plan_id: '', limit: 25 };
export type SubscriptionDraft = {
  subscription_plan_id: string; subscription_status: Subscription['status'];
  subscription_starts_at: string | null; subscription_ends_at: string | null;
  subscription_reference: string | null; subscription_notes: string | null;
};
export type SubscriptionEvent = {
  id: string; occurred_at: string; event_type: string; actor_user_id?: string | null;
  details: { fields?: string[]; previous_plan_id?: string; subscription_plan_id?: string; changes?: Record<string, { before: unknown; after: unknown }> };
};
export function price(plan: Plan) { return plan.currency + ' ' + plan.price_amount + ' / ' + plan.billing_period.replaceAll('_', ' '); }
export function displayDate(value: string | null) { return value ? new Date(value).toISOString().replace('T', ' ').replace('.000Z', ' UTC') : 'Not set'; }
