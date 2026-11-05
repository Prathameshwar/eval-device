import type { Plan, Subscription } from '../../src/lib/subscriptions';
export const plan: Plan = { id: '00000000-0000-4000-8000-000000000101', code: 'standard', name: 'Standard', price_amount: '350000.00', currency: 'INR', billing_period: 'unspecified', max_users: 200, max_devices: 1, is_active: true, configuration_version: 1 };
export const subscription: Subscription = { organization_id: '12345678-1234-4234-8234-123456789012', organization_name: 'Example tenant', organization_is_active: true, organization_archived: false, subscription_plan_id: plan.id,
  assigned_at: '2026-01-01T00:00:00Z', version: 3, status: 'active', state: 'active', starts_at: null, ends_at: null, reference: null, notes: null,
  enforcement: 'tracking_only', plan, usage: { active_users: 1, pending_invitations: 2, users: 3, devices: 1 }, remaining: { users: 197, devices: 0 }, over_limit: false };
