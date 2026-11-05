import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { StartSessionPage } from '../src/components/StartSessionPage';
import { SessionQueueWorkspace } from '../src/components/SessionQueueWorkspace';
import { canStartSession } from '../src/lib/session-start';
import { historyOptions } from '../src/lib/history-actions';
import * as actions from '../src/lib/session-queue-actions';

vi.mock('../src/lib/history-actions', () => ({ historyOptions: vi.fn() }));
vi.mock('../src/lib/session-queue-actions', () => ({
  readQueue: vi.fn(), queueLearners: vi.fn(), planSessions: vi.fn(), changeQueue: vi.fn(),
  editQueuedSession: vi.fn(), endQueuedSession: vi.fn(), practiceSessionResult: vi.fn(), practiceSessionHistory: vi.fn(), sessionHistory: vi.fn(),
}));
const options = {
  devices: [{ id: 'device', name: 'Practice laptop' }], learners: [],
  scenarios: [{ id: 'case', title: 'Chest discomfort', languages: ['en', 'hi'] },
    { id: 'second', title: 'Wheeze', languages: ['en'] }],
};
const empty: actions.SessionQueue = { revision: 1, paused: false, connected: true, runtime_state: 'idle', items: [], history: [] };
const row: actions.QueuedSession = { id: 'one', device_id: 'device', learner_id: 'learner', learner_name: 'Alex Student',
  scenario_id: 'case', scenario_title: 'Chest discomfort', language: 'en', duration_seconds: 300, status: 'queued',
  created_at: '2026-10-05T10:00:00Z', expires_at: '2026-10-06T10:00:00Z', started_at: null, ended_at: null };
beforeEach(() => {
  vi.resetAllMocks();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  vi.mocked(historyOptions).mockResolvedValue({ value: options });
  vi.mocked(actions.readQueue).mockResolvedValue({ value: empty });
  vi.mocked(actions.queueLearners).mockResolvedValue({ value: [{ id: 'learner', name: 'Alex Student' }, { id: 'other', name: 'Priya Rao' }] });
  vi.mocked(actions.planSessions).mockResolvedValue({ value: { ...empty, revision: 2, items: [row] } });
  vi.mocked(actions.changeQueue).mockResolvedValue({ value: empty });
  vi.mocked(actions.endQueuedSession).mockResolvedValue({ value: empty });
  vi.mocked(actions.sessionHistory).mockResolvedValue({ value: { items: [], next_cursor: null } });
});

it('requires every session-start capability', () => {
  const permissions = ['org.results.read', 'org.processing.execute', 'org.playback.execute', 'org.training.instruct'];
  expect(canStartSession(permissions)).toBe(true);
  for (const permission of permissions) expect(canStartSession(permissions.filter(p => p !== permission))).toBe(false);
});
it('plans multiple trainees with per-row settings and a fixed expiry explanation', async () => {
  render(<StartSessionPage contextId="tenant" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Alex Student'));
  await user.click(screen.getByLabelText('Priya Rao'));
  await user.selectOptions(screen.getByLabelText('Trainee 2 · Language'), 'hi');
  await user.click(screen.getByRole('button', { name: 'Add 2 to queue' }));
  expect(actions.planSessions).not.toHaveBeenCalled();
  const review = screen.getByRole('dialog', { name: 'Confirm device assignment' });
  expect(within(review).getByRole('region', { name: 'Assignment device' })).toHaveTextContent('Practice laptop');
  expect(within(review).getByText('Device ID: device')).toBeInTheDocument();
  await user.click(within(review).getByRole('button', { name: 'Confirm & add to queue' }));
  await waitFor(() => expect(actions.planSessions).toHaveBeenCalledTimes(1));
  expect(actions.planSessions).toHaveBeenCalledWith('tenant', 'device', { request_key: expect.any(String), items: [
    { learner_id: 'learner', scenario_id: 'case', language: 'en', duration_seconds: 300 },
    { learner_id: 'other', scenario_id: 'case', language: 'hi', duration_seconds: 300 },
  ] });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.getByText(/Every assignment expires 24 hours/)).toBeInTheDocument();
});
it('keeps one request identity when retrying an uncertain batch, without automatic resubmission', async () => {
  vi.mocked(actions.planSessions).mockRejectedValueOnce(new Error('transport'));
  render(<StartSessionPage contextId="tenant" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Alex Student'));
  await user.click(screen.getByRole('button', { name: 'Add 1 to queue' }));
  await user.click(screen.getByRole('button', { name: 'Confirm & add to queue' }));
  expect(await screen.findByText(/could not be confirmed/)).toBeInTheDocument();
  expect(actions.planSessions).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button', { name: 'Confirm & add to queue' }));
  await waitFor(() => expect(actions.planSessions).toHaveBeenCalledTimes(2));
  expect(vi.mocked(actions.planSessions).mock.calls[0]).toEqual(vi.mocked(actions.planSessions).mock.calls[1]);
});
it('does not submit twice while planning is pending', async () => {
  vi.mocked(actions.planSessions).mockReturnValue(new Promise(() => {}));
  render(<StartSessionPage contextId="tenant" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Alex Student'));
  await user.click(screen.getByRole('button', { name: 'Add 1 to queue' }));
  await user.dblClick(screen.getByRole('button', { name: 'Confirm & add to queue' }));
  expect(actions.planSessions).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText('Device')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Close panel' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Change device' })).toBeDisabled();
});

