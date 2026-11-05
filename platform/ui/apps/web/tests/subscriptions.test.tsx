import { PermissionProvider } from '@pms/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { SubscriptionDetails, Subscriptions } from '../src/components/Subscriptions';
import { SubscriptionEditor } from '../src/components/SubscriptionEditor';
import { listSubscriptions, readSubscription, saveSubscription, subscriptionHistory, subscriptionPlans } from '../src/lib/subscription-actions';
import { plan, subscription } from './fixtures/subscriptions';
vi.mock('../src/lib/subscription-actions', () => ({ listSubscriptions: vi.fn(), readSubscription: vi.fn(), saveSubscription: vi.fn(), saveSubscriptionPlan: vi.fn(), subscriptionHistory: vi.fn(), subscriptionPlans: vi.fn() }));
const empty = { items: [], total: 0, has_more: false, next_cursor: null };
beforeEach(() => {
  vi.mocked(listSubscriptions).mockResolvedValue({ value: { ...empty, items: [subscription], total: 1 } });
  vi.mocked(subscriptionPlans).mockResolvedValue({ value: [plan] });
  vi.mocked(readSubscription).mockResolvedValue({ value: subscription });
  vi.mocked(subscriptionHistory).mockResolvedValue({ value: empty });
  vi.mocked(saveSubscription).mockReset();
});
it('uses persisted subscriptions and forwards filters to the API', async () => {
  render(<PermissionProvider permissions={['platform.organizations.read']}><Subscriptions contextId="platform" /></PermissionProvider>);
  expect(await screen.findByRole('link', { name: 'Example tenant' })).toHaveAttribute('href', '/licenses/' + subscription.organization_id);
  const user = userEvent.setup(); await user.selectOptions(screen.getByLabelText('Subscription status'), 'expired');
  await waitFor(() => expect(listSubscriptions).toHaveBeenLastCalledWith('platform', expect.objectContaining({ state: 'expired' }), undefined));
  expect(screen.getByText(/do not block processing/)).toBeInTheDocument();
});
it('tenant details cannot offer management or display platform-only notes', async () => {
  const { notes, reference, ...tenant } = subscription;
  vi.mocked(readSubscription).mockResolvedValue({ value: tenant });
  render(<PermissionProvider permissions={['org.settings.read']}><SubscriptionDetails contextId={subscription.organization_id} organizationId={subscription.organization_id} /></PermissionProvider>);
  await screen.findByText('Standard subscription');
  expect(screen.queryByRole('button', { name: 'Edit or renew subscription' })).not.toBeInTheDocument();
  expect(screen.queryByText('Internal notes')).not.toBeInTheDocument();
});
it('retains a stale status confirmation and sends the selected version', async () => {
  vi.mocked(saveSubscription).mockResolvedValue({ error: 'Subscription changed; refresh first.' });
  render(<PermissionProvider permissions={['platform.organizations.manage']}><SubscriptionDetails contextId="platform" organizationId={subscription.organization_id} /></PermissionProvider>);
  const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: 'Suspend subscription' }));
  expect(saveSubscription).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Confirm status change' }));
  expect(await screen.findByText('Subscription changed; refresh first.')).toBeInTheDocument();
  expect(screen.getByRole('dialog', { name: 'Suspend subscription?' })).toBeInTheDocument();
  expect(saveSubscription).toHaveBeenCalledWith('platform', subscription.organization_id, 3, { subscription_status: 'suspended' });
});
it('validates UTC date ordering and retains edits after a rejected save', async () => {
  const save = vi.fn().mockResolvedValue('No free device seat.');
  render(<SubscriptionEditor row={subscription} plans={[plan]} onClose={vi.fn()} onSave={save} />);
  const user = userEvent.setup();
  const start = screen.getByLabelText('Starts at (UTC)'); const end = screen.getByLabelText('Ends at (UTC)');
  // Native datetime-local edits are dispatched as the browser's complete value.
  const { fireEvent } = await import('@testing-library/react');
  fireEvent.change(start, { target: { value: '2026-10-02T00:00' } }); fireEvent.change(end, { target: { value: '2026-10-01T00:00' } });
  await user.click(screen.getByRole('button', { name: 'Save subscription' }));
  expect(await screen.findByText('The end must be after the start.')).toBeInTheDocument(); expect(save).not.toHaveBeenCalled();
  fireEvent.change(end, { target: { value: '2027-10-01T00:00' } });
  await user.click(screen.getByRole('button', { name: 'Save subscription' }));
  expect(await screen.findByText('No free device seat.')).toBeInTheDocument();
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ subscription_starts_at: '2026-10-02T00:00:00.000Z', subscription_ends_at: '2027-10-01T00:00:00.000Z' }));
  expect(end).toHaveValue('2027-10-01T00:00');
});

it('preserves exact timestamps when editing only a manual reference', async () => {
  const row = { ...subscription, starts_at: '2026-01-01T00:00:00.123Z', ends_at: '2027-01-01T00:00:00.456Z' };
  const save = vi.fn().mockResolvedValue('Saved test');
  render(<SubscriptionEditor row={row} plans={[plan]} onClose={vi.fn()} onSave={save} />);
  const user = userEvent.setup(); await user.type(screen.getByLabelText('Manual reference'), 'Agreement');
  await user.click(screen.getByRole('button', { name: 'Save subscription' }));
  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ subscription_starts_at: row.starts_at, subscription_ends_at: row.ends_at })));
});

it('shows older plan-assignment events and their actor in retained history', async () => {
  vi.mocked(subscriptionHistory).mockResolvedValue({ value: { ...empty, items: [{ id: 'event', occurred_at: '2026-01-01T00:00:00Z', event_type: 'platform.organization.subscription_changed', actor_user_id: 'administrator-id', details: { previous_plan_id: 'old-plan', subscription_plan_id: plan.id } }] } });
  render(<PermissionProvider permissions={['org.settings.read']}><SubscriptionDetails contextId={subscription.organization_id} organizationId={subscription.organization_id} /></PermissionProvider>);
  expect(await screen.findByText('administrator-id')).toBeInTheDocument();
  expect(screen.getByText('Plan assignment: old-plan ? ' + plan.id)).toBeInTheDocument();
});
