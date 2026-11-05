import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

vi.mock('../src/lib/session', () => ({ currentUser: vi.fn() }));
import { currentUser } from '../src/lib/session';
import { ApiError } from '../src/lib/api';
import Home from '../src/app/page';
import { LandingPage } from '../src/components/landing/LandingPage';

beforeEach(() => { vi.mocked(currentUser).mockResolvedValue(undefined); });

it('renders the public homepage for a visitor and links into existing authentication', async () => {
  render(await Home());
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bring clinical learning to life.');
  expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(6);
  expect(screen.getAllByRole('link', { name: 'Login' })[0]).toHaveAttribute('href', '/login');
  expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
});

it('keeps the homepage public for signed-in users and offers their workspace', async () => {
  vi.mocked(currentUser).mockResolvedValue({ id: 'verified-user' } as NonNullable<Awaited<ReturnType<typeof currentUser>>>);
  render(await Home());
  expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: 'My Account' })[0]).toHaveAttribute('href', '/home');
  expect(screen.queryByRole('link', { name: 'Login' })).not.toBeInTheDocument();
});

it('keeps public information available during an account service outage', async () => {
  vi.mocked(currentUser).mockRejectedValue(new ApiError(503, 'unavailable'));
  render(await Home());
  expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: 'Login' })[0]).toHaveAttribute('href', '/login');
});

it('does not silently swallow unexpected failures', async () => {
  vi.mocked(currentUser).mockRejectedValue(new Error('unexpected'));
  await expect(Home()).rejects.toThrow('unexpected');
});

it('closes mobile navigation with Escape and returns focus to its control', () => {
  const { container } = render(<LandingPage signedIn={false} />);
  const menu = container.querySelector('header details') as HTMLDetailsElement;
  const summary = menu.querySelector('summary')!;
  menu.open = true;
  const link = within(menu).getByRole('link', { name: 'Meet Alex' });
  link.focus();
  fireEvent.keyDown(link, { key: 'Escape' });
  expect(menu.open).toBe(false);
  expect(summary).toHaveFocus();
});

it('closes mobile navigation and moves focus to the selected section', () => {
  const { container } = render(<LandingPage signedIn={false} />);
  const menu = container.querySelector('header details') as HTMLDetailsElement;
  menu.open = true;
  fireEvent.click(within(menu).getByRole('link', { name: 'Meet Alex' }));
  expect(menu.open).toBe(false);
  expect(container.querySelector('#alex')).toHaveFocus();
});

it('closes an open mobile menu when the visitor interacts outside it', () => {
  const { container } = render(<LandingPage signedIn={false} />);
  const menu = container.querySelector('header details') as HTMLDetailsElement;
  menu.open = true;
  fireEvent.pointerDown(screen.getByRole('heading', { level: 1 }));
  expect(menu.open).toBe(false);
});
