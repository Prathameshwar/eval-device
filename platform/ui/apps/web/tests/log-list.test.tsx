import { PermissionProvider, ToastProvider } from '@pms/ui';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { LogDirectoryProvider } from '../src/components/LogDirectoryProvider';
import { LogList } from '../src/components/LogList';
import { listLogs } from '../src/lib/log-actions';
import { logUser, logRecord, logPage } from './fixtures/logs';
vi.mock('../src/lib/log-actions', () => ({ listLogs: vi.fn() }));
beforeEach(() => { vi.mocked(listLogs).mockReset(); vi.mocked(listLogs).mockResolvedValue({ value: logPage }); });
function show(user = logUser) {
  return render(<PermissionProvider permissions={user.permissions}><ToastProvider><LogDirectoryProvider user={user}><LogList /></LogDirectoryProvider></ToastProvider></PermissionProvider>);
}
it('loads real rows with detail links and counts', async () => {
  show();
  expect(await screen.findByRole('link', { name: 'device.status' })).toHaveAttribute('href', '/logs/' + logRecord.id);
  expect(screen.getByText('1 log', { exact: true })).toBeInTheDocument();
});
it('sends search and category filters to the server and resets them', async () => {
  const user = userEvent.setup(); show();
  await screen.findByRole('link', { name: 'device.status' });
  await user.type(screen.getByRole('searchbox', { name: 'Search logs' }), 'missing');
  await waitFor(() => expect(listLogs).toHaveBeenLastCalledWith(logUser.contextId, expect.objectContaining({ q: 'missing' }), undefined));
  await user.selectOptions(screen.getByLabelText('Category'), 'audit');
  await waitFor(() => expect(listLogs).toHaveBeenLastCalledWith(logUser.contextId, expect.objectContaining({ category: 'audit' }), undefined));
  await user.click(screen.getByRole('button', { name: 'Clear filters' }));
  await waitFor(() => expect(listLogs).toHaveBeenLastCalledWith(logUser.contextId, expect.objectContaining({ q: '', category: 'all' }), undefined));
});
it('uses server cursors and resets pagination when filters change', async () => {
  vi.mocked(listLogs).mockResolvedValue({ value: { ...logPage, next_cursor: 'signed', has_more: true, total: 30 } });
  const user = userEvent.setup(); show(); await screen.findByRole('link', { name: 'device.status' });
  await user.click(screen.getByRole('button', { name: 'Next page of logs' }));
  await waitFor(() => expect(listLogs).toHaveBeenLastCalledWith(logUser.contextId, expect.anything(), 'signed'));
  await user.selectOptions(screen.getByLabelText('Severity'), 'error');
  await waitFor(() => expect(listLogs).toHaveBeenLastCalledWith(logUser.contextId, expect.objectContaining({ severity: 'error' }), undefined));
});
it('shows empty results and offers recovery from server errors', async () => {
  vi.mocked(listLogs).mockResolvedValueOnce({ error: 'Temporary failure' }).mockResolvedValue({ value: { ...logPage, items: [], total: 0 } });
  const user = userEvent.setup(); show(); await screen.findByText('Temporary failure');
  await user.click(screen.getByRole('button', { name: 'Refresh logs' }));
  expect(await screen.findByText('No logs recorded yet')).toBeInTheDocument();
});
it('only offers operational logs for activity-only users', async () => {
  show({ ...logUser, permissions: ['org.activity.read'] }); await screen.findByRole('link', { name: 'device.status' });
  expect(screen.queryByRole('option', { name: 'Audit' })).not.toBeInTheDocument();
  expect(listLogs).toHaveBeenCalledWith(logUser.contextId, expect.objectContaining({ category: 'operational' }), undefined);
});
it('copies the persisted event ID', async () => {
  const user = userEvent.setup(); show(); await screen.findByRole('link', { name: 'device.status' });
  const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
  await user.click(screen.getByRole('button', { name: 'Copy ID for device.status' }));
  expect(copy).toHaveBeenCalledWith(logRecord.id);
});

it('keeps date filters pending until Apply and clears both draft and applied values', async () => {
  const user = userEvent.setup(); show();
  await screen.findByRole('link', { name: 'device.status' });
  vi.mocked(listLogs).mockClear();
  fireEvent.change(screen.getByLabelText('Occurred from (UTC)'), { target: { value: '2026-09-01' } });
  fireEvent.change(screen.getByLabelText('Occurred through (UTC)'), { target: { value: '2026-09-30' } });
  expect(listLogs).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Apply date and ID filters' }));
  await waitFor(() => expect(listLogs).toHaveBeenLastCalledWith(logUser.contextId,
    expect.objectContaining({ since: '2026-09-01', until: '2026-09-30' }), undefined));
  await user.click(screen.getByRole('button', { name: 'Clear filters' }));
  expect(screen.getByLabelText('Occurred from (UTC)')).toHaveValue('');
  expect(screen.getByLabelText('Occurred through (UTC)')).toHaveValue('');
  await waitFor(() => expect(listLogs).toHaveBeenLastCalledWith(logUser.contextId,
    expect.objectContaining({ since: '', until: '' }), undefined));
});

it('applies the platform tenant ID filter only after submission', async () => {
  const user = userEvent.setup();
  show({ ...logUser, contextId: 'platform', permissions: ['platform.audit.read'] });
  await screen.findByRole('link', { name: 'device.status' });
  vi.mocked(listLogs).mockClear();
  await user.type(screen.getByLabelText('Tenant ID'), logRecord.organization_id!);
  expect(listLogs).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Apply date and ID filters' }));
  await waitFor(() => expect(listLogs).toHaveBeenLastCalledWith('platform',
    expect.objectContaining({ organization_id: logRecord.organization_id, category: 'audit' }), undefined));
});
