import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { MemberImportWizard } from '../src/components/MemberImportWizard';
import { MemberImportHistory } from '../src/components/MemberImportHistory';
import { peopleDepartments } from '../src/lib/people-actions';
import { commitMemberImport, memberImportHistory, readMemberImport, validateMemberImport } from '../src/lib/member-import-actions';
import type { MemberImport } from '../src/lib/member-imports';
vi.mock('../src/lib/people-actions', () => ({ peopleDepartments: vi.fn() }));
vi.mock('../src/lib/member-import-actions', () => ({
  commitMemberImport: vi.fn(), memberImportHistory: vi.fn(), readMemberImport: vi.fn(), validateMemberImport: vi.fn(),
}));
const id = '11111111-1111-4111-8111-111111111111';
const batch: MemberImport = {
  id, role: 'org_trainee', auth_method: 'local', department_id: null, status: 'validated',
  created_at: '2026-09-24T00:00:00Z', completed_at: null, validated_until: '2099-01-01T00:00:00Z',
  expires_at: '2099-02-01T00:00:00Z', email_configured: false, password_count: 0,
  counts: { total: 2, ready: 1, failed: 1, succeeded: 0 },
  rows: [
    { row_number: 2, full_name: 'Valid', email: 'valid@example.com', status: 'ready', code: null, message: null, membership_id: null },
    { row_number: 3, full_name: 'Bad', email: 'bad', status: 'invalid', code: 'invalid_person', message: 'Enter a valid email.', membership_id: null },
  ],
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(peopleDepartments).mockResolvedValue({ value: [{ id, name: 'Training', is_active: true, archived_at: null }] });
  vi.mocked(memberImportHistory).mockResolvedValue({ value: [] });
  vi.mocked(validateMemberImport).mockResolvedValue({ value: batch });
  vi.mocked(readMemberImport).mockResolvedValue({ value: batch });
  window.history.replaceState(null, '', '/members/import');
});
it('walks through one-role validation and partial results without importing during upload', async () => {
  const user = userEvent.setup();
  render(<MemberImportWizard contextId={id} tenantName="Example" />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled());
  expect(screen.queryByText('Platform administrator')).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Role'), 'org_trainee');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.upload(screen.getByLabelText('Upload completed workbook'), new File(['excel'], 'people.xlsx'));
  await user.click(screen.getByRole('button', { name: 'Validate workbook' }));
  expect(await screen.findByRole('heading', { name: 'Review before importing' })).toBeInTheDocument();
  expect(commitMemberImport).not.toHaveBeenCalled();
  expect(validateMemberImport).toHaveBeenCalledWith(id, expect.objectContaining({ role: 'org_trainee' }), expect.any(FormData));
  expect(screen.getByText(/Email delivery is not configured/)).toBeInTheDocument();
  vi.mocked(commitMemberImport).mockResolvedValue({ value: { ...batch, status: 'completed',
    counts: { total: 2, ready: 0, failed: 1, succeeded: 1 },
    rows: [{ ...batch.rows[0]!, status: 'succeeded', membership_id: id, email_status: 'pending' }, batch.rows[1]!],
  } });
  await user.click(screen.getByRole('button', { name: 'Import 1 member' }));
  expect(await screen.findByRole('heading', { name: 'Import results' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Download errors' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Download results' })).toBeInTheDocument();
  expect(screen.getByText('Email: queued')).toBeInTheDocument();
  expect(window.location.search).toBe('?batch=' + id);
  expect(commitMemberImport).toHaveBeenCalledTimes(1);
  expect(commitMemberImport).toHaveBeenCalledWith(id, id);
});
it('restores a saved batch on refresh and prevents importing expired validation', async () => {
  vi.mocked(readMemberImport).mockResolvedValue({ value: { ...batch, validated_until: '2000-01-01T00:00:00Z' } });
  render(<MemberImportWizard contextId={id} tenantName="Example" initialId={id} />);
  expect(await screen.findByText(/Validation has expired/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Import 1 member' })).toBeDisabled();
});
it('forces whole-tenant scope for administrators and requires loaded options', async () => {
  const user = userEvent.setup();
  render(<MemberImportWizard contextId={id} tenantName="Example" />);
  await waitFor(() => expect(screen.getByLabelText('Department')).toBeEnabled());
  await user.selectOptions(screen.getByLabelText('Department'), id);
  await user.selectOptions(screen.getByLabelText('Role'), 'org_admin');
  expect(screen.getByLabelText('Department')).toBeDisabled();
  expect(screen.getByLabelText('Department')).toHaveValue('');
  expect(screen.getByText(/grants administrative access/)).toBeInTheDocument();
});
it('retains the review after an uncertain commit so the same batch can be retried', async () => {
  const user = userEvent.setup();
  render(<MemberImportWizard contextId={id} tenantName="Example" initialId={id} />);
  const button = await screen.findByRole('button', { name: 'Import 1 member' });
  vi.mocked(commitMemberImport).mockResolvedValue({ error: 'Connection interrupted. Retry this saved import.' });
  await user.click(button);
  expect(await screen.findByText(/Connection interrupted/)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Review before importing' })).toBeInTheDocument();
  expect(window.location.search).toBe('?batch=' + id);
});
it('explains that external sign-in imports must leave passwords blank', async () => {
  const user = userEvent.setup();
  render(<MemberImportWizard contextId={id} tenantName="Example" />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled());
  await user.selectOptions(screen.getByLabelText('Sign-in method'), 'oidc');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getByText(/leave Password blank/)).toBeInTheDocument();
  expect(screen.queryByText(/generate secure passwords/)).not.toBeInTheDocument();
});

it('links import history and shows recoverable passwords only after completion', async () => {
  const completed: MemberImport = { ...batch, status: 'completed', password_count: 1,
    counts: { total: 2, ready: 0, failed: 1, succeeded: 1 },
    rows: [{ ...batch.rows[0]!, status: 'succeeded', password: 'initial-test-password-2026', membership_id: id }, batch.rows[1]!],
  };
  vi.mocked(readMemberImport).mockResolvedValue({ value: completed });
  vi.mocked(memberImportHistory).mockResolvedValue({ value: [completed] });
  const view = render(<MemberImportWizard contextId={id} tenantName="Example" initialId={id} />);
  expect(await screen.findByText('initial-test-password-2026')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Import History' })).toHaveAttribute('href', '/members/import/history');
  expect(screen.getByRole('button', { name: 'Download passwords' })).toBeInTheDocument();
  view.unmount();
  render(<MemberImportHistory contextId={id} />);
  expect(await screen.findByRole('link', { name: 'View results' })).toHaveAttribute('href', '/members/import?batch=' + id);
  expect(screen.getByRole('button', { name: 'Download passwords' })).toBeInTheDocument();
});

it('shows history loading and recovers from a failed history request', async () => {
  const user = userEvent.setup();
  vi.mocked(memberImportHistory).mockRejectedValueOnce(new Error('network'));
  render(<MemberImportHistory contextId={id} />);
  expect(screen.getByRole('status')).toHaveTextContent('Loading imports');
  expect(await screen.findByText('Unable to load import history. Please retry.')).toBeInTheDocument();
  expect(screen.queryByText('No retained imports.')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Refresh' }));
  expect(await screen.findByText('No retained imports.')).toBeInTheDocument();
});
