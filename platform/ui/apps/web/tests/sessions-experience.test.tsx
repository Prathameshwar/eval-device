import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { SessionHistory } from '../src/components/SessionHistory';
import { SessionDetails } from '../src/components/SessionDetails';
import { SessionQueueWorkspace } from '../src/components/SessionQueueWorkspace';
import * as actions from '../src/lib/session-queue-actions';
import * as archives from '../src/lib/session-archive-actions';

vi.mock('../src/lib/session-queue-actions', () => ({
  sessionHistory: vi.fn(), practiceSessionResult: vi.fn(), readQueue: vi.fn(), queueLearners: vi.fn(),
  planSessions: vi.fn(), changeQueue: vi.fn(), editQueuedSession: vi.fn(), endQueuedSession: vi.fn(),
}));
vi.mock('../src/lib/history-actions', () => ({ historyOptions: vi.fn() }));
vi.mock('../src/lib/session-archive-actions', () => ({
  listArchives: vi.fn(async () => ({ value: { items: [], next_cursor: null } })), readArchive: vi.fn(), archiveTurns: vi.fn(),
}));
const row: actions.QueuedSession = { id: 'one', device_id: 'device', learner_id: 'learner', learner_name: 'Priya Rao',
  scenario_id: 'case', scenario_title: 'Wheeze interview', language: 'en', duration_seconds: 300, status: 'completed',
  created_at: '2026-10-05T10:00:00Z', expires_at: '2026-10-06T10:00:00Z', started_at: '2026-10-05T10:01:00Z', ended_at: '2026-10-05T10:06:00Z' };
