import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { emptyDocument } from '../src/lib/patient-catalog';

const actions = vi.hoisted(() => ({
  list: vi.fn(), read: vi.fn(), create: vi.fn(), save: vi.fn(), submit: vi.fn(),
  archive: vi.fn(), validate: vi.fn(), approve: vi.fn(), retire: vi.fn(), refresh: vi.fn(),
  options: vi.fn(), listCatalog: vi.fn(), saveCatalog: vi.fn(),
}));
vi.mock('@/lib/scenario-actions', () => ({
  listScenarios: actions.list, readScenario: actions.read, createScenario: actions.create,
  saveScenario: actions.save, submitScenario: actions.submit, archiveScenario: actions.archive,
  validateScenario: actions.validate, approveScenario: actions.approve,
  retireScenario: actions.retire, refreshScenarioCase: actions.refresh,
}));
vi.mock('@/lib/catalog-actions', () => ({
  catalogOptions: actions.options, listCatalog: actions.listCatalog, saveCatalog: actions.saveCatalog,
}));

import { ScenarioLibrary } from '../src/components/ScenarioLibrary';

beforeEach(() => { Object.values(actions).forEach((mock) => mock.mockReset()); });

it('starts with published starters and opens a three-step editor for a new draft', async () => {
  actions.list.mockResolvedValue({ value: { items: [], total: 0, next_cursor: null, has_more: false } });
  actions.options.mockResolvedValue({ value: {
    categories: [{ id: 'specialty-a', code: 'cardiology', name: 'Cardiology', is_active: true }],
    languages: [{ code: 'en', name: 'English' }, { code: 'hi', name: 'Hindi' }],
  } });
  actions.listCatalog.mockResolvedValue({ value: { items: [], total: 0, next_cursor: null, has_more: false } });
  actions.create.mockImplementation(async (_context, code) => ({ value: {
    id: 'draft-a', code, title: 'Chest pain interview', revision: 1, schema_version: 4,
    specialty_id: 'specialty-a', is_archived: false, workflow_version: 2,
    document: { ...emptyDocument(), code, title: 'Chest pain interview', specialty: 'Cardiology' },
  } }));
  render(<ScenarioLibrary contextId="tenant-a" />);
  expect(await screen.findByLabelText('View')).toHaveValue('published');
  fireEvent.click(screen.getByRole('button', { name: 'New scenario' }));
  expect(screen.getByRole('heading', { name: 'Start with a name and specialty' })).toBeInTheDocument();
  await screen.findByRole('option', { name: 'Cardiology' });
  fireEvent.change(screen.getByLabelText('Scenario name'), { target: { value: 'Chest pain interview' } });
  fireEvent.change(screen.getByLabelText('Clinical specialty'), { target: { value: 'specialty-a' } });
  expect(screen.getByLabelText('Scenario name')).toHaveValue('Chest pain interview');
  expect(screen.getByLabelText('Clinical specialty')).toHaveValue('specialty-a');
  fireEvent.click(screen.getByRole('button', { name: 'Create draft' }));
  await waitFor(() => expect(actions.create).toHaveBeenCalledWith('tenant-a',
    'chest_pain_interview', expect.any(String), undefined, undefined,
    'specialty-a', 'Chest pain interview'));
  expect(await screen.findByText('Patient & specialty')).toBeInTheDocument();
  expect(screen.getByText('Clinical details')).toBeInTheDocument();
  expect(screen.getByText('Review & submit')).toBeInTheDocument();
  expect(screen.getByLabelText('Patient name')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Patient name'), { target: { value: 'Unsaved patient' } });
  fireEvent.click(screen.getByRole('button', { name: 'Back to scenarios' }));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByLabelText('Patient name')).toHaveValue('Unsaved patient');
  fireEvent.click(screen.getByRole('button', { name: 'Back to scenarios' }));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  expect(await screen.findByLabelText('View')).toHaveValue('published');
  expect(screen.getByRole('link', { name: 'Back to home' })).toHaveAttribute('href', '/home');
  expect(actions.save).not.toHaveBeenCalled();
});

it('copies an active historical case into the same guided editor', async () => {
  actions.list.mockResolvedValue({ value: { items: [], total: 0, next_cursor: null, has_more: false } });
  actions.options.mockResolvedValue({ value: { categories: [], languages: [{ code: 'en', name: 'English' }] } });
  actions.listCatalog.mockResolvedValue({ value: {
    items: [{ id: 'case-a', code: 'old_case', title: 'Old case' }], total: 1,
    next_cursor: null, has_more: false,
  } });
  actions.create.mockResolvedValue({ value: {
    id: 'draft-old', code: 'old_case', title: 'Old case', revision: 1, schema_version: 4,
    specialty_id: 'specialty-a', source_case_id: 'case-a', is_archived: false,
    document: { ...emptyDocument(), code: 'old_case', title: 'Old case' },
  } });
  render(<ScenarioLibrary contextId="tenant-a" />);
  fireEvent.click(await screen.findByRole('button', { name: 'New scenario' }));
  await screen.findByRole('option', { name: 'Old case' });
  fireEvent.change(screen.getByLabelText('Start from an existing case (optional)'),
    { target: { value: 'case-a' } });
  expect(screen.getByLabelText('Scenario code')).toHaveValue('old_case');
  fireEvent.click(screen.getByRole('button', { name: 'Create draft' }));
  await waitFor(() => expect(actions.create).toHaveBeenCalledWith('tenant-a',
    'old_case', expect.any(String), undefined, 'case-a', undefined, ''));
  expect(await screen.findByText('This copy keeps its source clinical specialty.')).toBeInTheDocument();
  expect(screen.getByLabelText('Clinical specialty')).toBeDisabled();
});

