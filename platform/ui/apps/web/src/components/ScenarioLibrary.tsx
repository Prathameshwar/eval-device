'use client';
import { BackNavigation } from './BackNavigation';
import { callAction } from '@/lib/call-action';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  DataTable,
  FilterBar,
  Notice,
  PageHeader,
  Pager,
  Select,
  TableSearch,
  Tabs,
  TextField,
  tabButtonId,
  WorkflowSteps,
  type Column,
} from '@pms/ui';
import {
  listScenarios,
  readScenario,
  createScenario,
  saveScenario,
  submitScenario,
  archiveScenario,
  validateScenario,
  approveScenario,
  retireScenario,
  refreshScenarioCase,
  type ScenarioRow,
  type ScenarioValidation,
} from '@/lib/scenario-actions';
import { catalogOptions, listCatalog } from '@/lib/catalog-actions';
import { useApiDirectory } from '@/lib/use-api-directory';
import { editableDocument, type CaseDocument, type LanguageOption } from '@/lib/patient-catalog';
import { CaseFields } from './CaseFields';
import { FormTextArea } from './FormTextArea';
import { ClinicalSpecialtyPicker } from './ClinicalSpecialtyPicker';
import styles from './ScenarioWorkspace.module.css';
const tabs = [
  { id: 'presentation', label: 'Presentation & symptoms' },
  { id: 'history', label: 'History' },
  { id: 'background', label: 'Patient background' },
  { id: 'vitals', label: 'Vitals' },
];
const steps = [
  { id: 'patient', label: 'Patient & specialty' },
  { id: 'case', label: 'Clinical details' },
  { id: 'review', label: 'Review & submit' },
] as const;
function scenarioCode(title: string) {
  const code = title.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40);
  return /^[a-z]/.test(code) ? code : 'scenario_' + code.slice(0, 31);
}
type ScenarioLibraryProps = {
  contextId: string; canAuthor?: boolean; canReview?: boolean; sourceCaseId?: string;
};
export function ScenarioLibrary(props: ScenarioLibraryProps) {
  return <ScenarioLibraryContent key={props.contextId} {...props} />;
}
function ScenarioLibraryContent({ contextId, canAuthor = true, canReview = true, sourceCaseId }: ScenarioLibraryProps) {
  const fetchPage = useCallback(
    (q: { q: string; limit: number; view: string }, cursor?: string) =>
      callAction(() => listScenarios(contextId, q, cursor)),
    [contextId],
  );
  const directory = useApiDirectory({ q: '', limit: 25, view: 'published' }, fetchPage);
  const versionView = directory.query.view === 'published' || directory.query.view === 'retired';
  const [row, setRow] = useState<ScenarioRow>();
  const [published, setPublished] = useState(false);
  const [creating, setCreating] = useState(false);
  const [code, setCode] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [specialtyId, setSpecialtyId] = useState('');
  const [specialties, setSpecialties] = useState<{ id: string; name?: string; code: string; is_active: boolean }[]>([]);
  const [existingCases, setExistingCases] = useState<{ id: string; title?: string; code: string }[]>([]);
  const [source, setSource] = useState<string>();
  const [sourceCase, setSourceCase] = useState<string>();
  const createKey = useRef('');
  const publishKey = useRef('');
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState('presentation');
  const [step, setStep] = useState<'patient' | 'case' | 'review'>('patient');
  const [language, setLanguage] = useState('en');
  const [languages, setLanguages] = useState<LanguageOption[]>([{ code: 'en', name: 'English' }]);
  const [validation, setValidation] = useState<ScenarioValidation>();
  const [educator, setEducator] = useState('');
  const [statement, setStatement] = useState('');
  const [confirm, setConfirm] = useState<'publish' | 'archive' | 'retire' | 'discard'>();
  const panel = useId();
  const stepHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { stepHeading.current?.focus(); }, [step, row?.id]);
  useEffect(() => {
    if (!sourceCaseId || !canAuthor) return;
    setSourceCase(sourceCaseId);
    setSource(undefined);
    setCreating(true);
    createKey.current = crypto.randomUUID();
  }, [sourceCaseId, canAuthor]);
  useEffect(() => {
    let live = true;
    setSpecialties([]);
    void callAction(() => catalogOptions()).then((r) => {
      if (live && r.value) {
        setLanguages(r.value.languages);
        setSpecialties((r.value.categories ?? []).filter((item) => item.is_active));
      }
      if (live && r.error) setError(r.error);
    });
    return () => {
      live = false;
    };
  }, [contextId]);
  useEffect(() => {
    if (!canAuthor) return;
    let live = true;
    setExistingCases([]);
    void callAction(() => listCatalog('cases', { q: '', state: 'active', limit: 100 })).then((result) => {
      if (live && result.value) setExistingCases(result.value.items);
    });
    return () => { live = false; };
  }, [contextId, canAuthor]);
  useEffect(() => {
    if (!dirty) return;
    const before = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', before);
    return () => window.removeEventListener('beforeunload', before);
  }, [dirty]);
  async function open(record: ScenarioRow) {
    setBusy(true);
    setError(undefined);
    const p = versionView;
    const r = await callAction(() => readScenario(contextId, record.id, p));
    setBusy(false);
    if (r.error !== undefined) {
      setError(r.error);
      return;
    }
    setRow(r.value);
    setPublished(p);
    setDirty(false);
    setTab('presentation');
    setStep(!p && r.value.submitted_revision != null && r.value.submitted_revision === r.value.revision
      ? 'review' : 'patient');
    setLanguage(r.value.document?.source_language ?? 'en');
    setEducator('');
    setStatement('');
    setValidation(undefined);
    setNotice('');
    publishKey.current = crypto.randomUUID();
  }
  function patch(document: CaseDocument) {
    if (!row) return;
    setRow({ ...row, document });
    setDirty(true);
    setValidation(undefined);
    setNotice('');
    publishKey.current = crypto.randomUUID();
  }
  function chooseSpecialty(value: string) {
    if (!row?.document) return;
    const selected = specialties.find((item) => item.id === value);
    setRow((current) => current?.document ? { ...current, specialty_id: value || null,
      document: { ...current.document, specialty: selected?.name || selected?.code || current.document.specialty } } : current);
    setDirty(true);
    setValidation(undefined);
    setNotice('');
    publishKey.current = crypto.randomUUID();
  }
  async function create() {
    if (!source && !sourceCase && (!newTitle.trim() || !specialtyId)) {
      setError('Enter a scenario name and choose a clinical specialty.');
      return;
    }
    setBusy(true);
    setError(undefined);
    const r = await callAction(() => createScenario(contextId, code, createKey.current, source, sourceCase,
      !source && !sourceCase ? specialtyId || undefined : undefined, newTitle));
    setBusy(false);
    if (r.error !== undefined) {
      setError(r.error);
      return;
    }
    setRow(r.value);
    setPublished(false);
    setCreating(false);
    setDirty(false);
    setTab('presentation');
    setStep('patient');
    setLanguage(r.value.document?.source_language ?? 'en');
    setNotice('Draft created. Add the patient and case details, then submit it for review.');
    setValidation(undefined);
    publishKey.current = crypto.randomUUID();
    directory.reload();
  }
  async function save() {
    if (!row) return;
    setBusy(true);
    setError(undefined);
    const r = await callAction(() => saveScenario(contextId, row));
    setBusy(false);
    if (r.error !== undefined) {
      setError(r.error);
      return;
    }
    setRow(r.value);
    setDirty(false);
    setValidation(undefined);
    setNotice('Draft saved.');
    directory.reload();
  }
  async function validate() {
    if (!row) return;
    setBusy(true);
    setError(undefined);
    const r = await callAction(() => validateScenario(contextId, row));
    setBusy(false);
    if (r.error !== undefined) setError(r.error);
    else setValidation(r.value);
  }
  async function submit() {
    if (!row) return;
    setBusy(true);
    setError(undefined);
    const result = await callAction(() => submitScenario(contextId, row));
    setBusy(false);
    if (result.error !== undefined) {
      setError(result.error);
      return;
    }
    setRow(result.value);
    setValidation(undefined);
    setNotice('Draft submitted for independent review.');
    directory.reload();
  }
  async function refreshCase() {
    if (!row) return;
    setBusy(true);
    setError(undefined);
    const result = await callAction(() => refreshScenarioCase(contextId, row));
    setBusy(false);
    if (result.error !== undefined) setError(result.error);
    else {
      setRow(result.value);
      setValidation(undefined);
      setNotice('Draft refreshed from the current tenant case. Review it before publication.');
      directory.reload();
    }
  }
  async function approve(publish = false) {
    if (!row) return;
    if (educator.trim().length < 2 || statement.trim().length < 20) {
      setError('Enter the educator name and a review statement of at least 20 characters.');
      setConfirm(undefined);
      return;
    }
    setBusy(true);
    setError(undefined);
    const r = await callAction(() =>
      approveScenario(
        contextId,
        row,
        { educator_name: educator.trim(), statement: statement.trim() },
        language,
        publish ? publishKey.current : undefined,
      ),
    );
    if (r.error !== undefined) {
      setBusy(false);
      setError(r.error);
      return;
    }
    setConfirm(undefined);
    setRow(r.value);
    setPublished(publish);
    setValidation(undefined);
    setNotice(
      publish
        ? 'Published a new immutable scenario version.'
        : 'Language review recorded for this draft revision.',
    );
    if (!publish) {
      const checked = await callAction(() => validateScenario(contextId, r.value));
      if (checked.error !== undefined) setError(checked.error);
      else setValidation(checked.value);
    }
    setBusy(false);
    directory.reload();
  }
  async function changeState() {
    if (!row) return;
    setBusy(true);
    setError(undefined);
    if (published) {
      const r = await callAction(() => retireScenario(contextId, row.id));
      setBusy(false);
      if (r.error !== undefined) {
        setError(r.error);
        return;
      }
      setRow({ ...row, is_active: false });
      setNotice('Scenario retired.');
    } else {
      const r = await callAction(() => archiveScenario(contextId, row));
      setBusy(false);
      if (r.error !== undefined) {
        setError(r.error);
        return;
      }
      setRow(r.value);
      setNotice(r.value.is_archived ? 'Draft archived.' : 'Draft restored.');
    }
    setConfirm(undefined);
    directory.reload();
  }
  const d = row?.document ? editableDocument(row.document) : undefined;
  const editable = !!row && canAuthor && !published && !row.is_archived && [4, 5].includes(row.schema_version);
  const copyable = !!row && published && [4, 5].includes(row.schema_version) && !!row.specialty_id &&
    specialties.some((item) => item.id === row.specialty_id);
  const columns: Column<ScenarioRow>[] = [
    {
      key: 'title',
      header: 'Scenario',
      type: 'custom',
      render: (r) => (
        <div className="pms-console__tenant-cell">
          <strong>{r.title ?? 'Untitled'}</strong>
          <span className="pms-meta">{r.code}</span>
          {r.publication_source === 'system_starter' ? (
            <span className="pms-meta">System-provisioned starter · no tenant clinical review</span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      type: 'custom',
      render: (r) => versionView
        ? (r.is_active ? 'Published' : 'Retired')
        : r.is_archived ? 'Archived'
          : r.submitted_revision === r.revision ? 'Awaiting review' : 'Draft',
    },
    {
      key: 'revision',
      header: versionView ? 'Version' : 'Revision',
      type: 'custom',
      render: (r) => r.revision ?? r.version,
    },
    {
      key: 'action',
      header: 'Actions',
      type: 'custom',
      render: (r) => (
        <Button variant="ghost" disabled={busy} onClick={() => void open(r)}>
          Open
        </Button>
      ),
    },
  ];
  return (
    <div className={`pms-page ${row ? styles.editor : creating ? styles.creation : ''}`}>
      {row ? <BackNavigation label="Back to scenarios" disabled={busy}
        onBack={() => (dirty ? setConfirm('discard') : setRow(undefined))} />
        : creating ? <BackNavigation label="Back to scenarios" disabled={busy} onBack={() => setCreating(false)} />
        : <BackNavigation href="/home" label="Back to home" />}
      <PageHeader
        overline="Tenant content"
        title={creating && !row ? 'New scenario' : row
          ? published ? (row.is_active ? 'Published scenario' : 'Retired scenario') : 'Scenario draft'
          : 'Scenarios'}
        lede={
          row
            ? published ? 'View the presentation, symptoms, history and vitals for this published version.'
              : 'Create the presentation, symptoms, history and vitals in one place.'
            : 'Create, review and publish tenant scenarios. Published versions preserve their original content.'
        }
        actions={
          !row && !creating && canAuthor ? (
            <Button
              onClick={() => {
                setCreating(true);
                setSource(undefined);
                setSourceCase(undefined);
                setCode('');
                setNewTitle('');
                setSpecialtyId('');
                createKey.current = crypto.randomUUID();
              }}
            >
              New scenario
            </Button>
          ) : null
        }
      />
      {error || directory.error ? (
        <Notice tone="danger" title="Request failed">
          {error ?? directory.error}
        </Notice>
      ) : null}
      {notice ? (
        <Notice tone="success" title="Scenario updated">
          {notice}
        </Notice>
      ) : null}
      {creating && !row ? (
        <div className={styles.editor}>
          <WorkflowSteps steps={steps} current="patient" />
          <Card><CardBody>
            <form className={styles.form} onSubmit={(event) => { event.preventDefault(); void create(); }}>
              <fieldset disabled={busy} className={styles.formFields} aria-label="New scenario details">
              <h2>Start with a name and specialty</h2>
              <p className="pms-meta">The remaining patient and case details can be saved as a draft.</p>
              {!source ? <Select label="Start from an existing case (optional)" value={sourceCase ?? ''}
                options={[{ value: '', label: 'Create a new patient story' },
                  ...existingCases.map((item) => ({ value: item.id, label: item.title || item.code }))]}
                onChange={(value) => {
                  setSourceCase(value || undefined);
                  if (value) {
                    const selected = existingCases.find((item) => item.id === value);
                    setCode(scenarioCode(selected?.title || selected?.code || 'scenario'));
                  } else setCode(newTitle ? scenarioCode(newTitle) : '');
                  createKey.current = crypto.randomUUID();
                }} /> : null}
              {!source && !sourceCase ? <>
                <TextField label="Scenario name" required maxLength={120} value={newTitle}
                  onChange={(event) => {
                    const title = event.target.value;
                    setNewTitle(title);
                    setCode(scenarioCode(title));
                    createKey.current = crypto.randomUUID();
                  }} />
                <ClinicalSpecialtyPicker value={specialtyId} options={specialties} canCreate={canAuthor}
                  onChange={(value) => { setSpecialtyId(value); createKey.current = crypto.randomUUID(); }}
                  onCreated={(option) => setSpecialties((items) => [...items, option])} />
              </> : <Notice tone="info" title="Copy existing content">
                This creates an editable draft. The published source remains unchanged.
              </Notice>}
              <TextField label="Scenario code" required maxLength={40} value={code}
                hint="Used as a stable identifier. Lowercase letters, numbers and underscores."
                onChange={(event) => { setCode(event.target.value); createKey.current = crypto.randomUUID(); }} />
              <div className={styles.actions}>
                <Button type="button" variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
                <Button type="submit" loading={busy} disabled={!code || busy}>Create draft</Button>
              </div>
              </fieldset>
            </form>
          </CardBody></Card>
        </div>
      ) : !row ? (
        <>
          <FilterBar>
            <TableSearch
              label="Search scenarios"
              value={directory.query.q}
              maxLength={120}
              onChange={(q) => directory.setQuery({ ...directory.query, q })}
            />
            <Select
              label="View"
              value={directory.query.view}
              options={[
                { value: 'drafts', label: 'Current drafts' },
                { value: 'archived', label: 'Archived drafts' },
                { value: 'published', label: 'Published versions' },
                { value: 'retired', label: 'Retired versions' },
              ]}
              onChange={(view) => directory.setQuery({ ...directory.query, view })}
            />
          </FilterBar>
          <DataTable
            caption="Scenarios"
            rows={directory.page.items}
            columns={columns}
            rowId={(r) => r.id}
            loading={directory.loading}
            emptyTitle="No scenarios found"
            emptyBody="Create a draft or choose another view."
          />
          <Pager
            count={directory.page.items.length}
            from={directory.page.from}
            limit={25}
            hasPrevious={directory.pageIndex > 0}
            hasNext={directory.page.has_more}
            onPrevious={() => directory.setPageIndex(directory.pageIndex - 1)}
            onNext={() => directory.setPageIndex(directory.pageIndex + 1)}
            busy={directory.loading}
          />
        </>
      ) : (
        <>
          <div className="pms-console__tenant-actions">
            {editable ? (
              <>
                {row.source_case_id ? (
                  <Button variant="ghost" disabled={busy || dirty} onClick={() => void refreshCase()}>
                    Refresh from source case
                  </Button>
                ) : null}
              </>
            ) : null}
            {!published && canAuthor ? (
              <Button variant="ghost" disabled={busy || dirty} onClick={() => setConfirm('archive')}>
                {row.is_archived ? 'Restore draft' : 'Archive draft'}
              </Button>
            ) : (
              <>
                {canAuthor && copyable ? <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => {
                    setSource(row.id);
                    setSourceCase(undefined);
                    setSpecialtyId('');
                    setNewTitle('');
                    setCode('');
                    setCreating(true);
                    setRow(undefined);
                    createKey.current = crypto.randomUUID();
                  }}
                >
                  Copy to new draft
                </Button> : null}
                {published && row.is_active && canReview ? (
                  <Button variant="ghost" onClick={() => setConfirm('retire')}>
                    Retire version
                  </Button>
                ) : null}
              </>
            )}
          </div>
          {![4, 5].includes(row.schema_version) ? (
            <Notice tone="warning" title="Reload this scenario">
              The scenario format has changed. Reload the page to load its current clinical details.
            </Notice>
          ) : null}
          {published && !row.execution_supported ? (
            <Notice tone="warning" title="Device sessions unavailable">
              This published version is not ready for device sessions. {copyable
                ? 'Copy it to a new draft, review both English and Hindi, and publish the new version before assigning it to a device.'
                : 'Create a new scenario with an active clinical specialty for device sessions.'}
            </Notice>
          ) : null}
          {published && row.publication_source === 'system_starter' ? (
            <Notice tone="info" title="System-provisioned starter">
              This published example was created during tenant setup without a tenant clinician's approval.
              A tenant clinician should review it and publish an approved version before assessed training.
            </Notice>
          ) : null}
          {published && row.approved_at && row.publication_source !== 'system_starter' ? (
            <p className="pms-meta">Approved {new Date(row.approved_at).toLocaleString()} by {row.approved_by}</p>
          ) : null}
          {!published && row.source_case_id ? (
            <p className="pms-meta">Copied from tenant case revision {row.source_case_revision}.
              Refresh explicitly after editing the case.</p>
          ) : null}
          {d && [4, 5].includes(row.schema_version) ? (
            <Card>
              <CardBody>
                <div className="pms-console__tenant-form">
                  <WorkflowSteps steps={steps.map((item) => item.id === 'review'
                    ? { ...item, label: published ? 'Summary' : !canAuthor ? 'Review & publish' : item.label } : item)} current={step} />
                  <h2 ref={stepHeading} tabIndex={-1} className={styles.stepHeading}>
                    {step === 'patient' ? 'Patient and specialty' : step === 'case' ? 'Clinical details' : 'Review the scenario'}
                  </h2>
                  <p className="pms-meta">
                    {row.code} · {published ? 'version ' + row.version : 'revision ' + row.revision}
                  </p>
                  <Select
                    label={step === 'review' ? 'Review language' : published || !editable ? 'Content language' : 'Editing language'}
                    options={languages.map((l) => ({
                      value: l.code,
                      label: l.name,
                    }))}
                    value={language}
                    onChange={(value) => { setLanguage(value); setNotice(''); }}
                    disabled={busy}
                  />
                  {step === 'case' ? <Tabs
                    tabs={tabs}
                    active={tab}
                    onChange={(value) => { if (!busy) setTab(value); }}
                    label="Scenario sections"
                    panelId={panel}
                  /> : null}
                  {step !== 'review' ? <div id={step === 'case' ? panel : undefined}
                    role={step === 'case' ? 'tabpanel' : undefined}
                    aria-labelledby={step === 'case' ? tabButtonId(tab, panel) : undefined}>
                    <fieldset disabled={!editable || busy} className={step === 'case' && tab === 'background'
                      ? styles.backgroundSection : 'pms-console__tenant-fieldset'}>
                      <legend>{step === 'patient' ? 'Patient and specialty' : tabs.find((t) => t.id === tab)?.label}</legend>
                      {step === 'patient' ? (
                        <div className="pms-console__tenant-form-grid">
                          <TextField
                            label="Title"
                            maxLength={120}
                            value={d.title ?? ''}
                            onChange={(e) =>
                              patch({
                                ...d,
                                title: e.target.value || undefined,
                              })
                            }
                          />
                          <ClinicalSpecialtyPicker value={row.specialty_id ?? ''} options={specialties}
                            selectedLabel={d.specialty}
                            canCreate={editable} disabled={!editable || !!row.source_case_id || !!row.source_scenario_id}
                            onChange={chooseSpecialty}
                            onCreated={(option) => {
                              setSpecialties((items) => [...items, option]);
                              setRow((current) => current?.document ? { ...current, specialty_id: option.id,
                                document: { ...current.document, specialty: option.name || option.code } } : current);
                            }} />
                          {row.source_case_id || row.source_scenario_id ?
                            <p className="pms-meta">This copy keeps its source clinical specialty.</p> : null}
                          <Select
                            label="Source language"
                            options={languages.map((l) => ({
                              value: l.code,
                              label: l.name,
                            }))}
                            value={d.source_language ?? 'en'}
                            onChange={(source_language) => patch({ ...d, source_language })}
                          />
                          <TextField
                            label="Patient name"
                            maxLength={120}
                            value={d.patient.name ?? ''}
                            onChange={(e) =>
                              patch({
                                ...d,
                                patient: {
                                  ...d.patient,
                                  name: e.target.value || undefined,
                                },
                              })
                            }
                          />
                          <TextField
                            label="Patient age"
                            type="number"
                            min={0}
                            max={150}
                            value={d.patient.age_years ?? ''}
                            onChange={(e) =>
                              patch({
                                ...d,
                                patient: {
                                  ...d.patient,
                                  age_years: e.target.value === '' ? undefined : Number(e.target.value),
                                },
                              })
                            }
                          />
                          <Select
                            label="Patient sex"
                            value={d.patient.sex ?? 'unspecified'}
                            options={['unspecified', 'female', 'male', 'intersex'].map((value) => ({
                              value,
                              label: value,
                            }))}
                            onChange={(sex) => patch({ ...d, patient: { ...d.patient, sex } })}
                          />
                          <TextField
                            label={'Occupation (' + language + ')'}
                            maxLength={600}
                            value={d.patient.occupation?.[language] ?? ''}
                            onChange={(e) =>
                              patch({
                                ...d,
                                patient: {
                                  ...d.patient,
                                  occupation: {
                                    ...d.patient.occupation,
                                    [language]: e.target.value,
                                  },
                                },
                              })
                            }
                          />
                          {(['height_cm', 'weight_kg'] as const).map((key) => (
                            <TextField
                              key={key}
                              label={key === 'height_cm' ? 'Height (cm)' : 'Weight (kg)'}
                              type="number"
                              min={0.01}
                              max={key === 'height_cm' ? 400 : 2000}
                              step={0.01}
                              value={d.patient[key] ?? ''}
                              onChange={(e) =>
                                patch({
                                  ...d,
                                  patient: {
                                    ...d.patient,
                                    [key]: e.target.value === '' ? undefined : Number(e.target.value),
                                  },
                                })
                              }
                            />
                          ))}
                        </div>
                      ) : (
                        <CaseFields
                          document={d}
                          onChange={patch}
                          section={tab}
                          language={language}
                          readOnly={!editable}
                        />
                      )}
                    </fieldset>
                  </div> : <div className={styles.review}>
                    <dl className={styles.summary}>
                      <div><dt>Scenario</dt><dd>{d.title || 'Untitled'} · {row.code}</dd></div>
                      <div><dt>Clinical specialty</dt><dd>{d.specialty || 'Choose a specialty'}</dd></div>
                      <div><dt>Patient</dt><dd>{d.patient.name || 'Not entered'}</dd></div>
                    </dl>
                    {!published && row.submitted_revision === row.revision && !dirty
                      ? <Notice tone="info" title="Awaiting independent review">
                          The submitted revision is ready for a different tenant reviewer.
                        </Notice>
                      : null}
                    {!published && editable ? <div className={styles.actions}>
                      <Button variant="ghost" disabled={busy || dirty} onClick={() => void validate()}>
                        Check completeness
                      </Button>
                      <Button disabled={busy || dirty || !row.specialty_id ||
                        row.submitted_revision === row.revision}
                        onClick={() => void submit()}>
                        Submit for review
                      </Button>
                    </div> : null}
                    {dirty ? <p className="pms-meta">Save your changes before checking completeness or submitting.</p> : null}
                  </div>}
                  <div className={styles.actions}>
                    {step !== 'patient' ? <Button variant="ghost" disabled={busy} onClick={() => setStep(step === 'review' ? 'case' : 'patient')}>
                      Previous
                    </Button> : null}
                    {step !== 'review' ? <Button disabled={busy} onClick={() => setStep(step === 'patient' ? 'case' : 'review')}>
                      Continue
                    </Button> : null}
                  </div>
                </div>
              </CardBody>
            </Card>
          ) : null}
          {validation ? (
            <Notice
              tone={validation.publishable ? 'success' : 'warning'}
              title={validation.publishable ? 'Required fields complete' : 'Complete the following fields'}
            >
              <ul>
                {validation.errors.map((e, i) => (
                  <li key={i}>
                    {e.path.join('.')}: {e.message}
                  </li>
                ))}
                {validation.warnings.map((e, i) => (
                  <li key={'w' + i}>{e.message}</li>
                ))}
              </ul>
            </Notice>
          ) : null}
          {canReview && row && !published && !row.is_archived && [4, 5].includes(row.schema_version) && step === 'review' ? (
            <Card>
              <CardBody>
                <fieldset disabled={busy || dirty || row.submitted_revision !== row.revision}
                  className={`pms-console__tenant-fieldset ${styles.reviewFields}`}>
                  <legend>Educator review & publication</legend>
                  <p className="pms-meta">
                    A different reviewer records a language review, then publishes the submitted revision.
                    Both English and Hindi must be reviewed for device sessions.
                  </p>
                  <TextField
                    label="Educator name"
                    maxLength={100}
                    value={educator}
                    onChange={(e) => {
                      setEducator(e.target.value);
                      publishKey.current = crypto.randomUUID();
                    }}
                  />
                  <FormTextArea
                    label="Review statement"
                    minLength={20}
                    maxLength={1000}
                    value={statement}
                    onChange={(e) => {
                      setStatement(e.target.value);
                      publishKey.current = crypto.randomUUID();
                    }}
                  />
                  <div className="pms-console__tenant-actions">
                    <Button variant="ghost" onClick={() => void validate()}>Check publication readiness</Button>
                    <Button variant="ghost" onClick={() => void approve()}>
                      Record {languages.find((item) => item.code === language)?.name ?? language} review
                    </Button>
                    <Button disabled={!validation?.publishable || validation.revision !== row.revision}
                      onClick={() => setConfirm('publish')}>
                      Publish version
                    </Button>
                  </div>
                </fieldset>
              </CardBody>
            </Card>
          ) : null}
          {editable ? <div className={styles.saveBar} aria-label="Draft actions">
            <span role="status">{busy ? 'Working…' : dirty ? 'Unsaved changes' : 'All changes saved'}</span>
            <Button disabled={!dirty || busy} loading={busy} onClick={() => void save()}>Save draft</Button>
          </div> : null}
        </>
      )}
      <ConfirmDialog
        open={!!confirm}
        title={
          confirm === 'publish'
            ? 'Publish this reviewed revision?'
            : confirm === 'discard'
              ? 'Discard unsaved edits?'
              : confirm === 'retire'
                ? 'Retire this published version?'
                : row?.is_archived
                  ? 'Restore this draft?'
                  : 'Archive this draft?'
        }
        confirmLabel={confirm === 'publish' ? 'Publish' : 'Confirm'}
        tone={confirm === 'publish' ? 'default' : 'danger'}
        busy={busy}
        error={error}
        onCancel={() => setConfirm(undefined)}
        onConfirm={() => {
          if (confirm === 'publish') void approve(true);
          else if (confirm === 'discard') {
            setRow(undefined);
            setDirty(false);
            setConfirm(undefined);
          } else void changeState();
        }}
      >
        Published versions and historical sessions are retained. Changes apply only to this tenant.
      </ConfirmDialog>
    </div>
  );
}
