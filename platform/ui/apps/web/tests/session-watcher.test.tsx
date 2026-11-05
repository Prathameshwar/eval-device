import { act, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SessionWatcher } from '../src/components/SessionWatcher';
import { checkSession } from '../src/lib/actions';

const router = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('../src/lib/actions', () => ({ checkSession: vi.fn() }));

beforeEach(() => {
  vi.mocked(checkSession).mockReset();
  router.replace.mockReset();
});
afterEach(() => vi.restoreAllMocks());

it('rechecks an open tab and redirects only when its session has expired', async () => {
  vi.mocked(checkSession)
    .mockResolvedValueOnce('active')
    .mockResolvedValueOnce('unavailable')
    .mockResolvedValueOnce('expired');
  const view = render(<SessionWatcher />);

  await act(async () => fireEvent.focus(window));
  expect(checkSession).toHaveBeenCalledTimes(1);
  expect(router.replace).not.toHaveBeenCalled();

  await act(async () => fireEvent.focus(window));
  expect(checkSession).toHaveBeenCalledTimes(2);
  expect(router.replace).not.toHaveBeenCalled();

  await act(async () => fireEvent.focus(window));
  expect(router.replace).toHaveBeenCalledWith('/login');
  view.unmount();
  fireEvent.focus(window);
  expect(checkSession).toHaveBeenCalledTimes(3);
});

it('detects expiry while the visible tab stays open', async () => {
  vi.useFakeTimers();
  try {
    vi.mocked(checkSession).mockResolvedValue('expired');
    const view = render(<SessionWatcher />);
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(checkSession).toHaveBeenCalledTimes(1);
    expect(router.replace).toHaveBeenCalledWith('/login');
    view.unmount();
  } finally {
    vi.useRealTimers();
  }
});
