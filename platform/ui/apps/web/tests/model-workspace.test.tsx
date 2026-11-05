import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DeviceModelDialog } from '../src/components/DeviceModelDialog';
import type { DeviceChoices } from '../src/lib/direct-model-types';
import { DEMO_DEVICES } from '../src/data/devices';
const mocks = vi.hoisted(() => ({ choices: vi.fn(), save: vi.fn() }));
vi.mock('../src/lib/direct-model-actions', () => ({ deviceModels: mocks.choices, saveDeviceModels: mocks.save }));
const base: DeviceChoices = {
  device: { ...DEMO_DEVICES[0]!, id: 'device', name: 'Lab laptop', is_active: true, enrollment_state: 'enrolled' },
  selection: { mode: 'cloud', version: 3, llm_model_id: null, asr_model_id: null, tts_model_id: null, video_model_id: null },
  models: [{ id: 'cloud', name: 'Cloud LLM', kind: 'llm', location: 'cloud', revision: 2, available: true },
    { id: 'local', name: 'Local LLM', kind: 'llm', location: 'local', revision: 1, available: true },
    { id: 'speech', name: 'Whisper', kind: 'asr', location: 'local', revision: 1, available: true },
    { id: 'missing', name: 'Missing LLM', kind: 'llm', location: 'local', revision: 1, available: false }],
};
beforeEach(() => { mocks.choices.mockReset(); mocks.save.mockReset(); mocks.choices.mockResolvedValue({ value: structuredClone(base) }); mocks.save.mockResolvedValue({ value: { version: 4 } }); });
function show() { const onClose = vi.fn(), onSaved = vi.fn(); render(<DeviceModelDialog deviceId="device" onClose={onClose} onSaved={onSaved} />); return { onClose, onSaved }; }
it('shows only one mode control and four direct model dropdowns', async () => {
  show(); await screen.findByText('Lab laptop');
  expect(screen.getAllByRole('combobox')).toHaveLength(4);
  expect(screen.queryByText(/profile|connection|publish/i)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  expect(screen.queryByRole('option', { name: 'Local LLM' })).not.toBeInTheDocument();
});
it('saves the four selections atomically with device and model versions', async () => {
  const user = userEvent.setup(); const { onSaved } = show(); await screen.findByText('Lab laptop');
  await user.click(screen.getByRole('button', { name: 'Local' }));
  expect(screen.queryByRole('option', { name: 'Missing LLM' })).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Conversation'), 'local');
  await user.selectOptions(screen.getByLabelText('Speech recognition'), 'speech');
  await user.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledWith('device', {
    mode: 'local', expected_version: 3, llm_model_id: 'local', asr_model_id: 'speech', tts_model_id: null, video_model_id: null,
    model_revisions: { local: 1, speech: 1 },
  }));
  expect(onSaved).toHaveBeenCalledWith('Lab laptop');
});
it('clears incompatible draft selections when switching mode', async () => {
  const user = userEvent.setup(); show(); await screen.findByText('Lab laptop');
  await user.selectOptions(screen.getByLabelText('Conversation'), 'cloud');
  await user.click(screen.getByRole('button', { name: 'Local' }));
  expect(screen.getByLabelText('Conversation')).toHaveValue('');
});
it('preserves unsaved changes when discard is cancelled', async () => {
  const user = userEvent.setup(); const { onClose } = show(); await screen.findByText('Lab laptop');
  await user.selectOptions(screen.getByLabelText('Conversation'), 'cloud');
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  const confirm = screen.getByRole('dialog', { name: 'Discard model changes?' });
  await user.click(within(confirm).getByRole('button', { name: 'Cancel' }));
  expect(onClose).not.toHaveBeenCalled(); expect(screen.getByLabelText('Conversation')).toHaveValue('cloud');
});
it('keeps the dialog open after a stale-save error', async () => {
  mocks.save.mockResolvedValue({ error: 'Models changed. Reload.' });
  const user = userEvent.setup(); const { onSaved } = show(); await screen.findByText('Lab laptop');
  await user.selectOptions(screen.getByLabelText('Conversation'), 'cloud');
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Models changed. Reload.')).toBeInTheDocument();
  expect(onSaved).not.toHaveBeenCalled(); expect(screen.getByLabelText('Conversation')).toHaveValue('cloud');
});
it('preserves mixed assignments until an explicit mode is chosen', async () => {
  mocks.choices.mockResolvedValue({ value: { ...base, selection: { ...base.selection, mode: 'mixed', llm_model_id: 'cloud', asr_model_id: 'speech' } } });
  show(); await screen.findByText('Lab laptop');
  expect(screen.getByLabelText('Conversation')).toHaveValue('cloud');
  expect(screen.getByLabelText('Speech recognition')).toHaveValue('speech');
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
});
it('blocks unavailable selected models and permits clearing them', async () => {
  mocks.choices.mockResolvedValue({ value: { ...base, selection: { ...base.selection, mode: 'local', llm_model_id: 'missing' } } });
  const user = userEvent.setup(); show(); await screen.findByText('Lab laptop');
  expect(screen.getByLabelText('Conversation')).toHaveValue('missing');
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  await user.selectOptions(screen.getByLabelText('Conversation'), '');
  expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
});
it('does not show editable controls for inactive devices', async () => {
  mocks.choices.mockResolvedValue({ value: { ...base, device: { ...base.device, is_active: false } } });
  show(); await screen.findByText('Lab laptop'); expect(screen.queryAllByRole('combobox')).toHaveLength(0);
});
it('requires a reload after an uncertain save before changing the device again', async () => {
  mocks.save.mockResolvedValue({ error: 'Check the saved selection.', uncertain: true });
  const user = userEvent.setup(); show(); await screen.findByText('Lab laptop');
  await user.selectOptions(screen.getByLabelText('Conversation'), 'cloud');
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Check the saved selection.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Reload' }));
  await waitFor(() => expect(mocks.choices).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText('Conversation')).toHaveValue('');
  expect(mocks.save).toHaveBeenCalledTimes(1);
});

