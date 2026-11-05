import { PermissionProvider, ToastProvider } from '@pms/ui';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DeviceDirectoryProvider } from '../src/components/DeviceDirectoryProvider';
import { DeviceList } from '../src/components/DeviceList';
import { listDevices } from '../src/lib/device-actions';
import { DEMO_DEVICES } from '../src/data/devices';
const navigation = vi.hoisted(() => ({ push: vi.fn() }));
const modelChoices = vi.hoisted(() => vi.fn());
const saveModels = vi.hoisted(() => vi.fn());
vi.mock('../src/lib/direct-model-actions', () => ({ deviceModels: modelChoices, saveDeviceModels: saveModels }));
vi.mock('next/navigation', () => ({ useRouter: () => navigation }));
vi.mock('../src/lib/device-actions', () => ({ listDevices: vi.fn(), saveDevice: vi.fn(), changeDeviceLifecycle: vi.fn(), transferDevice: vi.fn() }));
const row = { ...DEMO_DEVICES[0]!, connectivity: 'online' as const };
beforeEach(() => { vi.mocked(listDevices).mockReset(); navigation.push.mockReset(); modelChoices.mockReset().mockResolvedValue({ error: 'No model choices in this fixture' }); });
function show(platform = false) { render(<PermissionProvider permissions={platform ? ['platform.health.read', 'platform.organizations.manage'] : ['org.devices.summary.read', 'org.devices.manage']}><ToastProvider><DeviceDirectoryProvider contextId={platform ? 'platform' : row.organization_id} departments={{}} platform={platform}><DeviceList /></DeviceDirectoryProvider></ToastProvider></PermissionProvider>); }
it('uses API connectivity and search results', async () => {
  vi.mocked(listDevices).mockImplementation(async (_context, query) => ({ value: { items: query.q ? [] : [row], total: query.q ? 0 : 1, has_more: false, next_cursor: null } }));
  show();
  await screen.findByText(row.name);
  expect(screen.getByText('Online', { selector: '.pms-badge' })).toBeInTheDocument();
  await userEvent.setup().type(screen.getByRole('searchbox', { name: 'Search devices' }), 'Missing');
  expect(await screen.findByText('No matching devices')).toBeInTheDocument();
  expect(listDevices).toHaveBeenLastCalledWith(row.organization_id, expect.objectContaining({ q: 'Missing' }), undefined);
});
it('offers platform registration without exposing private configuration', async () => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [{ ...row, summary_only: true, organization_name: 'Tenant A' }], total: 1, has_more: false, next_cursor: null } });
  show(true);
  await screen.findByText('Tenant A');
  expect(screen.getByRole('button', { name: 'Create new device' })).toBeInTheDocument();
  expect(screen.queryByText(/Enrollment, provider credentials and results require/)).not.toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: `Actions for ${row.name}` }));
  await userEvent.setup().click(screen.getByRole('menuitem', { name: 'Configure model' }));
  expect(await screen.findByRole('dialog', { name: 'Configure model' })).toBeInTheDocument();
  expect(modelChoices).toHaveBeenCalledWith(row.id);
  expect(navigation.push).not.toHaveBeenCalled();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Cancel' }));
  await waitFor(() => expect(screen.getByRole('button', { name: `Actions for ${row.name}` })).toHaveFocus());
});
it('shows recoverable API errors instead of an empty fleet', async () => {
  vi.mocked(listDevices).mockResolvedValue({ error: 'Tenant inactive' });
  show();
  expect(await screen.findByText('Tenant inactive')).toBeInTheDocument();
  expect(screen.queryByText('No devices yet')).not.toBeInTheDocument();
});
it('disables model setup for inactive devices', async () => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [{ ...row, is_active: false }], total: 1, has_more: false, next_cursor: null } });
  show(true);
  await userEvent.setup().click(await screen.findByRole('button', { name: `Actions for ${row.name}` }));
  expect(screen.getByRole('menuitem', { name: /Configure model/ })).toHaveAttribute('aria-disabled', 'true');
});

it('puts required model setup immediately after View and restores focus after closing', async () => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [{ ...row, models_configured: false }], total: 1, has_more: false, next_cursor: null } });
  show(true);
  const configure = await screen.findByRole('button', { name: `Configure Model for ${row.name}` });
  expect(screen.getByRole('link', { name: `View ${row.name}` }).nextElementSibling).toBe(configure);
  expect(configure.parentElement).toHaveAttribute('data-model-required', 'true');
  expect(within(configure.closest('tr')!).getByText('Model required')).toBeInTheDocument();
  await userEvent.setup().click(configure);
  expect(await screen.findByRole('dialog', { name: 'Configure model' })).toBeInTheDocument();
  expect(modelChoices).toHaveBeenCalledWith(row.id);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Cancel' }));
  await waitFor(() => expect(configure).toHaveFocus());
});

