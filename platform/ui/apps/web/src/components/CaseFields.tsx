'use client';
import { Button, Card, CardBody, Select, TextField } from '@pms/ui';
import { FormTextArea } from './FormTextArea';
import { PatientBackgroundFields } from './PatientBackgroundFields';
import {
  HISTORY_FIELDS,
  VITALS,
  nextEntryId,
  type CaseDocument,
  type Localized,
} from '@/lib/patient-catalog';
const label = (value: string) => value.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());
const PRESENTATION_PLACEHOLDERS = {
  chief_complaint: 'e.g. Cough and shortness of breath',
  onset: 'e.g. Started gradually three days ago',
  duration: 'e.g. Present throughout the day for three days',
  severity: 'e.g. Moderate; interferes with daily activities',
};
function translated(current: Localized | undefined, language: string, value: string): Localized | undefined {
  const next = { ...current };
  if (value) next[language] = value;
  else delete next[language];
  return Object.keys(next).length ? next : undefined;
}
export function CaseFields({
  document: d,
  onChange,
  section,
  language,
  readOnly = false,
}: {
  document: CaseDocument;
  onChange: (d: CaseDocument) => void;
  section: string;
  language: string;
  readOnly?: boolean;
}) {
  const set = <K extends keyof CaseDocument>(key: K, value: CaseDocument[K]) =>
    onChange({ ...d, [key]: value });
  const local = (key: keyof CaseDocument['presentation']) =>
    typeof d.presentation[key] === 'object' ? (d.presentation[key] as Localized) : undefined;
  if (section === 'background')
    return <PatientBackgroundFields document={d} onChange={onChange} language={language} readOnly={readOnly} />;
  if (section === 'presentation')
    return (
      <>
        <div className="pms-console__tenant-form-grid">
          {(['chief_complaint', 'onset', 'duration', 'severity'] as const).map((key) => (
            <FormTextArea
              key={key}
              label={label(key) + ' (' + language + ')'}
              placeholder={PRESENTATION_PLACEHOLDERS[key]}
              maxLength={key === 'chief_complaint' ? 150 : 100}
              value={local(key)?.[language] ?? ''}
              onChange={(e) =>
                set('presentation', {
                  ...d.presentation,
                  [key]: translated(local(key), language, e.target.value),
                })
              }
            />
          ))}
        </div>
        <fieldset className="pms-console__tenant-fieldset">
          <legend>Symptoms</legend>
          {d.presentation.symptoms.map((symptom, index) => (
            <Card key={index}>
              <CardBody>

                <FormTextArea
                  label={'Symptom description (' + language + ')'}
                  placeholder="e.g. Dry cough that gets worse at night"
                  maxLength={600}
                  value={symptom.description?.[language] ?? ''}
                  onChange={(e) =>
                    set('presentation', {
                      ...d.presentation,
                      symptoms: d.presentation.symptoms.map((s, i) =>
                        i === index
                          ? {
                              ...s,
                              description: translated(s.description, language, e.target.value),
                            }
                          : s,
                      ),
                    })
                  }
                />

                <Button
                  type="button"
                  variant="ghost"
                  onClick={() =>
                    set('presentation', {
                      ...d.presentation,
                      symptoms: d.presentation.symptoms.filter((_, i) => i !== index),
                    })
                  }
                >
                  Remove symptom
                </Button>
              </CardBody>
            </Card>
          ))}
          <Button
            type="button"
            variant="ghost"
            disabled={d.presentation.symptoms.length >= 24}
            onClick={() =>
              set('presentation', {
                ...d.presentation,
                symptoms: [
                  ...d.presentation.symptoms,
                  {
                    id: nextEntryId('symptom', d.presentation.symptoms),
                  },
                ],
              })
            }
          >
            Add symptom
          </Button>
        </fieldset>
      </>
    );
  if (section === 'history')
    return (
      <>
        {HISTORY_FIELDS.map((key) => {
          const history = d.history[key] ?? {
            knowledge: 'unknown' as const,
            entries: [],
          };
          const update = (value: typeof history) => set('history', { ...d.history, [key]: value });
          return (
            <fieldset className="pms-console__tenant-fieldset" key={key}>
              <legend>{label(key)}</legend>
              <div className="pms-console__tenant-form-grid">
                <Select
                  label={label(key) + ' status'}
                  value={history.knowledge}
                  options={[
                    { value: 'unknown', label: 'Unknown' },
                    { value: 'none', label: 'None' },
                    { value: 'present', label: 'Present' },
                  ]}
                  onChange={(v) =>
                    update({
                      ...history,
                      knowledge: v as typeof history.knowledge,
                      entries: v === 'present' ? history.entries : [],
                    })
                  }
                />

              </div>
              {history.entries.map((entry, index) => (
                <div key={entry.id} className="pms-console__tenant-form-grid">
                  <FormTextArea
                    label={label(key) + ' entry ' + (index + 1) + ' (' + language + ')'}
                    maxLength={600}
                    value={entry.text[language] ?? ''}
                    onChange={(e) =>
                      update({
                        ...history,
                        entries: history.entries.map((x, i) =>
                          i === index
                            ? {
                                ...x,
                                text: translated(x.text, language, e.target.value) ?? {},
                              }
                            : x,
                        ),
                      })
                    }
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() =>
                      update({
                        ...history,
                        entries: history.entries.filter((_, i) => i !== index),
                      })
                    }
                  >
                    Remove entry
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                variant="ghost"
                disabled={history.entries.length >= 16}
                onClick={() =>
                  update({
                    ...history,
                    knowledge: 'present',
                    entries: [...history.entries, { id: nextEntryId('entry', history.entries), text: {} }],
                  })
                }
              >
                Add {label(key).toLowerCase()} entry
              </Button>
            </fieldset>
          );
        })}
      </>
    );
  if (section === 'vitals')
    return (
      <>
        <div className="pms-console__tenant-form-grid">
          {VITALS.map(([key, title, max]) => (
            <TextField
              key={key}
              label={title}
              type="number"
              min={0}
              max={max}
              step={key === 'temperature_c' ? 0.1 : 1}
              value={d.vitals[key] ?? ''}
              onChange={(e) => {
                const v = { ...d.vitals };
                if (e.target.value === '') delete v[key];
                else v[key] = Number(e.target.value);
                set('vitals', v);
              }}
            />
          ))}
        </div>

      </>
    );
  return null;
}