const entry = (session: actions.QueuedSession): actions.SessionHistoryEntry => ({ id: session.id, kind: 'assigned', session, archive: null });
const result: actions.SessionResult = { session: row, history_available: true, provenance: 'client_reported', messages: [
  { role: 'user', content: 'When did the cough begin?' }, { role: 'assistant', content: 'It started three days ago.' },
] };
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(archives.readArchive).mockResolvedValue({ value: { id: 'archive-one', learner_name: row.learner_name, scenario_title: row.scenario_title, created_at: row.created_at, sync_status: 'synced', received_items: 2, expected_items: 2, assigned_session_id: row.id, items: [{ id: 'audio', kind: 'patient_audio', sequence: 0, byte_size: 1000, available: true }] } });
  vi.mocked(actions.sessionHistory).mockResolvedValue({ value: { items: [entry(row)], next_cursor: null } });
  vi.mocked(actions.practiceSessionResult).mockResolvedValue({ value: result });
});
it('distinguishes loading, failure and empty history and supports retry', async () => {
  let finish!: (value: { error: string }) => void;
  vi.mocked(actions.sessionHistory).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  render(<SessionHistory contextId="tenant" onInspect={vi.fn()} />);
  expect(screen.getByRole('status')).toHaveTextContent('Loading session history');
  expect(screen.queryByText('No session history yet')).not.toBeInTheDocument();
  await act(async () => { finish({ error: 'Connection unavailable' }); });
  expect(screen.getByRole('alert')).toHaveTextContent('Connection unavailable');
  expect(screen.queryByText('No session history yet')).not.toBeInTheDocument();
  vi.mocked(actions.sessionHistory).mockResolvedValue({ value: { items: [], next_cursor: null } });
  await userEvent.click(screen.getByRole('button', { name: 'Refresh history' }));
  expect(await screen.findByText('No session history yet')).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
it('loads history pages on demand, deduplicates rows and opens the requested session', async () => {
  vi.mocked(actions.sessionHistory).mockResolvedValueOnce({ value: { items: [entry(row)], next_cursor: 'next' } })
    .mockResolvedValueOnce({ value: { items: [entry(row), entry({ ...row, id: 'two', learner_name: 'Navin Saini' })], next_cursor: null } });
  const inspect = vi.fn();
  render(<SessionHistory contextId="tenant" onInspect={inspect} />);
  await screen.findByText('Priya Rao');
  expect(actions.sessionHistory).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole('button', { name: 'Load more sessions' }));
  expect(await screen.findByText('Navin Saini')).toBeInTheDocument();
  expect(screen.getAllByText('Priya Rao')).toHaveLength(1);
  expect(actions.sessionHistory).toHaveBeenLastCalledWith('tenant', 'next');
  await userEvent.click(within(screen.getByText('Navin Saini').closest('tr')!).getByRole('button', { name: 'View session' }));
  expect(inspect).toHaveBeenCalledWith('two', 'assigned');
});
it('shows a details loading dialog, retries a failure, then renders separate speakers', async () => {
  vi.mocked(actions.practiceSessionResult).mockResolvedValueOnce({ error: 'Session temporarily unavailable' });
  const recordings = vi.fn();
  render(<SessionDetails contextId="tenant" id="one" onClose={vi.fn()} onRecordings={recordings} />);
  expect(screen.getByRole('dialog', { name: 'Session details' })).toBeInTheDocument();
  expect(await screen.findByText('Session temporarily unavailable')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
  const conversation = await screen.findByRole('region', { name: 'Session conversation' });
  expect(within(conversation).getByText('When did the cough begin?')).toBeInTheDocument();
  expect(within(conversation).getByText('It started three days ago.')).toBeInTheDocument();
  expect(within(conversation).getByText('Patient')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Back to session history' }));
  expect(recordings).toHaveBeenCalledOnce();
});
it('ignores an old history response after a context change', async () => {
  let finish!: (value: { value: { items: actions.SessionHistoryEntry[]; next_cursor: null } }) => void;
  vi.mocked(actions.sessionHistory).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }))
    .mockResolvedValueOnce({ value: { items: [entry({ ...row, learner_name: 'Current tenant learner' })], next_cursor: null } });
  const { rerender } = render(<SessionHistory contextId="first" onInspect={vi.fn()} />);
  rerender(<SessionHistory contextId="second" onInspect={vi.fn()} />);
  await screen.findByText('Current tenant learner');
  await act(async () => { finish({ value: { items: [entry(row)], next_cursor: null } }); });
  expect(screen.queryByText('Priya Rao')).not.toBeInTheDocument();
});
it('shows archived conversation when optional live reporting saved no messages and pages all turns', async () => {
  vi.mocked(actions.practiceSessionResult).mockResolvedValue({ value: { ...result, messages: [], archive_id: 'archive-one' } });
  const first = { turn_key: 'turn-one', input_text: 'What helps?', response_text: 'Rest helps.', occurred_at: row.created_at, outcome: 'completed' };
  vi.mocked(archives.archiveTurns).mockResolvedValueOnce({ value: { items: [first], next_offset: 25 } })
    .mockResolvedValueOnce({ value: { items: [first, { ...first, turn_key: 'turn-two', input_text: 'Who prescribed it?', response_text: 'My doctor.' }], next_offset: null } });
  render(<SessionDetails contextId="tenant" id="one" onClose={vi.fn()} onRecordings={vi.fn()} />);
  expect(await screen.findByText('Rest helps.')).toBeInTheDocument();
  expect(screen.queryByText('No conversation available')).not.toBeInTheDocument();
  expect(archives.archiveTurns).toHaveBeenCalledWith('tenant', 'archive-one');
  expect(await screen.findByText('Fully synced')).toBeInTheDocument();
  expect(screen.getByText('2 / 2 expected')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Download recording' })).toHaveAttribute('href', '/api/session-recordings?context=tenant&archive=archive-one&item=audio');
  await userEvent.click(screen.getByRole('button', { name: 'Load more conversation' }));
  expect(await screen.findByText('My doctor.')).toBeInTheDocument();
  expect(screen.getAllByText('Rest helps.')).toHaveLength(1);
  expect(archives.archiveTurns).toHaveBeenLastCalledWith('tenant', 'archive-one', 25);
});
it('shows separate completion and sync values and keeps standalone captures in the same list', async () => {
  const archive = { id: 'saved-one', learner_name: row.learner_name, scenario_title: row.scenario_title, created_at: row.created_at, sync_status: 'incomplete', received_items: 16, expected_items: 66, assigned_session_id: row.id, items: [] };
  vi.mocked(actions.sessionHistory).mockResolvedValue({ value: { items: [
    { ...entry(row), archive },
    { id: 'standalone', kind: 'standalone', session: null, archive: { ...archive, id: 'standalone', assigned_session_id: null, learner_name: 'No trainee assigned', sync_status: 'synced', outcome: 'completed' } },
  ], next_cursor: null } });
  const inspect = vi.fn();
  render(<SessionHistory contextId="tenant" onInspect={inspect} />);
  const assigned = (await screen.findByText('Priya Rao')).closest('tr')!;
  expect(within(assigned).getByText('Completed')).toBeInTheDocument();
  expect(within(assigned).getByText('Missing capture data')).toBeInTheDocument();
  expect(within(assigned).getByText('16 saved / 66 expected')).toBeInTheDocument();
  const standalone = screen.getByText('Standalone practice').closest('tr')!;
  await userEvent.click(within(standalone).getByRole('button', { name: 'View session' }));
  expect(inspect).toHaveBeenCalledWith('standalone', 'standalone');
});
it('reports an archive read failure without claiming no conversation exists', async () => {
  vi.mocked(actions.practiceSessionResult).mockResolvedValue({ value: { ...result, messages: [], archive_id: 'archive-one' } });
  vi.mocked(archives.archiveTurns).mockResolvedValue({ error: 'Saved results unavailable' });
  render(<SessionDetails contextId="tenant" id="one" onClose={vi.fn()} onRecordings={vi.fn()} />);
  expect(await screen.findByText('Saved results unavailable')).toBeInTheDocument();
  expect(screen.queryByText('Conversation upload pending')).not.toBeInTheDocument();
});
it('shows one named history panel and never exposes queue management to a trainee', async () => {
  render(<SessionQueueWorkspace contextId="tenant" canManage={false} />);
  const historyTab = screen.getByRole('tab', { name: 'Session history' });
  expect(historyTab).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('tabpanel', { name: 'Session history' })).toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: 'Recordings & sync' })).not.toBeInTheDocument();
  expect(screen.getAllByRole('tab')).toHaveLength(1);
  expect(screen.queryByRole('tab', { name: 'Device queue' })).not.toBeInTheDocument();
  expect(actions.readQueue).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
});
