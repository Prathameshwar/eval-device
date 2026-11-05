import { ToastProvider } from '@pms/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { LogDetails } from '../src/components/LogDetails';
import { readLog } from '../src/lib/log-actions';
import { logUser, logRecord } from './fixtures/logs';
import type { ApiResult } from '../src/lib/directory-api';
import type { ActivityEvent } from '../src/lib/log-directory';
vi.mock('../src/lib/log-actions', () => ({ readLog: vi.fn() }));
beforeEach(() => { vi.mocked(readLog).mockReset(); vi.mocked(readLog).mockResolvedValue({ value: logRecord }); });
const show = () => render(<ToastProvider><LogDetails logId={logRecord.id} user={logUser} /></ToastProvider>);
it('loads details directly, focuses the heading, and explains omitted metadata', async () => {
  vi.mocked(readLog).mockResolvedValue({ value: { ...logRecord, details_redacted: true } });
  show();
  await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'device.status' })).toHaveFocus());
  expect(readLog).toHaveBeenCalledWith(logUser.contextId, logRecord.id);
  expect(screen.getByText(/Other payload fields have been omitted/)).toBeInTheDocument();
  expect(screen.getByText(/"status": "ready"/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Back to logs' })).toHaveAttribute('href', '/logs');
});
it('retries a missing or temporarily unavailable detail record', async () => {
  vi.mocked(readLog).mockResolvedValueOnce({ error: 'Record not found.' }).mockResolvedValue({ value: logRecord });
  const user = userEvent.setup(); show(); await screen.findByRole('heading', { name: 'Log not available' });
  await user.click(screen.getByRole('button', { name: 'Retry' }));
  expect(await screen.findByRole('heading', { name: 'device.status' })).toBeInTheDocument();
});
it('provides a manual copy fallback', async () => {
  const user = userEvent.setup(); show(); await screen.findByRole('heading', { name: 'device.status' });
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('Denied'));
  await user.click(screen.getByRole('button', { name: 'Copy log ID' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Clipboard unavailable');
  expect(screen.getByText(logRecord.id)).toHaveFocus();
});
it('discards late results after context changes', async () => {
  let resolve!: (value: ApiResult<ActivityEvent>) => void;
  vi.mocked(readLog).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const view = show();
  view.rerender(<ToastProvider><LogDetails logId={logRecord.id} user={{ ...logUser, contextId: 'new-context' }} /></ToastProvider>);
  await screen.findByRole('heading', { name: 'device.status' });
  resolve({ value: { ...logRecord, event_type: 'stale.event' } });
  await waitFor(() => expect(screen.queryByText('stale.event')).not.toBeInTheDocument());
});
