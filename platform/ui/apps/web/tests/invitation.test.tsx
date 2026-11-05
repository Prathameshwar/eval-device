import { StrictMode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }));
vi.mock('../src/lib/invitation-actions', () => ({ joinInvitation: vi.fn() }));
import { joinInvitation } from '../src/lib/invitation-actions';
import { InvitationForm } from '../src/components/InvitationForm';
const token = 'inv_' + 'a'.repeat(40);
beforeEach(() => { vi.clearAllMocks(); window.history.replaceState(null, '', '/invitations/accept#token=' + token); });
it('removes tokens from the address and accepts only on explicit submission', async () => {
  const user = userEvent.setup(); vi.mocked(joinInvitation).mockResolvedValue({ value: true });
  render(<StrictMode><InvitationForm signedInEmail="person@example.com" /></StrictMode>);
  await waitFor(() => expect(window.location.hash).toBe(''));
  expect(joinInvitation).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Accept invitation' }));
  expect(joinInvitation).toHaveBeenCalledWith(token, undefined);
  expect(await screen.findByText(/Invitation accepted/)).toBeInTheDocument();
});
it('does not submit missing or malformed invitations', async () => {
  window.history.replaceState(null, '', '/invitations/accept#token=bad');
  render(<InvitationForm />);
  expect(await screen.findByText(/Open the complete invitation link/)).toBeInTheDocument();
  expect(joinInvitation).not.toHaveBeenCalled();
});
it('signs in on the invitation page and preserves the link when identity is rejected', async () => {
  const user = userEvent.setup(); vi.mocked(joinInvitation).mockResolvedValue({ error: 'Use the invited email.' });
  render(<InvitationForm />);
  await user.type(screen.getByLabelText('Email address'), 'wrong@example.com');
  await user.type(screen.getByLabelText('Password'), 'test password');
  await user.click(screen.getByRole('button', { name: 'Sign in and accept' }));
  expect(await screen.findByText('Use the invited email.')).toBeInTheDocument();
  expect(screen.getByLabelText('Password')).toHaveValue('');
  expect(joinInvitation).toHaveBeenCalledWith(token, { email: 'wrong@example.com', password: 'test password' });
});
