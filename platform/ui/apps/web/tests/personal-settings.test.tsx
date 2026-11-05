import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PersonalSettings } from '../src/components/PersonalSettings';
import * as actions from '../src/lib/personal-actions';
vi.mock('../src/lib/personal-actions', () => ({
  readPersonal: vi.fn(),
  savePersonal: vi.fn(),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(actions.readPersonal).mockResolvedValue({
    value: {
      display_name: 'Member',
      email: 'member@example.com',
      phone: null,
      auth_method: 'local',
    },
  });
});
it('saves only the editable personal fields and keeps the sign-in email read-only', async () => {
  const visitor = userEvent.setup();
  vi.mocked(actions.savePersonal).mockResolvedValue({
    value: {
      display_name: 'Updated',
      email: 'member@example.com',
      phone: '123',
      auth_method: 'local',
    },
  });
  render(<PersonalSettings />);
  const name = await screen.findByLabelText('Display name');
  await visitor.clear(name);
  await visitor.type(name, 'Updated');
  await visitor.type(screen.getByLabelText('Phone'), '123');
  expect(screen.getByLabelText('Sign-in email')).toHaveAttribute('readonly');
  await visitor.click(screen.getByRole('button', { name: 'Save profile' }));
  expect(await screen.findByText('Your account details have been updated.')).toBeInTheDocument();
  expect(actions.savePersonal).toHaveBeenCalledWith('Updated', '123');
});
it('keeps the profile fields on API refusal', async () => {
  const visitor = userEvent.setup();
  vi.mocked(actions.savePersonal).mockResolvedValue({
    error: 'Unable to save.',
  });
  render(<PersonalSettings />);
  await screen.findByLabelText('Display name');
  await visitor.click(screen.getByRole('button', { name: 'Save profile' }));
  expect(await screen.findByText('Unable to save.')).toBeInTheDocument();
  expect(screen.getByLabelText('Display name')).toHaveValue('Member');
});