it('changes the device during review, preserves sessions and opens the chosen queue', async () => {
  vi.mocked(historyOptions).mockResolvedValue({ value: { ...options,
    devices: [...options.devices, { id: 'other-device', name: 'GPU laptop' }],
  } });
  vi.mocked(actions.readQueue).mockImplementation(async (_context, device) => ({ value: {
    ...empty, revision: device === 'device' ? 100 : 1,
  } }));
  render(<StartSessionPage contextId="tenant" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Alex Student'));
  await user.selectOptions(screen.getByLabelText('Trainee 1 · Language'), 'hi');
  await user.click(screen.getByRole('button', { name: 'Add 1 to queue' }));
  await user.click(screen.getByRole('button', { name: 'Change device' }));
  await user.selectOptions(screen.getByLabelText('Assign to device'), 'other-device');
  await waitFor(() => expect(actions.queueLearners).toHaveBeenLastCalledWith('tenant', 'other-device'));
  expect(screen.getByLabelText('Trainee 1 · Language')).toHaveValue('hi');
  await user.click(screen.getByRole('button', { name: 'Add 1 to queue' }));
  const target = screen.getByRole('region', { name: 'Assignment device' });
  expect(target).toHaveTextContent('GPU laptop');
  expect(target).toHaveTextContent('Device ID: other-device');
  expect(actions.planSessions).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Confirm & add to queue' }));
  await waitFor(() => expect(actions.planSessions).toHaveBeenCalledWith('tenant', 'other-device', {
    request_key: expect.any(String), items: [{ learner_id: 'learner', scenario_id: 'case', language: 'hi', duration_seconds: 300 }],
  }));
  await waitFor(() => expect(screen.getByLabelText('Device')).toHaveValue('other-device'));
  expect(actions.readQueue).toHaveBeenLastCalledWith('tenant', 'other-device');
});

it('rechecks trainee eligibility on device changes and blocks unavailable trainees', async () => {
  vi.mocked(historyOptions).mockResolvedValue({ value: { ...options,
    devices: [...options.devices, { id: 'other-device', name: 'Other department laptop' }],
  } });
  vi.mocked(actions.queueLearners).mockImplementation(async (_context, device) => ({ value: device === 'device'
    ? [{ id: 'learner', name: 'Alex Student' }] : [{ id: 'other', name: 'Priya Rao' }],
  }));
  render(<StartSessionPage contextId="tenant" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Alex Student'));
  await user.click(screen.getByRole('button', { name: 'Add 1 to queue' }));
  await user.click(screen.getByRole('button', { name: 'Change device' }));
  await user.selectOptions(screen.getByLabelText('Assign to device'), 'other-device');
  await screen.findByLabelText('Priya Rao');
  await user.click(screen.getByRole('button', { name: 'Add 1 to queue' }));
  expect(await screen.findByText(/Some selected trainees are unavailable for this device/)).toBeInTheDocument();
  expect(actions.planSessions).not.toHaveBeenCalled();
  expect(screen.getByRole('region', { name: 'Session 1: Alex Student' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Remove trainee 1' }));
  await user.click(screen.getByLabelText('Priya Rao'));
  await user.click(screen.getByRole('button', { name: 'Add 1 to queue' }));
  await user.click(screen.getByRole('button', { name: 'Confirm & add to queue' }));
  expect(actions.planSessions).toHaveBeenCalledWith('tenant', 'other-device', {
    request_key: expect.any(String), items: [{ learner_id: 'other', scenario_id: 'case', language: 'en', duration_seconds: 300 }],
  });
});

it('returns from confirmation and cancels without adding sessions', async () => {
  render(<StartSessionPage contextId="tenant" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Alex Student'));
  await user.click(screen.getByRole('button', { name: 'Add 1 to queue' }));
  await user.click(screen.getByRole('button', { name: 'Back' }));
  expect(screen.getByRole('checkbox', { name: /Alex Student/ })).toBeChecked();
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(actions.planSessions).not.toHaveBeenCalled();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('keeps per-trainee settings when reordering a draft and submits the visible order', async () => {
  render(<StartSessionPage contextId="tenant" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Alex Student'));
  await user.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'hi');
  await user.click(screen.getByLabelText('Priya Rao'));
  expect(screen.getByLabelText('Trainee 1 · Language')).toHaveValue('en');
  expect(screen.getByLabelText('Trainee 2 · Language')).toHaveValue('hi');
  await user.click(screen.getByRole('button', { name: 'Move trainee 2 up' }));
  expect(screen.getByRole('region', { name: 'Session 1: Priya Rao' })).toBeInTheDocument();
  expect(screen.getByLabelText('Trainee 1 · Language')).toHaveValue('hi');
  expect(screen.getByLabelText('Trainee 2 · Language')).toHaveValue('en');
  expect(screen.getByRole('button', { name: 'Move trainee 1 up' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Move trainee 2 down' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Add 2 to queue' }));
  await user.click(screen.getByRole('button', { name: 'Confirm & add to queue' }));
  await waitFor(() => expect(actions.planSessions).toHaveBeenCalledTimes(1));
  expect(vi.mocked(actions.planSessions).mock.calls[0]![2].items.map(item => [item.learner_id, item.language]))
    .toEqual([['other', 'hi'], ['learner', 'en']]);
});

it('explains an empty search without losing selected trainees and supports removing them', async () => {
  render(<StartSessionPage contextId="tenant" />);
  const user = userEvent.setup();
  await user.click(await screen.findByLabelText('Alex Student'));
  await user.type(screen.getByLabelText('Find trainees'), 'nobody');
  expect(screen.getByText(/No trainees match/)).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Session 1: Alex Student' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Remove trainee 1' }));
  expect(screen.getByRole('button', { name: 'Add 0 to queue' })).toBeDisabled();
  await user.clear(screen.getByLabelText('Find trainees'));
  expect(screen.getByLabelText('Alex Student')).not.toBeChecked();
  await user.type(screen.getByLabelText('Find trainees'), '  PRIYA  ');
  expect(screen.getByLabelText('Priya Rao')).toBeInTheDocument();
  expect(screen.queryByLabelText('Alex Student')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(actions.planSessions).not.toHaveBeenCalled();
});
it('reorders only waiting sessions and preserves queue revision', async () => {
  vi.mocked(actions.readQueue).mockResolvedValue({ value: { ...empty, revision: 7,
    items: [{ ...row, id: 'active', status: 'active' }, row, { ...row, id: 'two', learner_name: 'Priya Rao' }] } });
  render(<SessionQueueWorkspace contextId="tenant" />);
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Move Priya Rao up' }));
  expect(actions.changeQueue).toHaveBeenCalledWith('tenant', 'device', { expected_revision: 7, order: ['two', 'one'], paused: false });
});
it('asks before ending an active session and displays stopping acknowledgement', async () => {
  vi.mocked(actions.readQueue).mockResolvedValue({ value: { ...empty, items: [{ ...row, status: 'active' }] } });
  vi.mocked(actions.endQueuedSession).mockResolvedValue({ value: { ...empty, items: [{ ...row, status: 'stopping' }] } });
  render(<SessionQueueWorkspace contextId="tenant" />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'End session' }));
  expect(actions.endQueuedSession).not.toHaveBeenCalled();
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'End session' }));
  expect(await screen.findByText('Stopping — awaiting device confirmation')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'End session' })).toBeDisabled();
});
it('preserves standalone practice when no assignment is waiting', async () => {
  vi.mocked(actions.readQueue).mockResolvedValue({ value: { ...empty, runtime_state: 'standalone' } });
  render(<SessionQueueWorkspace contextId="tenant" />);
  expect(await screen.findByRole('heading', { name: 'Standalone practice' })).toBeInTheDocument();
  expect(screen.getByText(/No trainee assigned/)).toBeInTheDocument();
});
it('gives trainees their history without exposing queue management', async () => {
  render(<SessionQueueWorkspace contextId="tenant" canManage={false} />);
  await waitFor(() => expect(actions.sessionHistory).toHaveBeenCalledWith('tenant'));
  expect(actions.readQueue).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: /Plan sessions/ })).not.toBeInTheDocument();
});


