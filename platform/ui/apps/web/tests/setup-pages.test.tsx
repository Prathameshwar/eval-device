import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({ redirect: vi.fn((path: string) => { throw new Error(`redirect:${path}`); }) }));
vi.mock('../src/lib/session', () => ({ currentUser: vi.fn() }));
vi.mock('../src/lib/setup', () => ({ setupStatus: vi.fn() }));
import { currentUser } from '../src/lib/session';
import { setupStatus } from '../src/lib/setup';
import LoginPage from '../src/app/(auth)/login/page';
import SetupPage from '../src/app/(auth)/setup/page';

beforeEach(() => { vi.mocked(currentUser).mockResolvedValue(undefined); });

it('routes a fresh installation from login into setup', async () => {
  vi.mocked(setupStatus).mockResolvedValue({ required: true, available: true });
  await expect(LoginPage()).rejects.toThrow('redirect:/setup');
  render(await SetupPage());
  expect(screen.getByRole('heading', { name: 'Set up your platform' })).toBeInTheDocument();
});

it('keeps setup closed and shows login on an existing installation', async () => {
  vi.mocked(setupStatus).mockResolvedValue({ required: false, available: false });
  await expect(SetupPage()).rejects.toThrow('redirect:/login');
  render(await LoginPage());
  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
});

it('explains a missing configuration without rendering account creation', async () => {
  vi.mocked(setupStatus).mockResolvedValue({ required: true, available: false });
  render(await SetupPage());
  expect(screen.getByText('Setup is not enabled yet')).toBeInTheDocument();
  expect(screen.queryByLabelText('Installation key')).not.toBeInTheDocument();
});

it('offers a full reload after an API outage', async () => {
  vi.mocked(setupStatus).mockResolvedValue(null);
  render(await SetupPage());
  expect(screen.getByText('Unable to check setup')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Check again' })).toHaveAttribute('href', '/setup');
});
