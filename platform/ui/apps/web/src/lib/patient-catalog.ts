export type CatalogKind = 'categories' | 'patients' | 'cases';
export type Localized = Record<string, string>;
export const HISTORY_FIELDS = [
  'past_conditions',
  'surgeries',
  'medications',
  'allergies',
  'family',
  'social',
] as const;
export type HistoryField = (typeof HISTORY_FIELDS)[number];
export const VITALS = [
  ['temperature_c', 'Temperature (°C)', 100],
  ['heart_rate_bpm', 'Heart rate (bpm)', 1000],
  ['pulse_bpm', 'Pulse (bpm)', 1000],
  ['systolic_mmhg', 'Systolic pressure (mmHg)', 1000],
  ['diastolic_mmhg', 'Diastolic pressure (mmHg)', 1000],
  ['respirations_per_minute', 'Respiratory rate', 1000],
  ['spo2_percent', 'Oxygen saturation (%)', 100],
  ['pain_0_10', 'Pain (0–10)', 10],
] as const;
export type VitalKey = (typeof VITALS)[number][0];
export type CaseDocument = {
  version: 4 | 5;
  code: string;
  title?: string;
  learner_label?: string;
  specialty?: string;
  source_language: string;
  patient: {
    name?: string;
    age_years?: number;
    sex?: string;
    occupation?: Localized;
    height_cm?: number;
    weight_kg?: number;
  };
  presentation: {
    chief_complaint?: Localized;
    onset?: Localized;
    duration?: Localized;
    severity?: Localized;
    symptoms: { id: string; description?: Localized }[];
  };
  history: Partial<
    Record<
      HistoryField,
      {
        knowledge: 'unknown' | 'none' | 'present';
        entries: { id: string; text: Localized }[];
      }
    >
  >;
  vitals: Partial<Record<VitalKey, number>>;
  localizations: Record<string, unknown>;
  background?: BackgroundEntry[];
};
export const BACKGROUND_FIELDS = [
  ['food_drink', 'Food & drink'], ['sleep_activity', 'Sleep & activity'],
  ['work_home', 'Work & home life'], ['personality', 'Personality & interests'],
  ['additional', 'Additional background'],
] as const;
export type BackgroundEntry = {
  id: (typeof BACKGROUND_FIELDS)[number][0];
  text: Localized;
  allow_variation: boolean;
  choices: { id: string; text: Localized }[];
};
export type CatalogRecord = {
  id: string;
  code: string;
  version: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
  name?: string;
  names?: Localized;
  description?: string;
  sort_order?: number;
  age_years?: number;
  sex?: string;
  occupations?: Localized;
  backgrounds?: Localized;
  height_cm?: number;
  weight_kg?: number;
  languages?: string[];
  preferred_language?: string;
  category_id?: string;
  patient_identity_id?: string;
  specialty_id?: string;
  patient_profile_id?: string;
  title?: string;
  titles?: Localized;
  revision?: number;
  document?: CaseDocument;
};
export type LanguageOption = {
  code: string;
  name: string;
  speech_locale?: string;
  is_active?: boolean;
};
export type CatalogOptions = {
  categories: CatalogRecord[];
  patients: CatalogRecord[];
  languages: LanguageOption[];
  conversation_languages: LanguageOption[];
};
export type CatalogQuery = { q: string; state: string; limit: number };
export const CATALOG_LABELS: Record<CatalogKind, { title: string; singular: string; description: string }> = {
  categories: {
    title: 'Clinical specialties',
    singular: 'clinical specialty',
    description: 'Organize patient practice cases by clinical specialty.',
  },
  patients: {
    title: 'Patient profiles',
    singular: 'patient profile',
    description: 'Manage fictional identities used by patient cases and manikin practice.',
  },
  cases: {
    title: 'Case drafts',
    singular: 'case',
    description: 'Manage presentation, symptoms, history and vitals.',
  },
};
export function emptyDocument(): CaseDocument {
  return {
    version: 4,
    code: '',
    title: '',
    source_language: 'en',
    patient: {},
    presentation: { symptoms: [] },
    history: {},
    vitals: {},
    localizations: {},
  };
}
export function editableDocument(document: CaseDocument): CaseDocument {
  const empty = emptyDocument();
  return {
    ...empty,
    ...document,
    patient: { ...empty.patient, ...document.patient },
    presentation: {
      ...empty.presentation,
      ...document.presentation,
      symptoms: document.presentation?.symptoms ?? [],
    },
    history: { ...empty.history, ...document.history },
    vitals: { ...empty.vitals, ...document.vitals },
    localizations: { ...empty.localizations, ...document.localizations },
  };
}
export function newCatalogRecord(kind: CatalogKind): CatalogRecord {
  return {
    id: '',
    code: '',
    version: 0,
    is_active: kind !== 'cases',
    ...(kind === 'categories'
      ? { name: '', names: { en: '' }, description: '', sort_order: 0 }
      : kind === 'patients'
        ? {
            name: '',
            names: { en: '' },
            age_years: 30,
            sex: 'unspecified',
            occupations: { en: '' },
            backgrounds: { en: '' },
            height_cm: 170,
            weight_kg: 70,
            languages: ['en'],
            preferred_language: 'en',
          }
        : {
            title: '',
            titles: { en: '' },
            category_id: '',
            patient_identity_id: '',
            document: emptyDocument(),
          }),
  };
}
export function catalogPayload(kind: CatalogKind, row: CatalogRecord) {
  const common = { code: row.code.trim(), is_active: row.is_active };
  if (kind === 'categories')
    return {
      ...common,
      name: row.name?.trim(),
      names: { ...row.names, en: row.name?.trim() },
      description: row.description?.trim(),
      sort_order: row.sort_order,
    };
  if (kind === 'patients')
    return {
      ...common,
      name: row.name?.trim(),
      names: { ...row.names, en: row.name?.trim() },
      age_years: row.age_years,
      sex: row.sex,
      occupations: row.occupations,
      backgrounds: row.backgrounds,
      height_cm: Number(row.height_cm),
      weight_kg: Number(row.weight_kg),
      languages: row.languages,
      preferred_language: row.preferred_language,
    };
  return {
    ...common,
    title: row.title?.trim(),
    titles: { ...row.titles, en: row.title?.trim() },
    specialty_id: row.category_id,
    patient_profile_id: row.patient_identity_id,
    document: { ...row.document, code: common.code, title: row.title?.trim() },
  };
}
export function validateCatalog(kind: CatalogKind, row: CatalogRecord): string[] {
  const errors: string[] = [];
  if (!/^[a-z][a-z0-9_]{0,39}$/.test(row.code))
    errors.push(
      'Code: use a lowercase letter followed by up to 39 lowercase letters, numbers or underscores.',
    );
  if (!(kind === 'cases' ? row.title : row.name)?.trim()) errors.push('Enter a display name or title.');
  if (kind === 'categories' && !row.description?.trim()) errors.push('Enter a clinical specialty description.');
  if (kind === 'patients') {
    if (!Number.isInteger(row.age_years) || row.age_years! < 0 || row.age_years! > 150)
      errors.push('Age must be a whole number from 0 to 150.');
    if (
      !row.height_cm ||
      row.height_cm < 0 ||
      row.height_cm > 400 ||
      !row.weight_kg ||
      row.weight_kg < 0 ||
      row.weight_kg > 2000
    )
      errors.push('Enter valid positive height and weight.');
    for (const lang of row.languages ?? [])
      if (![row.names?.[lang], row.occupations?.[lang], row.backgrounds?.[lang]].every((v) => v?.trim()))
        errors.push('Complete name, occupation and background for ' + lang + '.');
  }
  if (kind === 'cases') {
    if (!row.category_id || !row.patient_identity_id) errors.push('Select a clinical specialty and patient profile.');
    const v = row.document?.vitals;
    if (v?.systolic_mmhg !== undefined && v.diastolic_mmhg !== undefined && v.diastolic_mmhg > v.systolic_mmhg)
      errors.push('Diastolic pressure cannot exceed systolic pressure.');

  }
  return errors;
}
export function nextEntryId(prefix: string, rows: { id: string }[]): string {
  let n = 1;
  while (rows.some((r) => r.id === prefix + '_' + n)) n++;
  return prefix + '_' + n;
}
