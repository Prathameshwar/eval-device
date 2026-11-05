import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { CatalogEditor } from '../src/components/CatalogEditor';
import { CaseFields } from '../src/components/CaseFields';
import {
  catalogPayload,
  emptyDocument,
  newCatalogRecord,
  validateCatalog,
  nextEntryId,
} from '../src/lib/patient-catalog';
import * as actions from '../src/lib/catalog-actions';
vi.mock('../src/lib/catalog-actions', () => ({
  catalogOptions: vi.fn(),
  readCatalog: vi.fn(),
  saveCatalog: vi.fn(),
}));
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push }),
}));
const options = {
  categories: [],
  patients: [],
  languages: [{ code: 'en', name: 'English' }],
  conversation_languages: [{ code: 'en', name: 'English' }],
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(actions.catalogOptions).mockResolvedValue({ value: options });
});
it('keeps unsaved catalog edits until leaving is explicitly confirmed', async () => {
  const visitor = userEvent.setup();
  render(<CatalogEditor kind="categories" id="new" canManage />);
  await visitor.type(await screen.findByLabelText('English name'), 'Unsaved specialty');
  await visitor.click(screen.getByRole('button', { name: 'Back to clinical specialties' }));
  expect(push).not.toHaveBeenCalled();
  await visitor.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByLabelText('English name')).toHaveValue('Unsaved specialty');
  await visitor.click(screen.getByRole('button', { name: 'Back to clinical specialties' }));
  await visitor.click(screen.getByRole('button', { name: 'Discard changes' }));
  expect(push).toHaveBeenCalledWith('/catalog/categories');
  expect(actions.saveCatalog).not.toHaveBeenCalled();
});
it('keeps a rejected edit and entered values in the editor', async () => {
  const visitor = userEvent.setup();
  const row = {
    ...newCatalogRecord('categories'),
    id: 'category',
    version: 4,
    code: 'category',
    name: 'Old category',
    names: { en: 'Old category' },
    description: 'Description',
  };
  vi.mocked(actions.readCatalog).mockResolvedValue({ value: row });
  vi.mocked(actions.saveCatalog).mockResolvedValue({
    error: 'This record changed. Reload before saving.',
  });
  render(<CatalogEditor kind="categories" id="category" canManage />);
  const name = await screen.findByLabelText('English name');
  await visitor.clear(name);
  await visitor.type(name, 'New category');
  await visitor.click(screen.getByRole('button', { name: 'Save clinical specialty' }));
  expect(await screen.findByText('This record changed. Reload before saving.')).toBeInTheDocument();
  expect(name).toHaveValue('New category');
  expect(actions.saveCatalog).toHaveBeenCalledWith(
    'categories',
    expect.objectContaining({ version: 4, name: 'New category' }),
  );
});
it('allows readers to inspect clinical tabs without write controls or removed sections', async () => {
  const visitor = userEvent.setup();
  const document = emptyDocument();
  document.vitals = { heart_rate_bpm: 84 };
  vi.mocked(actions.readCatalog).mockResolvedValue({ value: { ...newCatalogRecord('cases'), id: 'case', document } });
  render(<CatalogEditor kind="cases" id="case" canManage={false} />);
  await visitor.click(await screen.findByRole('tab', { name: 'Vitals' }));
  expect(screen.getByLabelText('Heart rate (bpm)')).toBeDisabled();
  expect(screen.getByLabelText('Heart rate (bpm)')).toHaveValue(84);
  expect(screen.getAllByRole('spinbutton')).toHaveLength(8);
  expect(screen.queryByText(/Fact disclosure/)).not.toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: /Questions|Instructor/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save case' })).not.toBeInTheDocument();
});
it('opens an incomplete draft and lets an author add a symptom', async () => {
  const visitor = userEvent.setup();
  vi.mocked(actions.readCatalog).mockResolvedValue({ value: {
    ...newCatalogRecord('cases'), id: 'case', code: 'case', title: 'Incomplete case',
    document: { version: 4, code: 'case', title: 'Incomplete case', source_language: 'en' } as never,
  } });
  render(<CatalogEditor kind="cases" id="case" canManage />);
  await visitor.click(await screen.findByRole('tab', { name: 'Presentation & symptoms' }));
  await visitor.click(screen.getByRole('button', { name: 'Add symptom' }));
  expect(screen.getByLabelText('Symptom description (en)')).toHaveValue('');
  expect(screen.queryByLabelText(/Disclosure/)).not.toBeInTheDocument();
});
it('does not call the API for missing required category fields', async () => {
  const visitor = userEvent.setup();
  render(<CatalogEditor kind="categories" id="new" canManage />);
  await screen.findByLabelText('Code');
  await visitor.click(screen.getByRole('button', { name: 'Save clinical specialty' }));
  expect(await screen.findByText('Enter a clinical specialty description.')).toBeInTheDocument();
  expect(actions.saveCatalog).not.toHaveBeenCalled();
});
it('removes entries when history is explicitly changed to none', async () => {
  const visitor = userEvent.setup();
  const document = emptyDocument();
  document.history.medications = {
    knowledge: 'present',
    entries: [{ id: 'one', text: { en: 'Medicine' } }],
  };
  const change = vi.fn();
  render(<CaseFields document={document} section="history" language="en" onChange={change} />);
  await visitor.selectOptions(screen.getByLabelText('Medications status'), 'none');
  expect(change).toHaveBeenLastCalledWith(
    expect.objectContaining({
      history: expect.objectContaining({
        medications: expect.objectContaining({
          knowledge: 'none',
          entries: [],
        }),
      }),
    }),
  );
});
it('adds a blank symptom that can be saved as an incomplete draft', async () => {
  const change = vi.fn();
  const visitor = userEvent.setup();
  render(<CaseFields document={emptyDocument()} section="presentation" language="en" onChange={change} />);
  await visitor.click(screen.getByRole('button', { name: 'Add symptom' }));
  expect(change.mock.calls[0]![0].presentation.symptoms).toEqual([{ id: 'symptom_1' }]);
});
it('retains symptom translations and only clinical content in API payloads', () => {
  const row = { ...newCatalogRecord('cases'), code: 'case', title: 'Title',
    titles: { en: 'Old', hi: 'Hindi' }, document: emptyDocument() };
  row.document.presentation.symptoms = [{ id: 'symptom_1', description: { en: 'Pain', hi: 'Hindi symptom' } }];
  const payload = catalogPayload('cases', row);
  expect(payload).toMatchObject({ titles: { en: 'Title', hi: 'Hindi' }, document: {
    version: 4, code: 'case', title: 'Title', presentation: { symptoms: [{ description: { en: 'Pain', hi: 'Hindi symptom' } }] },
  } });
  expect(payload).not.toHaveProperty('document.dialogue');
  expect(payload).not.toHaveProperty('document.instructor');
  expect(payload).not.toHaveProperty('document.fact_disclosure');
  expect(nextEntryId('symptom', row.document.presentation.symptoms)).toBe('symptom_2');
});
it('validates bounds and every profile translation before saving', () => {
  const row = {
    ...newCatalogRecord('patients'),
    code: 'patient',
    name: 'Patient',
    names: { en: 'Patient' },
    height_cm: -3,
    languages: ['en', 'hi'],
  };
  expect(validateCatalog('patients', row)).toContain('Enter valid positive height and weight.');
  expect(validateCatalog('patients', row).join(' ')).toContain('hi');
});

it('recovers from a rejected server-action transport without retrying the write', async () => {
  const visitor = userEvent.setup();
  const row = {
    ...newCatalogRecord('categories'),
    id: 'category',
    version: 4,
    code: 'category',
    name: 'Category',
    names: { en: 'Category' },
    description: 'Description',
  };
  vi.mocked(actions.readCatalog).mockResolvedValue({ value: row });
  vi.mocked(actions.saveCatalog).mockRejectedValue(new Error('transport interrupted'));
  render(<CatalogEditor kind="categories" id="category" canManage />);
  await visitor.type(await screen.findByLabelText('English name'), ' changed');
  await visitor.click(screen.getByRole('button', { name: 'Save clinical specialty' }));
  expect(
    await screen.findByText('The request could not be confirmed. Reload the record before retrying.'),
  ).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save clinical specialty' })).toBeEnabled();
  expect(actions.saveCatalog).toHaveBeenCalledTimes(1);
});
