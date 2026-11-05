'use client';
import { BackNavigation } from './BackNavigation';
import { callAction } from '@/lib/call-action';
import Link from 'next/link';
import { useEffect, useId, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Button,
  Card,
  CardBody,
  Checkbox,
  ConfirmDialog,
  Notice,
  PageHeader,
  Select,
  Tabs,
  TextField,
  tabButtonId,
} from '@pms/ui';
import { catalogOptions, readCatalog, saveCatalog } from '@/lib/catalog-actions';
import {
  CATALOG_LABELS,
  editableDocument,
  newCatalogRecord,
  validateCatalog,
  type CatalogKind,
  type CatalogRecord,
  type CatalogOptions,
} from '@/lib/patient-catalog';
import { CaseFields } from './CaseFields';
import { FormTextArea } from './FormTextArea';
const caseTabs = [
  { id: 'details', label: 'Details' },
  { id: 'presentation', label: 'Presentation & symptoms' },
  { id: 'history', label: 'History' },
  { id: 'vitals', label: 'Vitals' },
];
export function CatalogEditor({
  kind,
  id,
  canManage,
}: {
  kind: CatalogKind;
  id: string;
  canManage: boolean;
}) {
  const router = useRouter();
  const panel = useId();
  const labels = CATALOG_LABELS[kind];
  const [row, setRow] = useState<CatalogRecord>();
  const [options, setOptions] = useState<CatalogOptions>();
  const [error, setError] = useState<string>();
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState('details');
  const [language, setLanguage] = useState('en');
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let live = true;
    setRow(undefined);
    setError(undefined);
    Promise.all([
      callAction(() => catalogOptions()),
      id === 'new'
        ? Promise.resolve({ value: newCatalogRecord(kind), error: undefined })
        : callAction(() => readCatalog(kind, id)),
    ])
      .then(([o, r]) => {
        if (!live) return;
        if (o.error !== undefined || r.error !== undefined) {
          setError(o.error ?? r.error);
          return;
        }
        setOptions(o.value);
        setRow(r.value);
        setDirty(false);
      })
      .catch(() => {
        if (live) setError('Unable to load this record. Please retry.');
      });
    return () => {
      live = false;
    };
  }, [id, kind, reload]);
  useEffect(() => {
    if (!dirty) return;
    const listener = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', listener);
    return () => window.removeEventListener('beforeunload', listener);
  }, [dirty]);
  function patch(value: Partial<CatalogRecord>) {
    setRow((current) => (current ? { ...current, ...value } : current));
    setDirty(true);
    setSaved(false);
  }
  async function save() {
    if (!row || busy) return;
    const issues = validateCatalog(kind, row);
    setErrors(issues);
    if (issues.length) return;
    setBusy(true);
    setError(undefined);
    const result = await callAction(() => saveCatalog(kind, row));
    setBusy(false);
    if (result.error !== undefined) {
      setError(result.error);
      return;
    }
    setRow(result.value);
    setDirty(false);
    setSaved(true);
    if (id === 'new') router.replace('/catalog/' + kind + '/' + result.value.id);
  }
  if (!row || !options)
    return (
      <div className="pms-page">
        <BackNavigation href={'/catalog/' + kind} label={'Back to ' + labels.title.toLowerCase()} />
        <PageHeader title={id === 'new' ? 'Create ' + labels.singular : labels.title} />
        {error ? (
          <Notice
            tone="danger"
            title="Could not load editor"
            action={<Button onClick={() => setReload((x) => x + 1)}>Retry</Button>}
          >
            {error}
          </Notice>
        ) : (
          <p role="status">Loading record…</p>
        )}
      </div>
    );
  const langs = Array.from(
    new Map(
      [
        { code: 'en', name: 'English' },
        ...options.languages,
        ...options.conversation_languages,
        ...(row.languages ?? []).map((code) => ({ code, name: code })),
      ].map((l) => [l.code, l]),
    ).values(),
  );
  const choices = langs.map((l) => ({
    value: l.code,
    label: l.name + ' (' + l.code + ')',
  }));
  return (
    <div className="pms-page">
      <BackNavigation
        label={'Back to ' + labels.title.toLowerCase()}
        disabled={busy}
        onBack={() => (dirty ? setDiscard(true) : router.push('/catalog/' + kind))}
      />
      <PageHeader
        overline="Content catalog"
        title={(id === 'new' ? 'Create ' : canManage ? 'Edit ' : 'View ') + labels.singular}
        lede={
          kind === 'patients'
            ? 'Fictional patient identity. The device/manikin display name is configured separately.'
            : kind === 'cases'
              ? 'Save incomplete cases as inactive. Activate when all required content is ready.'
              : labels.description
        }
        actions={
          <>
            {canManage ? (
              <Button loading={busy} disabled={!dirty && id !== 'new'} onClick={() => void save()}>
                Save {labels.singular}
              </Button>
            ) : null}
            {canManage && kind === 'cases' && row.id && row.is_active && !dirty ? (
              <Link className="pms-btn pms-btn--ghost" href={'/scenarios?source_case_id=' + row.id}>
                Copy into training draft
              </Link>
            ) : null}
          </>
        }
      />
      {saved ? (
        <Notice tone="success" title="Saved">
          Your changes are saved.
        </Notice>
      ) : null}
      {error ? (
        <Notice tone="danger" title="Could not save">
          {error}
        </Notice>
      ) : null}
      {errors.length ? (
        <Notice tone="danger" title="Check these fields">
          <ul>
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </Notice>
      ) : null}
      <Card>
        <CardBody>
          <form
            className="pms-console__tenant-form"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <div className="pms-console__tenant-form">
              <div className="pms-console__tenant-form-grid">
                <Select label="Editing language" value={language} options={choices} onChange={setLanguage} />
                <Checkbox
                  disabled={!canManage || busy}
                  checked={row.is_active}
                  onChange={(e) => patch({ is_active: e.target.checked })}
                >
                  Active for new practice
                </Checkbox>
              </div>
              {kind === 'cases' ? (
                <Tabs tabs={caseTabs} active={tab} onChange={setTab} label="Case sections" panelId={panel} />
              ) : null}
              <div
                id={panel}
                role={kind === 'cases' ? 'tabpanel' : undefined}
                aria-labelledby={kind === 'cases' ? tabButtonId(tab, panel) : undefined}
              >
                <fieldset disabled={!canManage || busy} className="pms-console__tenant-fieldset">
                  <legend>
                    {kind === 'cases' ? caseTabs.find((t) => t.id === tab)?.label : labels.title}
                  </legend>
                  {kind !== 'cases' || tab === 'details' ? (
                    <div className="pms-console__tenant-form">
                      <div className="pms-console__tenant-form-grid">
                        <TextField
                          label="Code"
                          hint="Permanent identifier: lowercase letters, numbers and underscores."
                          value={row.code}
                          disabled={!!row.id}
                          maxLength={40}
                          pattern="[a-z][a-z0-9_]{0,39}"
                          required
                          onChange={(e) => patch({ code: e.target.value })}
                        />
                        <TextField
                          label={kind === 'cases' ? 'English title' : 'English name'}
                          value={kind === 'cases' ? row.title : row.name}
                          maxLength={120}
                          required
                          onChange={(e) =>
                            patch(
                              kind === 'cases'
                                ? {
                                    title: e.target.value,
                                    titles: {
                                      ...row.titles,
                                      en: e.target.value,
                                    },
                                  }
                                : {
                                    name: e.target.value,
                                    names: { ...row.names, en: e.target.value },
                                  },
                            )
                          }
                        />
                      </div>
                      {language !== 'en' ? (
                        <TextField
                          label={'Name / title (' + language + ')'}
                          maxLength={120}
                          value={(kind === 'cases' ? row.titles : row.names)?.[language] ?? ''}
                          onChange={(e) => {
                            const key = kind === 'cases' ? 'titles' : 'names';
                            const values = { ...row[key] };
                            if (e.target.value) values[language] = e.target.value;
                            else delete values[language];
                            patch({ [key]: values });
                          }}
                        />
                      ) : null}
                      {kind === 'categories' ? (
                        <>
                          <FormTextArea
                            label="Description"
                            value={row.description ?? ''}
                            maxLength={600}
                            required
                            onChange={(e) => patch({ description: e.target.value })}
                          />
                          <TextField
                            label="Display order"
                            type="number"
                            min={0}
                            max={10000}
                            value={row.sort_order ?? 0}
                            onChange={(e) => patch({ sort_order: Number(e.target.value) })}
                          />
                        </>
                      ) : null}
                      {kind === 'patients' ? (
                        <>
                          <div className="pms-console__tenant-form-grid">
                            <TextField
                              label="Age (years)"
                              type="number"
                              min={0}
                              max={150}
                              step={1}
                              value={row.age_years ?? ''}
                              required
                              onChange={(e) =>
                                patch({
                                  age_years: e.target.value === '' ? undefined : Number(e.target.value),
                                })
                              }
                            />
                            <Select
                              label="Sex"
                              value={row.sex ?? 'unspecified'}
                              options={['unspecified', 'female', 'male', 'intersex'].map((value) => ({
                                value,
                                label: value,
                              }))}
                              onChange={(sex) => patch({ sex })}
                            />
                            <TextField
                              label="Height (cm)"
                              type="number"
                              min={0.01}
                              max={400}
                              step={0.01}
                              value={row.height_cm ?? ''}
                              onChange={(e) => patch({ height_cm: Number(e.target.value) })}
                            />
                            <TextField
                              label="Weight (kg)"
                              type="number"
                              min={0.01}
                              max={2000}
                              step={0.01}
                              value={row.weight_kg ?? ''}
                              onChange={(e) => patch({ weight_kg: Number(e.target.value) })}
                            />
                          </div>
                          <TextField
                            label={'Occupation (' + language + ')'}
                            maxLength={600}
                            value={row.occupations?.[language] ?? ''}
                            onChange={(e) =>
                              patch({
                                occupations: {
                                  ...row.occupations,
                                  [language]: e.target.value,
                                },
                              })
                            }
                          />
                          <FormTextArea
                            label={'Background (' + language + ')'}
                            maxLength={600}
                            value={row.backgrounds?.[language] ?? ''}
                            onChange={(e) =>
                              patch({
                                backgrounds: {
                                  ...row.backgrounds,
                                  [language]: e.target.value,
                                },
                              })
                            }
                          />
                          <Checkbox
                            checked={row.languages?.includes(language) ?? false}
                            disabled={language === 'en' || row.preferred_language === language}
                            onChange={(e) =>
                              patch({
                                languages: e.target.checked
                                  ? [...(row.languages ?? []), language]
                                  : (row.languages ?? []).filter((l) => l !== language),
                              })
                            }
                          >
                            Include {language} in this profile (complete all three translated fields)
                          </Checkbox>
                          <Select
                            label="Preferred language"
                            value={row.preferred_language ?? 'en'}
                            options={choices.filter((c) => row.languages?.includes(c.value))}
                            onChange={(preferred_language) => patch({ preferred_language })}
                          />
                        </>
                      ) : null}
                      {kind === 'cases' ? (
                        <>
                          <div className="pms-console__tenant-form-grid">
                            <Select
                              label="Clinical specialty"
                              value={row.category_id ?? ''}
                              disabled={!!row.id}
                              options={[
                                { value: '', label: 'Select clinical specialty' },
                                ...options.categories.map((c) => ({
                                  value: c.id,
                                  label: (c.name ?? c.code) + (c.is_active ? '' : ' (inactive)'),
                                })),
                              ]}
                              onChange={(category_id) => patch({ category_id })}
                            />
                            <Select
                              label="Patient profile"
                              value={row.patient_identity_id ?? ''}
                              disabled={!!row.id}
                              options={[
                                { value: '', label: 'Select patient profile' },
                                ...options.patients.map((p) => ({
                                  value: p.id,
                                  label: (p.name ?? p.code) + (p.is_active ? '' : ' (inactive)'),
                                })),
                              ]}
                              onChange={(patient_identity_id) => patch({ patient_identity_id })}
                            />
                          </div>
                          <p className="pms-meta">
                            Clinical specialty and patient profile are fixed after creation. Create a new case to use a
                            different association.
                          </p>
                          <Select
                            label="Source language"
                            value={row.document?.source_language ?? 'en'}
                            options={choices}
                            onChange={(source_language) =>
                              patch({
                                document: { ...row.document!, source_language },
                              })
                            }
                          />
                          {row.patient_identity_id ? (
                            <Link href={'/catalog/patients/' + row.patient_identity_id}>
                              View selected patient profile
                            </Link>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                  ) : row.document ? (
                    <CaseFields
                      document={editableDocument(row.document)}
                      language={language}
                      section={tab}
                      readOnly={!canManage}
                      onChange={(document) => patch({ document })}
                    />
                  ) : null}
                </fieldset>
              </div>
            </div>
          </form>
        </CardBody>
      </Card>
      <ConfirmDialog
        open={discard}
        title="Discard unsaved changes?"
        confirmLabel="Discard changes"
        tone="danger"
        onCancel={() => setDiscard(false)}
        onConfirm={() => router.push('/catalog/' + kind)}
      >
        Your unsaved edits will be lost.
      </ConfirmDialog>
    </div>
  );
}
