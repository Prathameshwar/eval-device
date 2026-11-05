import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ScenarioLibrary } from '../src/components/ScenarioLibrary';

const actions = vi.hoisted(() => ({
  readScenario: vi.fn(), listScenarios: vi.fn(), createScenario: vi.fn(),
  saveScenario: vi.fn(), archiveScenario: vi.fn(), validateScenario: vi.fn(),
  approveScenario: vi.fn(), retireScenario: vi.fn(), refreshScenarioCase: vi.fn(),
}));
vi.mock('@/lib/scenario-actions', () => actions);
const catalog = vi.hoisted(() => ({ catalogOptions: vi.fn() }));
vi.mock('@/lib/catalog-actions', () => catalog);
const starter = {
  id: 'starter-a', code: 'alex_chest_discomfort', title: 'Chest discomfort interview',
  version: 1, schema_version: 1, is_active: true, execution_supported: true,
  publication_source: 'system_starter' as const, approved_at: '2026-10-02T00:00:00Z', approved_by: null,
  document: { version: 1, code: 'alex_chest_discomfort', title: 'Chest discomfort interview' },
};
vi.mock('@/lib/use-api-directory', () => ({
  useApiDirectory: () => ({
    query: { q: '', limit: 25, view: 'published' },
    page: { items: [starter], next_cursor: null },
    loading: false, error: undefined, reload: vi.fn(), setQuery: vi.fn(),
  }),
}));

beforeEach(() => {
  vi.resetAllMocks();
  catalog.catalogOptions.mockResolvedValue({ value: { languages: [] } });
  actions.readScenario.mockResolvedValue({ value: starter });
});

it('labels a published system starter in the list and detail without naming a human approver', async () => {
  const user = userEvent.setup();
  render(<ScenarioLibrary contextId="tenant-a" canAuthor={false} canReview={false} />);
  expect(await screen.findByText(/System-provisioned starter/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Open' }));
  expect(await screen.findByText(/created during tenant setup without a tenant clinician's approval/)).toBeInTheDocument();
  expect(screen.queryByText(/Approved .* by null/)).not.toBeInTheDocument();
});
