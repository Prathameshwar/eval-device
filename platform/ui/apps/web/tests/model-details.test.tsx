import { PermissionProvider, ToastProvider } from '@pms/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ModelDirectoryProvider } from '../src/components/ModelDirectoryProvider';
import { ModelDetails } from '../src/components/ModelDetails';
import { listModels, retireModel, restoreModel } from '../src/lib/model-actions';
import { DEMO_MODELS } from '../src/data/models';
vi.mock('../src/lib/model-actions', () => ({ listModels: vi.fn(), saveModel: vi.fn(), retireModel: vi.fn(), restoreModel: vi.fn() }));
const model = DEMO_MODELS[0]!;
const providers = [{ id: 'openai', operations: ['text.generate'], adapterAvailable: true }];
beforeEach(() => {
  vi.mocked(listModels).mockResolvedValue({ value: { items: [], total: 0, has_more: false, next_cursor: null } });
  vi.mocked(retireModel).mockReset();
  vi.mocked(restoreModel).mockReset();
});
function show(record = model, manage = true) {
  render(
    <PermissionProvider permissions={manage ? ['platform.settings.read', 'platform.settings.manage'] : ['org.configuration.read']}>
      <ToastProvider>
        <ModelDirectoryProvider providers={providers}>
          <ModelDetails modelId={record.id} initialModel={record} />
        </ModelDirectoryProvider>
      </ToastProvider>
    </PermissionProvider>,
  );
}
it('renders a deep-linked model that is not in the current directory page', async () => {
  show();
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(model.display_name);
  expect(screen.getByText(model.model_key)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Back to models' })).toHaveAttribute('href', '/models?tab=catalog');
});
it('retires the model only after confirmation and server success', async () => {
  vi.mocked(retireModel).mockResolvedValue({ value: { ...model, lifecycle: 'retired' } });
  show();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Model actions' }));
  await user.click(screen.getByRole('menuitem', { name: 'Retire' }));
  expect(retireModel).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Retire model' }));
  expect(await screen.findByText('This model is retired. Its details remain available.')).toBeInTheDocument();
  expect(retireModel).toHaveBeenCalledWith(model.id);
  expect(screen.queryByRole('button', { name: 'Edit model' })).not.toBeInTheDocument();
});
it('restores a retired model only after confirmation and server success', async () => {
  const retired = { ...model, lifecycle: 'retired' as const };
  vi.mocked(restoreModel).mockResolvedValue({ value: { ...retired, lifecycle: 'deprecated' } });
  show(retired);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Model actions' }));
  await user.click(screen.getByRole('menuitem', { name: 'Restore' }));
  expect(restoreModel).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Restore model' }));
  expect(await screen.findByText('This model is restored as deprecated.')).toBeInTheDocument();
  expect(restoreModel).toHaveBeenCalledWith(model.id, model.version);
});
it('hides mutation controls for readers', async () => {
  show(model, false);
  expect(screen.queryByRole('button', { name: 'Edit model' })).not.toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Model actions' }));
  expect(screen.queryByRole('menuitem', { name: 'Retire' })).not.toBeInTheDocument();
  expect(screen.getByRole('menuitem', { name: 'Copy ID' })).toBeInTheDocument();
});