it('keeps the edit revision from opening the form when polling brings a newer queue', async () => {
  let poll: (() => void) | undefined;
  const timer = vi.spyOn(globalThis, 'setInterval').mockImplementation(((callback: () => void) => {
    poll = callback; return 1;
  }) as typeof setInterval);
  try {
    vi.mocked(actions.readQueue).mockResolvedValueOnce({ value: { ...empty, revision: 7, items: [row] } })
      .mockResolvedValue({ value: { ...empty, revision: 8, items: [{ ...row, duration_seconds: 60 }] } });
    vi.mocked(actions.editQueuedSession).mockResolvedValue({ error: 'Queue changed; reopen this assignment.' });
    render(<SessionQueueWorkspace contextId="tenant" />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    await screen.findByRole('button', { name: 'Save changes' });
    await act(async () => { poll!(); });
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(actions.editQueuedSession).toHaveBeenCalledWith('tenant', 'device', 'one', {
      learner_id: 'learner', scenario_id: 'case', language: 'en', duration_seconds: 300, expected_revision: 7,
    });
    expect(await screen.findByText('Queue changed; reopen this assignment.')).toBeInTheDocument();
  } finally { timer.mockRestore(); }
});

it('does not replace a newer polled queue with a delayed planning reply', async () => {
  let poll: (() => void) | undefined;
  const timer = vi.spyOn(globalThis, 'setInterval').mockImplementation(((callback: () => void) => {
    poll = callback; return 1;
  }) as typeof setInterval);
  let complete!: (value: { value: actions.SessionQueue }) => void;
  try {
    vi.mocked(actions.planSessions).mockReturnValue(new Promise(resolve => { complete = resolve; }));
    render(<StartSessionPage contextId="tenant" />);
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText('Alex Student'));
    await user.click(screen.getByRole('button', { name: 'Add 1 to queue' }));
    await user.click(screen.getByRole('button', { name: 'Confirm & add to queue' }));
    vi.mocked(actions.readQueue).mockResolvedValue({ value: { ...empty, revision: 3, items: [{ ...row, status: 'active' }] } });
    await act(async () => { poll!(); });
    await act(async () => { complete({ value: { ...empty, revision: 2, items: [row] } }); });
    expect(await screen.findByRole('button', { name: 'End session' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Waiting queue/ })).toHaveTextContent('0');
  } finally { timer.mockRestore(); }
});
