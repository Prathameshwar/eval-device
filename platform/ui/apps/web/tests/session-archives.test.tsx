import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { SessionArchives } from '../src/components/SessionArchives';
import * as actions from '../src/lib/session-archive-actions';

vi.mock('../src/lib/session-archive-actions', () => ({ listArchives: vi.fn(), readArchive: vi.fn(), archiveTurns: vi.fn() }));
const row: actions.Archive = { id: 'archive', learner_name: 'No trainee assigned', scenario_title: 'Chest discomfort',
  created_at: '2026-10-05T10:00:00Z', sync_status: 'pending', received_items: 1, expected_items: 2,
  assigned_session_id: null, items: [] };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(actions.listArchives).mockResolvedValue({ value: { items: [row], next_cursor: null } });
  vi.mocked(actions.readArchive).mockResolvedValue({ value: { ...row, sync_status: 'incomplete', items: [
    { id: 'audio', kind: 'microphone', byte_size: 500, sequence: 0, available: true },
    { id: 'video', kind: 'video', byte_size: 800, sequence: 1, available: false },
  ] } });
  vi.mocked(actions.archiveTurns).mockResolvedValue({ value: { items: [{ turn_key: 'turn', occurred_at: row.created_at,
    input_text: 'Fictional question', response_text: 'Fictional answer', outcome: 'completed' }], next_offset: null } });
});
it('loads one page, shows honest sync state and streams only available recording links', async () => {
  render(<SessionArchives contextId="tenant" />);
  expect(await screen.findByText('Sync pending')).toBeInTheDocument();
  expect(actions.listArchives).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole('button', { name: 'View history & recordings' }));
  expect(await screen.findByText('Some capture data is missing')).toBeInTheDocument();
  expect(screen.getByText('Fictional answer')).toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: 'Download recording' })).toHaveLength(1);
  expect(screen.getByRole('link', { name: 'Download recording' })).toHaveAttribute('href', '/api/session-recordings?context=tenant&archive=archive&item=audio');
  expect(screen.getByText('Pending upload or retention expired', { exact: false })).toBeInTheDocument();
  expect(actions.readArchive).toHaveBeenCalledWith('tenant', 'archive');
});
it('fetches further pages only on demand and reports server failures', async () => {
  vi.mocked(actions.listArchives).mockResolvedValueOnce({ value: { items: [row], next_cursor: 'next' } });
  render(<SessionArchives contextId="tenant" />);
  await userEvent.click(await screen.findByRole('button', { name: 'Load more sessions' }));
  await waitFor(() => expect(actions.listArchives).toHaveBeenLastCalledWith('tenant', 'next'));
  vi.mocked(actions.listArchives).mockResolvedValue({ error: 'Connection unavailable' });
  await userEvent.click(screen.getByRole('button', { name: 'Refresh sync status' }));
  expect(await screen.findByText('Connection unavailable')).toBeInTheDocument();
});

it('shows pending transfer alongside incomplete capture and distinct retention deadlines', async () => {
  vi.mocked(actions.readArchive).mockResolvedValue({ value: { ...row, sync_status: 'incomplete',
    transfer_status: 'pending', capture_status: 'incomplete',
    media_expires_at: '2026-10-06T10:00:00Z', upload_until: '2026-10-12T10:00:00Z' } });
  render(<SessionArchives contextId="tenant" />);
  await userEvent.click(await screen.findByRole('button', { name: 'View history & recordings' }));
  expect(await screen.findByText('Some capture data is missing')).toBeInTheDocument();
  expect(screen.getByText('Uploads are still pending')).toBeInTheDocument();
  expect(screen.getByText('Recording retention deadline')).toBeInTheDocument();
  expect(screen.getByText('Result upload deadline')).toBeInTheDocument();
});

it('does not let a late response reopen a closed recording dialog', async () => {
  let finish!: (value: { value: actions.Archive }) => void;
  vi.mocked(actions.readArchive).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  render(<SessionArchives contextId="tenant" />);
  await userEvent.click(await screen.findByRole('button', { name: 'View history & recordings' }));
  expect(screen.getByRole('dialog', { name: 'History & recordings' })).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Loading history and recordings');
  await userEvent.click(screen.getByRole('button', { name: 'Done' }));
  await act(async () => { finish({ value: row }); });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
