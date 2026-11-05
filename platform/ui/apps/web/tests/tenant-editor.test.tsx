import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { TenantEditor } from '../src/components/TenantEditor';
import { DEMO_TENANTS, TENANT_PLANS } from '../src/data/tenants';
import { saveTenantDraft, tenantDraft, validateTenantDraft } from '../src/lib/tenant-editor';

const plan = Object.keys(TENANT_PLANS)[0]!;
const tenant = DEMO_TENANTS[0]!;
const valid = () => ({ ...tenantDraft(null), name: 'New academy', subscription_plan_id: plan });

describe('tenant editor data', () => {
  it('requires a nonblank name and an available plan on creation', () => {
    expect(validateTenantDraft({ ...valid(), name: '   ', subscription_plan_id: 'unknown' }, TENANT_PLANS, true))
      .toEqual({ name: 'Enter a tenant name.', subscription_plan_id: 'Choose an available subscription plan.' });
    expect(validateTenantDraft(valid(), {}, true)).toHaveProperty('subscription_plan_id');
  });
  it.each([['name', 256], ['description', 4000], ['contact_name', 256], ['contact_phone', 80]] as const)(
    'honors the API length boundary for %s', (field, max) => {
      expect(validateTenantDraft({ ...valid(), [field]: 'x'.repeat(max) }, TENANT_PLANS, true)[field]).toBeUndefined();
      expect(validateTenantDraft({ ...valid(), [field]: 'x'.repeat(max + 1) }, TENANT_PLANS, true)[field]).toBeDefined();
    },
  );
  it('allows optional email, validates it when supplied and normalizes pasted addresses', () => {
    expect(validateTenantDraft(valid(), TENANT_PLANS, true)).toEqual({});
    expect(validateTenantDraft({ ...valid(), contact_email: 'wrong' }, TENANT_PLANS, true)).toHaveProperty('contact_email');
    expect(validateTenantDraft({ ...valid(), contact_email: 'Office <office@EXAMPLE.COM>' }, TENANT_PLANS, true)).toEqual({});
  });
  it('creates inactive records, trims optional fields and keeps identity/version fields consistent', () => {
    const saved = saveTenantDraft({ ...valid(), name: '  New academy  ', contact_phone: '  +91 12345 ext 9  ', is_active: true }, null, 'new-id', 'timestamp');
    expect(saved).toMatchObject({ id: 'new-id', name: 'New academy', is_active: false, archived_at: null,
      contact_email: null, contact_name: null, description: null, contact_phone: '+91 12345 ext 9',
      created_at: 'timestamp', updated_at: 'timestamp', management_version: 1 });
  });
  it('preserves IDs, original creation date and plan when editing, even with an unavailable plan label', () => {
    const draft = { ...tenantDraft(tenant), name: 'Renamed', subscription_plan_id: 'different-plan', contact_email: '' };
    expect(validateTenantDraft(draft, {}, false)).toEqual({});
    expect(saveTenantDraft(draft, tenant, 'ignored', 'later')).toMatchObject({ id: tenant.id, name: 'Renamed',
      subscription_plan_id: tenant.subscription_plan_id, created_at: tenant.created_at, updated_at: 'later',
      management_version: tenant.management_version + 1, contact_email: null });
    expect(tenant.name).toBe('Apex Medical College');
  });
});

describe('tenant editor controls', () => {
  it('does not show errors while an untouched form mounts or focus passes through it', async () => {
    const user = userEvent.setup();
    render(<StrictMode><TenantEditor tenant={null} plans={TENANT_PLANS} onSave={vi.fn()} onClose={() => {}} /></StrictMode>);
    expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveFocus();
    await user.tab();
    expect(screen.queryByText('Enter a tenant name.')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Tenant name' })).not.toHaveAttribute('aria-invalid', 'true');
  });

  it('shows required and email errors, moves focus to the first error and clears errors as corrected', async () => {
    const user = userEvent.setup(); const save = vi.fn();
    render(<TenantEditor tenant={null} plans={TENANT_PLANS} onSave={save} onClose={() => {}} />);
    expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Create tenant' }));
    expect(screen.getByText('Enter a tenant name.')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveFocus());
    await user.type(screen.getByRole('textbox', { name: 'Tenant name' }), 'Academy');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Subscription plan' }), plan);
    await user.type(screen.getByRole('textbox', { name: 'Contact email' }), 'invalid');
    await user.click(screen.getByRole('button', { name: 'Create tenant' }));
    expect(screen.getByRole('textbox', { name: 'Contact email' })).toHaveAttribute('aria-invalid', 'true');
    expect(save).not.toHaveBeenCalled();
    await user.clear(screen.getByRole('textbox', { name: 'Contact email' }));
    await user.type(screen.getByRole('textbox', { name: 'Contact email' }), 'office@example.com');
    expect(screen.queryByText('Check the highlighted fields')).not.toBeInTheDocument();
    await user.dblClick(screen.getByRole('button', { name: 'Create tenant' }));
    expect(save).toHaveBeenCalledTimes(1);
  });
  it('protects a dirty draft on Escape, keeps editing, and discards only after confirmation', async () => {
    const user = userEvent.setup(); const close = vi.fn();
    render(<TenantEditor tenant={null} plans={TENANT_PLANS} onSave={vi.fn()} onClose={close} />);
    await user.type(screen.getByRole('textbox', { name: 'Tenant name' }), 'Draft');
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event); expect(event.defaultPrevented).toBe(true);
    await user.keyboard('{Escape}');
    const confirmation = screen.getByRole('dialog', { name: 'Discard unsaved changes?' });
    expect(within(confirmation).getByRole('button', { name: 'Keep editing' })).toHaveFocus();
    await user.click(within(confirmation).getByRole('button', { name: 'Keep editing' }));
    expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveValue('Draft');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(close).toHaveBeenCalledTimes(1);
  });
  it('does not warn or save an unchanged edit, and allows Cancel immediately', async () => {
    const user = userEvent.setup(); const close = vi.fn(); const save = vi.fn();
    render(<TenantEditor tenant={tenant} plans={TENANT_PLANS} onSave={save} onClose={close} />);
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Subscription plan' })).toHaveAttribute('readonly');
    fireEvent.submit(screen.getByRole('textbox', { name: 'Tenant name' }).closest('form')!);
    expect(save).not.toHaveBeenCalled();
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event); expect(event.defaultPrevented).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(close).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog', { name: 'Discard unsaved changes?' })).not.toBeInTheDocument();
  });
  it('explains an empty plan catalogue and prevents creation', () => {
    render(<TenantEditor tenant={null} plans={{}} onSave={vi.fn()} onClose={() => {}} />);
    expect(screen.getByText('No plans available')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Subscription plan' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Create tenant' })).toBeDisabled();
  });
  it('retains entries on a save failure and permits retry', async () => {
    const user = userEvent.setup(); const save = vi.fn().mockReturnValueOnce('This record changed. Reopen it.').mockReturnValue(undefined);
    render(<TenantEditor tenant={tenant} plans={TENANT_PLANS} onSave={save} onClose={() => {}} />);
    await user.type(screen.getByRole('textbox', { name: 'Tenant name' }), ' Updated');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(screen.getByText('Tenant was not saved')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Tenant name' })).toHaveValue(`${tenant.name} Updated`);
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(save).toHaveBeenCalledTimes(2);
  });
});
