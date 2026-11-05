import { PermissionProvider, ToastProvider } from '@pms/ui';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ModelDirectoryProvider } from '../src/components/ModelDirectoryProvider';
import { ModelList } from '../src/components/ModelList';
import { listModels, retireModel } from '../src/lib/model-actions';
import { DEMO_MODELS } from '../src/data/models';
vi.mock('../src/lib/model-actions', () => ({ listModels: vi.fn(), saveModel: vi.fn(), retireModel: vi.fn(), restoreModel: vi.fn() }));
const row = DEMO_MODELS[0]!;
beforeEach(() => { vi.mocked(listModels).mockReset(); vi.mocked(retireModel).mockReset(); });
function show(admin = true) {
  render(
    <PermissionProvider permissions={admin ? ['platform.settings.read', 'platform.settings.manage'] : ['org.configuration.read']}>
      <ToastProvider>
        <ModelDirectoryProvider providers={[{ id: 'openai', operations: ['text.generate'], adapterAvailable: true }]}>
          <ModelList />
        </ModelDirectoryProvider>
      </ToastProvider>
    </PermissionProvider>,
  );
}
it('lists models from the server and supports search', async () => {
  vi.mocked(listModels).mockImplementation(async (query) => ({ value: { items: query.q ? [] : [row], total: query.q ? 0 : 1, has_more: false, next_cursor: null } }));
  show();
  await screen.findByText(row.display_name);
  await userEvent.setup().type(screen.getByRole('searchbox', { name: 'Search models' }), 'Missing');
  expect(await screen.findByText('No matching models')).toBeInTheDocument();
  expect(listModels).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'Missing' }), undefined);
});
it('hides management actions and the Retired filter for a tenant-scoped reader', async () => {
  vi.mocked(listModels).mockResolvedValue({ value: { items: [row], total: 1, has_more: false, next_cursor: null } });
  show(false);
  await screen.findByText(row.display_name);
  expect(screen.queryByRole('button', { name: 'Register model' })).not.toBeInTheDocument();
  expect(screen.getByText(/read only in your tenant/)).toBeInTheDocument();
  const lifecycleSelect = screen.getByRole('combobox', { name: 'Lifecycle' });
  expect(within(lifecycleSelect).queryByRole('option', { name: 'Retired models' })).not.toBeInTheDocument();
  expect(within(lifecycleSelect).queryByRole('option', { name: 'All models' })).not.toBeInTheDocument();
});
it('offers the Retired and All filters to a platform administrator', async () => {
  vi.mocked(listModels).mockResolvedValue({ value: { items: [row], total: 1, has_more: false, next_cursor: null } });
  show(true);
  await screen.findByText(row.display_name);
  const lifecycleSelect = screen.getByRole('combobox', { name: 'Lifecycle' });
  expect(within(lifecycleSelect).getByRole('option', { name: 'Retired models' })).toBeInTheDocument();
  expect(within(lifecycleSelect).getByRole('option', { name: 'All models' })).toBeInTheDocument();
});
it('retires a model only after confirmation and server success', async () => {
  vi.mocked(listModels).mockResolvedValue({ value: { items: [row], total: 1, has_more: false, next_cursor: null } });
  vi.mocked(retireModel).mockResolvedValue({ value: { ...row, lifecycle: 'retired' } });
  show();
  const user = userEvent.setup();
  await screen.findByText(row.display_name);
  await user.click(screen.getByRole('button', { name: `Actions for ${row.display_name}` }));
  await user.click(screen.getByRole('menuitem', { name: 'Retire' }));
  expect(retireModel).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Retire model' }));
  expect(await screen.findByText('Model retired')).toBeInTheDocument();
  expect(retireModel).toHaveBeenCalledWith(row.id);
});
it('shows recoverable API errors instead of an empty catalog', async () => {
  vi.mocked(listModels).mockResolvedValue({ error: 'Settings unavailable' });
  show();
  expect(await screen.findByText('Settings unavailable')).toBeInTheDocument();
  expect(screen.queryByText('No models registered yet')).not.toBeInTheDocument();
});