function arrangeRecord(overrides: Record<string, unknown> = {}) {
  const record = { id: 'scenario-a', title: 'Chest pain interview', code: 'chest_pain', schema_version: 4,
    revision: 2, submitted_revision: 2, specialty_id: 'specialty-a', is_active: true,
    document: { ...emptyDocument(), title: 'Chest pain interview', specialty: 'Cardiology' }, ...overrides };
  actions.list.mockResolvedValue({ value: { items: [record], total: 1, has_more: false } });
  actions.read.mockResolvedValue({ value: record });
  actions.options.mockResolvedValue({ value: {
    categories: [{ id: 'specialty-a', code: 'cardiology', name: 'Cardiology', is_active: true }],
    languages: [{ code: 'en', name: 'English' }, { code: 'hi', name: 'Hindi' }],
  } });
  actions.listCatalog.mockResolvedValue({ value: { items: [] } });
  return record;
}

it('opens a published scenario on its patient details even without draft revision fields', async () => {
  arrangeRecord({ revision: undefined, submitted_revision: undefined, version: 1 });
  render(<ScenarioLibrary contextId="tenant-a" />);
  fireEvent.click(await screen.findByRole('button', { name: /Open/ }));
  expect(await screen.findByLabelText('Patient name')).toBeDisabled();
  expect(screen.getByLabelText('Content language')).toBeInTheDocument();
  expect(screen.queryByText('Add a clinical specialty')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save draft' })).not.toBeInTheDocument();
});

it('moves a retired version out of Published and opens it read-only from Retired', async () => {
  const record = arrangeRecord({ revision: undefined, submitted_revision: undefined, version: 1 });
  let retired = false;
  actions.list.mockImplementation(async (_context, query) => ({ value: {
    items: query.view === (retired ? 'retired' : 'published') ? [{ ...record, is_active: !retired }] : [],
    total: 1, next_cursor: null, has_more: false,
  } }));
  actions.retire.mockImplementation(async () => {
    retired = true;
    actions.read.mockResolvedValue({ value: { ...record, is_active: false } });
    return { value: true };
  });
  render(<ScenarioLibrary contextId="tenant-a" />);
  expect(await screen.findByRole('option', { name: 'Retired versions' })).toHaveValue('retired');
  fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Retire version' }));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  expect(await screen.findByText('Scenario retired.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to scenarios' }));
  expect(await screen.findByText('No scenarios found')).toBeInTheDocument();
  expect(screen.getByLabelText('View')).toHaveValue('published');
  fireEvent.change(screen.getByLabelText('View'), { target: { value: 'retired' } });
  expect(await screen.findByText('Retired', { exact: true })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Version' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Open' }));
  await waitFor(() => expect(actions.read).toHaveBeenLastCalledWith('tenant-a', record.id, true));
  expect(await screen.findByLabelText('Patient name')).toBeDisabled();
  expect(screen.getByRole('heading', { name: 'Retired scenario' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Retire version' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Archive draft' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save draft' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Copy to new draft' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to scenarios' }));
  fireEvent.change(screen.getByLabelText('View'), { target: { value: 'published' } });
  expect(await screen.findByText('No scenarios found')).toBeInTheDocument();
});

it('lets a reviewer choose Hindi in the review step and checks readiness after recording review', async () => {
  const record = arrangeRecord();
  const reviewed = { ...record, revision: 3, submitted_revision: 3 };
  actions.approve.mockResolvedValue({ value: reviewed });
  actions.validate.mockResolvedValue({ value: { revision: 3, publishable: true, errors: [], warnings: [] } });
  render(<ScenarioLibrary contextId="tenant-a" canAuthor={false} canReview />);
  fireEvent.change(await screen.findByLabelText('View'), { target: { value: 'drafts' } });
  fireEvent.click(await screen.findByRole('button', { name: /Open/ }));
  fireEvent.change(await screen.findByLabelText('Review language'), { target: { value: 'hi' } });
  fireEvent.change(screen.getByLabelText('Educator name'), { target: { value: 'Reviewer Alex' } });
  fireEvent.change(screen.getByLabelText('Review statement'), { target: { value: 'Reviewed for this synthetic software test.' } });
  expect(screen.queryByRole('button', { name: 'Retire version' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Record Hindi review' }));
  await waitFor(() => expect(actions.approve).toHaveBeenCalledWith('tenant-a', record,
    expect.any(Object), 'hi', undefined));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Publish version' })).toBeEnabled());
  expect(actions.validate).toHaveBeenCalledWith('tenant-a', reviewed);
});

it('saves an inline-created specialty with its name as well as its identifier', async () => {
  arrangeRecord();
  actions.saveCatalog.mockResolvedValue({ value: {
    id: 'specialty-b', name: 'Emergency Medicine', code: 'emergency_medicine', is_active: true,
  } });
  actions.save.mockImplementation(async (_context, row) => ({ value: { ...row, revision: 3 } }));
  render(<ScenarioLibrary contextId="tenant-a" />);
  fireEvent.change(await screen.findByLabelText('View'), { target: { value: 'drafts' } });
  fireEvent.click(await screen.findByRole('button', { name: /Open/ }));
  fireEvent.click(await screen.findByRole('button', { name: 'Previous' }));
  fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
  fireEvent.click(screen.getByText('Add a clinical specialty'));
  fireEvent.change(screen.getByLabelText('Specialty name'), { target: { value: 'Emergency Medicine' } });
  fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Urgent assessment' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add specialty' }));
  await waitFor(() => expect(screen.getByLabelText('Clinical specialty')).toHaveValue('specialty-b'));
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(actions.save).toHaveBeenCalledWith('tenant-a', expect.objectContaining({
    specialty_id: 'specialty-b', document: expect.objectContaining({ specialty: 'Emergency Medicine' }),
  })));
});
