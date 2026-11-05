import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PermissionProvider, ToastProvider } from '@pms/ui';
import { CatalogDirectory } from '../src/components/CatalogDirectory';
import { ManagedDepartments } from '../src/components/ManagedDepartments';
import { HistoryWorkspace } from '../src/components/HistoryWorkspace';
import { ScenarioLibrary } from '../src/components/ScenarioLibrary';
import { ModelList } from '../src/components/ModelList';
import { ModelDirectoryProvider } from '../src/components/ModelDirectoryProvider';

const actions = vi.hoisted(() => ({
  catalog: vi.fn(), departments: vi.fn(), configuration: vi.fn(), options: vi.fn(),
  history: vi.fn(), stats: vi.fn(),
  scenarios: vi.fn(), catalogOptions: vi.fn(), models: vi.fn(), modelOptions: vi.fn(), deviceProfiles: vi.fn(),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('../src/lib/catalog-actions', () => ({ listCatalog: actions.catalog, catalogOptions: actions.catalogOptions }));
vi.mock('../src/lib/department-actions', () => ({ listDepartments: actions.departments }));
vi.mock('../src/lib/history-actions', () => ({ listHistory: actions.history, historyStats: actions.stats }));
vi.mock('../src/lib/scenario-actions', () => ({ listScenarios: actions.scenarios }));
vi.mock('../src/lib/model-actions', () => ({ listModels: actions.models }));
vi.mock('../src/lib/device-actions', () => ({ platformDeviceModelOptions: actions.deviceProfiles }));

const empty = { items: [], total: 0, has_more: false, next_cursor: null };
beforeEach(() => {
  vi.resetAllMocks();
  for (const action of [actions.catalog, actions.departments, actions.configuration, actions.history, actions.scenarios, actions.models]) {
    action.mockResolvedValue({ value: empty });
  }
  actions.options.mockResolvedValue({ value: { connections: [], models: [], providers: [], operations: [], connection_fields: {} } });
  actions.stats.mockResolvedValue({ value: { sessions: 0, hours_practiced: 0, average_score: null, awaiting_review: 0 } });
  actions.catalogOptions.mockResolvedValue({ value: { languages: [], categories: [] } });
  actions.modelOptions.mockResolvedValue({ value: { cloud: [], catalog: [], devices: [] } });
  actions.deviceProfiles.mockResolvedValue({ value: [] });
});

it.each(['categories', 'patients', 'cases'] as const)('keeps %s search and status filtering server-backed', async kind => {
  const visitor = userEvent.setup();
  render(<CatalogDirectory kind={kind} canManage={false} />);
  await waitFor(() => expect(actions.catalog).toHaveBeenCalled());
  await visitor.type(screen.getByRole('searchbox'), 'cardio{Enter}');
  await visitor.selectOptions(screen.getByLabelText('Status'), 'active');
  await waitFor(() => expect(actions.catalog).toHaveBeenLastCalledWith(
    kind, expect.objectContaining({ q: 'cardio', state: 'active' }), undefined,
  ));
  await visitor.click(screen.getByRole('button', { name: 'Clear search' }));
  await waitFor(() => expect(actions.catalog).toHaveBeenLastCalledWith(
    kind, expect.objectContaining({ q: '', state: 'active' }), undefined,
  ));
});

it('preserves department lifecycle filtering after searching', async () => {
  const visitor = userEvent.setup();
  render(<ManagedDepartments contextId="tenant-a" />);
  await waitFor(() => expect(actions.departments).toHaveBeenCalled());
  await visitor.type(screen.getByRole('searchbox'), 'cardio{Enter}');
  await visitor.selectOptions(screen.getByLabelText('Lifecycle'), 'true');
  await waitFor(() => expect(actions.departments).toHaveBeenLastCalledWith(
    'tenant-a', expect.objectContaining({ q: 'cardio', archived: 'true' }), undefined,
  ));
});

it.each(['sessions', 'reports'] as const)('retains the %s scope selector', async mode => {
  render(<HistoryWorkspace contextId="tenant-a" mode={mode} canManage={false} canMedia={false} />);
  await waitFor(() => expect(actions.history).toHaveBeenCalled());
  await userEvent.setup().selectOptions(screen.getByLabelText('Session scope'), 'mine');
  await waitFor(() => expect(actions.history).toHaveBeenLastCalledWith(
    'tenant-a', expect.objectContaining({ mine: true, kind: 'sessions' }), undefined,
  ));
});

it('does not render an empty filter strip on recordings', async () => {
  const { container } = render(<HistoryWorkspace contextId="tenant-a" mode="recordings" canManage={false} canMedia={false} />);
  await waitFor(() => expect(actions.history).toHaveBeenCalled());
  expect(container.querySelector('.pms-filter-bar')).toBeNull();
  expect(actions.history).toHaveBeenCalledWith(
    'tenant-a', expect.objectContaining({ kind: 'runs' }), undefined,
  );
});

it('keeps scenario search and publication view in the same query', async () => {
  const visitor = userEvent.setup();
  render(<ScenarioLibrary contextId="tenant-a" canAuthor={false} canReview={false} />);
  await waitFor(() => expect(actions.scenarios).toHaveBeenCalled());
  await visitor.type(screen.getByRole('searchbox'), 'cardio{Enter}');
  await visitor.selectOptions(screen.getByLabelText('View'), 'published');
  await waitFor(() => expect(actions.scenarios).toHaveBeenLastCalledWith(
    'tenant-a', expect.objectContaining({ q: 'cardio', view: 'published' }), undefined,
  ));
});

it('retains the catalog search', async () => {
  const visitor = userEvent.setup();
  render(<PermissionProvider permissions={['platform.settings.read', 'platform.settings.manage']}>
    <ToastProvider><ModelDirectoryProvider><ModelList /></ModelDirectoryProvider></ToastProvider>
  </PermissionProvider>);
  await waitFor(() => expect(actions.models).toHaveBeenCalled());
  await visitor.type(screen.getByRole('searchbox'), 'speech{Enter}');
  await waitFor(() => expect(actions.models).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'speech' }), undefined));
});
