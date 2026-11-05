import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PermissionProvider } from '@pms/ui';
import { beforeEach, expect, it, vi } from 'vitest';
import { RuntimeModelsDirectory } from '../src/components/RuntimeModelsDirectory';
import { RuntimeModelEditor } from '../src/components/RuntimeModelEditor';
const mocks = vi.hoisted(() => ({ list: vi.fn(), save: vi.fn(), remove: vi.fn(), test: vi.fn() }));
vi.mock('../src/lib/direct-model-actions', () => ({ listModels: mocks.list, saveModel: mocks.save, deleteModel: mocks.remove, testModel: mocks.test }));
vi.mock('../src/components/SettingsBreadcrumbs', () => ({ SettingsBreadcrumbs: () => null }));
beforeEach(() => { Object.values(mocks).forEach(mock => mock.mockReset()); mocks.list.mockResolvedValue({ value: [] }); mocks.save.mockResolvedValue({ value: { id: 'saved' } }); });
it('has only relevant add buttons and model filters', async () => {
  render(<PermissionProvider permissions={['platform.settings.manage']}><RuntimeModelsDirectory /></PermissionProvider>);
  await screen.findByText('Add your first model');
  for (const name of ['Add LLM', 'Add audio', 'Add video']) expect(screen.getByRole('button', { name })).toBeInTheDocument();
  expect(screen.queryByText(/profiles|connections|assignments/i)).not.toBeInTheDocument();
  expect(screen.getAllByRole('combobox')).toHaveLength(3);
});
it('keeps add controls hidden for a read-only session', async () => {
  render(<RuntimeModelsDirectory />); await screen.findByText('Add your first model');
  expect(screen.queryByRole('button', { name: 'Add LLM' })).not.toBeInTheDocument();
});
it('local models need only a name and supported model selection', async () => {
  const user = userEvent.setup(); const onSaved = vi.fn();
  render(<RuntimeModelEditor kind="llm" onClose={vi.fn()} onSaved={onSaved} />);
  await user.click(screen.getByRole('button', { name: 'Local' }));
  expect(screen.queryByLabelText('API endpoint')).not.toBeInTheDocument(); expect(screen.queryByLabelText('API key')).not.toBeInTheDocument();
  await user.type(screen.getByLabelText('Name'), 'My local model');
  await user.click(screen.getByRole('button', { name: 'Save model' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ kind: 'llm', location: 'local', settings: {}, model_key: 'qwen3-4b-local' }), undefined);
});
it('switching audio type removes unrelated inputs and credentials', async () => {
  const user = userEvent.setup(); render(<RuntimeModelEditor kind="asr" onClose={vi.fn()} onSaved={vi.fn()} />);
  await user.type(screen.getByLabelText('API key'), 'discard-me');
  await user.selectOptions(screen.getByLabelText('Audio type'), 'tts');
  expect(screen.queryByLabelText('Deployment name')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('API key')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Access key ID')).toHaveValue('');
});
it('video forms omit conversation and speech inputs', () => {
  render(<RuntimeModelEditor kind="video" onClose={vi.fn()} onSaved={vi.fn()} />);
  expect(screen.queryByLabelText('Model ID')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Language')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Voice')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Private staging bucket')).toBeInTheDocument();
});
it('does not repeat a model creation after an uncertain network result', async () => {
  mocks.save.mockResolvedValue({ error: 'Reload to check the save.', uncertain: true });
  const user = userEvent.setup();
  render(<RuntimeModelEditor kind="llm" onClose={vi.fn()} onSaved={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: 'Local' }));
  await user.type(screen.getByLabelText('Name'), 'Local test');
  await user.click(screen.getByRole('button', { name: 'Save model' }));
  expect(await screen.findByText('Reload to check the save.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save model' })).toBeDisabled();
  expect(mocks.save).toHaveBeenCalledTimes(1);
});

const cloud = { id: 'cloud-model', name: 'Whisper cloud', organization_id: null, kind: 'asr' as const, location: 'cloud' as const,
  provider: 'azure', engine: 'azure_openai_whisper', model_key: 'my-deployment', settings: { endpoint: 'https://fixture.openai.azure.com/openai/v1', auth_mode: 'api_key', model: 'whisper', api_version: '2024-06-01' }, defaults: {}, is_active: true, has_credentials: true, revision: 4 };
