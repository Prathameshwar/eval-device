'use client';
import { useId } from 'react';
import { Button, Checkbox, PlusIcon } from '@pms/ui';
import { FormTextArea } from './FormTextArea';
import { BACKGROUND_FIELDS, nextEntryId, type BackgroundEntry, type CaseDocument } from '@/lib/patient-catalog';
import styles from './PatientBackgroundFields.module.css';

const guidance = {
  food_drink: 'Usual meals, drinks and eating habits.',
  sleep_activity: 'Sleep patterns, exercise and daily routines.',
  work_home: 'Work, household and everyday responsibilities.',
  personality: 'Interests, hobbies and how the patient relates to others.',
  additional: 'Education and other everyday facts relevant to this patient.',
};
function translate(current: Record<string, string>, language: string, value: string) {
  const next = { ...current };
  if (value) next[language] = value;
  else delete next[language];
  return next;
}

export function PatientBackgroundFields({ document: d, onChange, language, readOnly = false }: {
  document: CaseDocument; onChange: (document: CaseDocument) => void; language: string; readOnly?: boolean;
}) {
  const headingId = useId();
  function update(value: BackgroundEntry) {
    const entries = (d.background ?? []).filter((entry) => entry.id !== value.id);
    if (Object.keys(value.text).length || value.choices.length) entries.push(value);
    onChange({ ...d, version: 5, background: entries });
  }
  return <div className={styles.background}>
    <div className={styles.intro}>
      <p>Everyday details give the fictional patient a consistent personal story.</p>
      <span>Blank details remain unspecified. Keep clinical events and treatments in History.</span>
    </div>
    <div className={styles.grid}>
      {BACKGROUND_FIELDS.map(([id, title]) => {
        const entry = d.background?.find((value) => value.id === id)
          ?? { id, text: {}, allow_variation: false, choices: [] };
        return <section className={styles.category} key={id} aria-labelledby={headingId + id}>
          <div className={styles.categoryHeading}>
            <h3 id={headingId + id}>{title}</h3>
            <span className={styles.status}>{Object.keys(entry.text).length ? 'Supplied' : 'Optional'}</span>
          </div>
          {readOnly ? <>
            <p className={styles.reading}>{entry.text[language] || (Object.keys(entry.text).length ? 'Translation missing' : 'Not specified')}</p>
            {entry.choices.length ? <div className={styles.approvedReading}>
              <h4>Approved everyday details</h4>
              <p className={styles.guidance}>{entry.allow_variation ? 'Enabled for conversation' : 'Not enabled for conversation'}</p>
              <ul>{entry.choices.map((choice) => <li key={choice.id}>{choice.text[language] || 'Translation missing'}</li>)}</ul>
            </div> : null}
          </> : <>
            <p className={styles.guidance}>{guidance[id]}</p>
            <FormTextArea label={title + ' background (' + language + ')'} maxLength={240} rows={3}
              value={entry.text[language] ?? ''} placeholder="Keep the background brief and specific."
              onChange={(event) => update({ ...entry, text: translate(entry.text, language, event.target.value) })} />
            <details className={styles.details}>
              <summary><span>Approved everyday details</span><span className={styles.detailCount}>{entry.choices.length}/3</span></summary>
              <div className={styles.detailBody}>
                <p className={styles.guidance}>Add up to three possibilities. When enabled, one stays consistent throughout an interview. Keep illness triggers and clinical findings in History.</p>
                {entry.choices.map((choice, index) => <div className={styles.choice} key={choice.id}>
                  <FormTextArea label={'Everyday detail ' + (index + 1) + ' (' + language + ')'}
                    aria-label={title + ' everyday detail ' + (index + 1) + ' (' + language + ')'}
                    maxLength={160} rows={2} value={choice.text[language] ?? ''}
                    onChange={(event) => update({ ...entry, choices: entry.choices.map((value) => value.id === choice.id
                      ? { ...value, text: translate(value.text, language, event.target.value) } : value) })} />
                  <Button type="button" variant="ghost" aria-label={'Remove ' + title.toLowerCase() + ' detail ' + (index + 1)}
                    onClick={() => {
                      const choices = entry.choices.filter((value) => value.id !== choice.id);
                      update({ ...entry, choices, allow_variation: choices.length > 0 && entry.allow_variation });
                    }}>Remove detail</Button>
                </div>)}
                <div className={styles.detailActions}>
                  <Button type="button" variant="ghost" aria-label={'Add ' + title.toLowerCase() + ' detail'}
                    disabled={entry.choices.length >= 3 || !Object.keys(entry.text).length}
                    onClick={() => update({ ...entry, choices: [...entry.choices, {
                      id: nextEntryId('choice', entry.choices), text: {},
                    }] })}><PlusIcon size={16} />Add detail</Button>
                  {!Object.keys(entry.text).length ? <span>Add a background before adding details.</span> : null}
                </div>
                <div className={styles.variation}>
                  <Checkbox checked={entry.allow_variation} disabled={!entry.choices.length}
                    aria-label={'Allow approved everyday details for ' + title.toLowerCase()}
                    onChange={(event) => update({ ...entry, allow_variation: event.target.checked })}>
                    Use approved details in conversation
                  </Checkbox>
                </div>
              </div>
            </details>
          </>}
        </section>;
      })}
    </div>
    {!readOnly ? <section className={styles.preview} aria-label="Patient background preview">
      <h3>Patient background preview</h3>
      {(d.background ?? []).length ? <dl>
        {BACKGROUND_FIELDS.map(([id, title]) => {
          const entry = d.background?.find((value) => value.id === id);
          return entry ? <div key={id}><dt>{title}</dt><dd>{entry.text[language] || 'Translation missing'}
            {entry.allow_variation ? <span className={styles.previewNote}>Approved everyday details enabled</span> : null}
          </dd></div> : null;
        })}
      </dl> : <p>Your supplied background will appear here. Blank details remain unspecified.</p>}
    </section> : null}
  </div>;
}
