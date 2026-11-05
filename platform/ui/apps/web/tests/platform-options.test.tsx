import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PlatformOptions } from '../src/components/PlatformOptions';
import { readPlatformOptions, savePlatformOptions, type PlatformOptions as Options } from '../src/lib/platform-options-actions';

vi.mock('../src/lib/platform-options-actions', () => ({ readPlatformOptions: vi.fn(), savePlatformOptions: vi.fn() }));
const options: Options = { configuration_version: 4, display_name: 'AI Evaluator', registration_mode: 'invite_only', maintenance_mode: false, enabled_providers: ['aws'], languages: [{ code: 'en', name: 'English', speech_locale: 'en-IN', is_active: true }] };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(readPlatformOptions).mockResolvedValue({ value: options });
  vi.mocked(savePlatformOptions).mockImplementation(async value => ({ value }));
});

it('groups settings clearly and saves new languages with the current version', async () => {
  const user = userEvent.setup(); render(<PlatformOptions canManage />);
  await screen.findByLabelText('Platform display name');
  for (const name of ['General settings', 'Maintenance', 'Cloud providers']) expect(screen.getByRole('region', { name })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Add language option' }));
  const language = within(screen.getByRole('group', { name: 'Language 2' }));
  await user.type(language.getByLabelText('Language name'), 'Hindi');
  await user.type(language.getByLabelText('Language code'), 'hi');
  await user.type(language.getByLabelText('Speech locale'), 'hi-IN');
  await user.click(screen.getByRole('button', { name: 'Save options' }));
  await screen.findByText('The platform options have been updated.');
  expect(savePlatformOptions).toHaveBeenCalledWith({ ...options, languages: [...options.languages, { code: 'hi', name: 'Hindi', speech_locale: 'hi-IN', is_active: true }] });
});

it('requires confirmation before saving maintenance changes and retains failed edits', async () => {
  vi.mocked(savePlatformOptions).mockResolvedValueOnce({ error: 'The options changed. Reload before saving.' });
  const user = userEvent.setup(); render(<PlatformOptions canManage />);
  await user.click(await screen.findByLabelText('Maintenance mode'));
  await user.click(screen.getByRole('button', { name: 'Save options' }));
  expect(savePlatformOptions).not.toHaveBeenCalled();
  await user.click(within(screen.getByRole('dialog', { name: 'Enable maintenance mode?' })).getByRole('button', { name: 'Save options' }));
  expect(await screen.findByText('The options changed. Reload before saving.')).toBeInTheDocument();
  expect(screen.getByLabelText('Maintenance mode')).toBeChecked();
});

it('keeps all controls read-only without management permission', async () => {
  render(<PlatformOptions canManage={false} />);
  expect(await screen.findByLabelText('Platform display name')).toBeDisabled();
  expect(screen.getByLabelText('Registration')).toBeDisabled();
  expect(screen.getByLabelText('Maintenance mode')).toBeDisabled();
  expect(screen.getByLabelText('Active language')).toBeDisabled();
  expect(screen.queryByRole('button', { name: 'Save options' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Add language option' })).not.toBeInTheDocument();
});

it('rejects disabling the default language and recovers from an initial load failure', async () => {
  vi.mocked(readPlatformOptions).mockResolvedValueOnce({ error: 'Unable to load settings.' });
  const user = userEvent.setup(); render(<PlatformOptions canManage />);
  await screen.findByText('Unable to load settings.');
  expect(screen.queryByText('Loading platform options…')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Reload' }));
  await screen.findByLabelText('Platform display name');
  await waitFor(() => expect(screen.queryByText('Unable to load settings.')).not.toBeInTheDocument());
  await user.click(screen.getByLabelText('Active language'));
  await user.click(screen.getByRole('button', { name: 'Save options' }));
  expect(await screen.findByText('Keep English (en) active as the default device language.')).toBeInTheDocument();
  expect(savePlatformOptions).not.toHaveBeenCalled();
});