it('preserves Whisper API version and deployment when editing without replacing the key', async () => {
  const user = userEvent.setup(); render(<RuntimeModelEditor kind="asr" model={cloud} onClose={vi.fn()} onSaved={vi.fn()} />);
  expect(screen.getByLabelText('API version')).toHaveValue('2024-06-01');
  await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), 'Renamed');
  await user.click(screen.getByRole('button', { name: 'Save model' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ model_key: 'my-deployment', expected_revision: 4, settings: expect.objectContaining({ model: 'whisper', api_version: '2024-06-01' }) }), 'cloud-model'));
  expect(mocks.save.mock.calls[0]![0]).not.toHaveProperty('credentials');
});
it('realtime Whisper clears the incompatible file API version', async () => {
  const user = userEvent.setup(); render(<RuntimeModelEditor kind="asr" model={cloud} onClose={vi.fn()} onSaved={vi.fn()} />);
  await user.selectOptions(screen.getByLabelText('Speech model'), 'gpt-realtime-whisper');
  expect(screen.queryByLabelText('API version')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Save model' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalled());
  expect(mocks.save.mock.calls[0]![0].settings).toEqual({ endpoint: cloud.settings.endpoint, auth_mode: 'api_key', model: 'gpt-realtime-whisper' });
});
it('supports optional AWS session credentials and storage prefix', async () => {
  const user = userEvent.setup(); render(<RuntimeModelEditor kind="video" onClose={vi.fn()} onSaved={vi.fn()} />);
  for (const [label, value] of Object.entries({ Name: 'Video', Region: 'ap-south-1', 'Private staging bucket': 'fixture-private', 'Staging folder prefix': 'custom', 'Access key ID': 'fixture-id', 'Secret access key': 'fixture-key', 'Session token': 'fixture-token' })) await user.type(screen.getByLabelText(label), value);
  await user.click(screen.getByRole('button', { name: 'Save model' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ settings: expect.objectContaining({ staging_prefix: 'custom' }), credentials: { access_key_id: 'fixture-id', secret_access_key: 'fixture-key', session_token: 'fixture-token' } }), undefined));
});
it('tests saved cloud revisions and explains that access checks do not verify inference', async () => {
  mocks.list.mockResolvedValue({ value: [cloud, { ...cloud, id: 'local', name: 'Local', location: 'local' }] });
  mocks.test.mockResolvedValue({ value: { status: 'passed', revision: 4, inference_verified: false } });
  render(<PermissionProvider permissions={['platform.settings.manage']}><RuntimeModelsDirectory /></PermissionProvider>);
  const button = await screen.findByRole('button', { name: 'Test connection for Whisper cloud' });
  expect(screen.queryByRole('button', { name: 'Test connection for Local' })).not.toBeInTheDocument();
  await userEvent.setup().click(button);
  expect(await screen.findByText(/device inference has not been tested/)).toBeInTheDocument();
  expect(mocks.test).toHaveBeenCalledWith('cloud-model', 4);
});
it('shows provider test failures without claiming success', async () => {
  mocks.list.mockResolvedValue({ value: [cloud] }); mocks.test.mockResolvedValue({ error: 'Cloud calls are disabled.' });
  render(<PermissionProvider permissions={['platform.settings.manage']}><RuntimeModelsDirectory /></PermissionProvider>);
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Test connection for Whisper cloud' }));
  expect(await screen.findByText('Whisper cloud: Cloud calls are disabled.')).toBeInTheDocument();
  expect(screen.queryByText(/connection check passed/)).not.toBeInTheDocument();
});

it('saves conversation protocol options for compatible providers', async () => {
  const user = userEvent.setup(); render(<RuntimeModelEditor kind="llm" onClose={vi.fn()} onSaved={vi.fn()} />);
  await user.selectOptions(screen.getByLabelText('Provider'), 'openai_compatible');
  for (const [label, value] of Object.entries({ Name: 'Compatible', 'Model ID': 'fixture-model', 'API endpoint': 'https://fixture.example/v1', 'API key': 'fixture-key' })) await user.type(screen.getByLabelText(label), value);
  await user.click(screen.getByText('Conversation compatibility'));
  await user.selectOptions(screen.getByLabelText('Output token parameter'), 'max_completion_tokens');
  await user.selectOptions(screen.getByLabelText('Streaming usage'), 'off');
  await user.selectOptions(screen.getByLabelText('Instruction role'), 'developer');
  await user.click(screen.getByRole('button', { name: 'Save model' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ settings: expect.objectContaining({ token_parameter: 'max_completion_tokens', stream_usage: false, instruction_role: 'developer' }) }), undefined));
});
