import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AccountActionForm } from '../src/components/AccountActionForm';
import { ChangePasswordDialog } from '../src/components/ChangePasswordDialog';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const token = 'act_' + 't'.repeat(43);
beforeEach(() => { window.history.replaceState(null, '', '/account/setup#token=' + token); });

it('reads the fragment once, removes it from the address bar and completes setup', async () => {
  const user = userEvent.setup();
  const complete = vi.fn(async () => ({ completed: true }));
  const { container } = render(<AccountActionForm purpose="setup" complete={complete} />);
  await waitFor(() => expect(location.hash).toBe(''));
  expect(container.textContent).not.toContain(token);
  expect(complete).not.toHaveBeenCalled();
  await user.type(screen.getByLabelText('New password'), 'a new test password long enough');
  await user.type(screen.getByLabelText('Confirm new password'), 'a new test password long enough');
  await user.click(screen.getByRole('button', { name: 'Save password' }));
  expect(complete).toHaveBeenCalledWith('setup', token, 'a new test password long enough');
  expect(await screen.findByRole('status')).toHaveTextContent('Account updated');
});
it('requires an explicit confirmation rather than consuming an email link on open', async () => {
  const user = userEvent.setup();
  const complete = vi.fn(async () => ({ completed: true }));
  render(<AccountActionForm purpose="email-change" complete={complete} />);
  expect(complete).not.toHaveBeenCalled();
  await user.click(await screen.findByRole('button', { name: 'Confirm email change' }));
  expect(complete).toHaveBeenCalledWith('email-change', token, undefined);
});
it('handles expired links and permits a transport retry', async () => {
  const user = userEvent.setup();
  const complete = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ error: 'This link is invalid, expired, or already used. Request a new link.' });
  render(<AccountActionForm purpose="email-change" complete={complete} />);
  await user.click(await screen.findByRole('button', { name: 'Confirm email change' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to connect');
  await user.click(screen.getByRole('button', { name: 'Confirm email change' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('expired');
});
it('shows a missing-link error instead of sending an empty token', async () => {
  window.history.replaceState(null, '', '/account/setup');
  const complete = vi.fn();
  render(<AccountActionForm purpose="setup" complete={complete} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Open the complete link');
  expect(complete).not.toHaveBeenCalled();
});
it('posts a password change, clears secrets and asks for a fresh login', async () => {
  const user = userEvent.setup();
  const updatePassword = vi.fn(async () => ({ completed: true }));
  render(<ChangePasswordDialog open email="real@example.com" onClose={() => {}} updatePassword={updatePassword} />);
  await user.type(screen.getByLabelText('Current password'), 'old password long enough');
  await user.type(screen.getByLabelText('New password'), 'new password long enough');
  await user.type(screen.getByLabelText('Confirm new password'), 'new password long enough');
  await user.click(screen.getByRole('button', { name: 'Update password' }));
  expect(updatePassword).toHaveBeenCalledWith('old password long enough', 'new password long enough');
  expect(await screen.findByRole('status')).toHaveTextContent('Password changed');
  expect(screen.queryByLabelText('Current password')).not.toBeInTheDocument();
});

it('accepts another emailed fragment on the same page after completion', async () => {
  const user = userEvent.setup();
  const complete = vi.fn(async () => ({ completed: true }));
  render(<AccountActionForm purpose="email-change" complete={complete} />);
  await user.click(await screen.findByRole('button', { name: 'Confirm email change' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Account updated');
  const nextToken = 'act_' + 'n'.repeat(43);
  window.history.replaceState(null, '', '/account/email-change#token=' + nextToken);
  act(() => window.dispatchEvent(new HashChangeEvent('hashchange')));
  await user.click(await screen.findByRole('button', { name: 'Confirm email change' }));
  expect(complete).toHaveBeenLastCalledWith('email-change', nextToken, undefined);
  expect(location.hash).toBe('');
});