it.each([true, undefined])('does not flag configured or unknown model status (%s)', async models_configured => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [{ ...row, models_configured }], total: 1, has_more: false, next_cursor: null } });
  show(true);
  const view = await screen.findByRole('link', { name: `View ${row.name}` });
  expect(screen.queryByRole('button', { name: `Configure Model for ${row.name}` })).not.toBeInTheDocument();
  expect(view.parentElement).not.toHaveAttribute('data-model-required');
  expect(screen.queryByText('Model required')).not.toBeInTheDocument();
});

it('removes the required action and row marker after saving a model', async () => {
  let configured = false;
  vi.mocked(listDevices).mockImplementation(async () => ({ value: { items: [{ ...row, models_configured: configured }], total: 1, has_more: false, next_cursor: null } }));
  modelChoices.mockResolvedValue({ value: {
    device: row,
    selection: { mode: 'local', version: 0, llm_model_id: null, asr_model_id: null, tts_model_id: null, video_model_id: null },
    models: [{ id: 'local-llm', name: 'Local conversation', kind: 'llm', location: 'local', revision: 1, available: true }],
  } });
  saveModels.mockImplementation(async () => { configured = true; return { value: {} }; });
  show(true);
  const visitor = userEvent.setup();
  await visitor.click(await screen.findByRole('button', { name: `Configure Model for ${row.name}` }));
  await visitor.selectOptions(await screen.findByLabelText('Conversation'), 'local-llm');
  await visitor.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Configure model' })).not.toBeInTheDocument());
  const view = await screen.findByRole('link', { name: `View ${row.name}` });
  expect(view.parentElement).not.toHaveAttribute('data-model-required');
  expect(screen.queryByRole('button', { name: `Configure Model for ${row.name}` })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole('button', { name: `Actions for ${row.name}` })).toHaveFocus());
});

it.each(['inactive', 'retired'])('keeps the visible model action disabled for %s devices', async state => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [{ ...row, models_configured: false, is_active: state !== 'inactive', enrollment_state: state === 'retired' ? 'retired' : 'pending' }], total: 1, has_more: false, next_cursor: null } });
  show(true);
  const configure = await screen.findByRole('button', { name: `Configure Model for ${row.name}` });
  expect(configure).toBeDisabled();
  await userEvent.setup().click(configure);
  expect(modelChoices).not.toHaveBeenCalled();
});

it('does not expose platform model setup in the tenant list', async () => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [{ ...row, models_configured: false }], total: 1, has_more: false, next_cursor: null } });
  show();
  const view = await screen.findByRole('link', { name: `View ${row.name}` });
  expect(screen.queryByRole('button', { name: `Configure Model for ${row.name}` })).not.toBeInTheDocument();
  expect(view.parentElement).not.toHaveAttribute('data-model-required');
});

it('does not offer model setup without platform management permission', async () => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [{ ...row, models_configured: false }], total: 1, has_more: false, next_cursor: null } });
  render(<PermissionProvider permissions={['platform.health.read']}><ToastProvider><DeviceDirectoryProvider contextId="platform" departments={{}} platform><DeviceList /></DeviceDirectoryProvider></ToastProvider></PermissionProvider>);
  await screen.findByText(row.name);
  expect(screen.queryByRole('button', { name: `Configure Model for ${row.name}` })).not.toBeInTheDocument();
});

it('filters departments without exposing obsolete profile controls', async () => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [row], total: 1, has_more: false, next_cursor: null } });
  render(<PermissionProvider permissions={['org.devices.summary.read', 'org.devices.manage']}><ToastProvider>
    <DeviceDirectoryProvider contextId={row.organization_id}
      departments={{ department: 'Department of clinical simulation and advanced training' }}
     >
      <DeviceList />
    </DeviceDirectoryProvider>
  </ToastProvider></PermissionProvider>);
  await screen.findByText(row.name);
  const visitor = userEvent.setup();
  await visitor.selectOptions(screen.getByLabelText('Department'), 'department');
  expect(screen.queryByLabelText('Profile')).not.toBeInTheDocument();
  await waitFor(() => expect(listDevices).toHaveBeenLastCalledWith(row.organization_id,
    expect.objectContaining({ department_id: 'department' }), undefined));
});