it.each(['local', 'cloud'] as const)('offers configured %s models on a pending manikin and saves the selected types', async mode => {
  const models: DeviceChoices['models'] = mode === 'local' ? [
    { id: 'qwen', name: 'qwen3.5-4b-local', kind: 'llm', location: 'local', revision: 1, available: true },
    { id: 'whisper', name: 'Whisper large-v3', kind: 'asr', location: 'local', revision: 1, available: true },
    { id: 'espeak', name: 'eSpeak NG', kind: 'tts', location: 'local', revision: 1, available: true },
  ] : (['llm', 'asr', 'tts', 'video'] as const).map(kind => ({
    id: `cloud-${kind}`, name: `Configured cloud ${kind}`, kind, location: 'cloud', revision: 2, available: true,
  }));
  mocks.choices.mockResolvedValue({ value: {
    ...base, device: { ...base.device, name: 'Manikin demo 2', device_type: 'manikin', enrollment_state: 'pending' },
    models: [...models, { id: 'wrong-mode', name: 'Other mode', kind: 'llm', location: mode === 'local' ? 'cloud' : 'local', revision: 1, available: true }],
  } });
  const user = userEvent.setup(); const { onSaved } = show();
  await screen.findByText('Manikin demo 2');
  await user.click(screen.getByRole('button', { name: mode === 'local' ? 'Local' : 'Cloud' }));
  expect(screen.queryByRole('option', { name: 'Other mode' })).not.toBeInTheDocument();
  const labels = { llm: 'Conversation', asr: 'Speech recognition', tts: 'Speech output', video: 'Video' };
  for (const row of models) {
    const select = screen.getByLabelText(labels[row.kind]);
    expect(within(select).getByRole('option', { name: row.name })).toBeEnabled();
    await user.selectOptions(select, row.id);
  }
  if (mode === 'local') {
    expect(within(screen.getByLabelText('Video')).getAllByRole('option')).toHaveLength(1);
    expect(screen.getByText('No active local models configured. Add one in Models.')).toBeInTheDocument();
    expect(screen.getByText(/Install and run it on the device or its connected laptop/)).toBeInTheDocument();
  }
  await user.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('Manikin demo 2'));
  expect(mocks.save).toHaveBeenCalledWith('device', {
    mode, expected_version: 3, llm_model_id: null, asr_model_id: null, tts_model_id: null, video_model_id: null,
    ...Object.fromEntries(models.map(row => [`${row.kind}_model_id`, row.id])),
    model_revisions: Object.fromEntries(models.map(row => [row.id, row.revision])),
  });
});

it('removes stale selections after a failed reload', async () => {
  mocks.save.mockResolvedValue({ error: 'Models changed. Reload.' });
  const user = userEvent.setup(); show(); await screen.findByText('Lab laptop');
  await user.selectOptions(screen.getByLabelText('Conversation'), 'cloud');
  await user.click(screen.getByRole('button', { name: 'Save' }));
  await screen.findByText('Models changed. Reload.');
  mocks.choices.mockResolvedValueOnce({ error: 'Device unavailable.' });
  await user.click(screen.getByRole('button', { name: 'Reload' }));
  expect(await screen.findByText('Device unavailable.')).toBeInTheDocument();
  expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  expect(mocks.save).toHaveBeenCalledTimes(1);
});
it('shows the server lifecycle reason and prevents editing a blocked tenant device', async () => {
  mocks.choices.mockResolvedValue({ value: { ...base, configuration_allowed: false, configuration_blocked_reason: 'Activate the device department first.' } });
  show(); expect(await screen.findByText('Activate the device department first.')).toBeInTheDocument();
  expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
});
it('never submits a previous device selection after the next device fails to load', async () => {
  const user = userEvent.setup();
  const view = render(<DeviceModelDialog deviceId="device" onClose={vi.fn()} onSaved={vi.fn()} />);
  await screen.findByText('Lab laptop'); await user.selectOptions(screen.getByLabelText('Conversation'), 'cloud');
  mocks.choices.mockResolvedValueOnce({ error: 'Next device unavailable.' });
  view.rerender(<DeviceModelDialog deviceId="next-device" onClose={vi.fn()} onSaved={vi.fn()} />);
  await screen.findByText('Next device unavailable.');
  expect(screen.queryByText('Lab laptop')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  expect(mocks.save).not.toHaveBeenCalled();
});
