'use client';
import { BackNavigation } from './BackNavigation';
import { callAction } from '@/lib/call-action';
import { useEffect, useState } from 'react';
import {
  Button,
  Checkbox,
  ConfirmDialog,
  Notice,
  PageHeader,
  Select,
  TextField,
} from '@pms/ui';
import {
  readPlatformOptions,
  savePlatformOptions,
  type PlatformOptions as Options,
} from '@/lib/platform-options-actions';
import styles from './PlatformOptions.module.css';
export function PlatformOptions({ canManage }: { canManage: boolean }) {
  const [options, setOptions] = useState<Options>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [reload, setReload] = useState(0);
  const [originalMaintenance, setOriginalMaintenance] = useState(false);
  useEffect(() => {
    let active = true;
    setError(undefined);
    void callAction(() => readPlatformOptions()).then((r) => {
      if (!active) return;
      if (r.error !== undefined) setError(r.error);
      else {
        setOptions(r.value);
        setOriginalMaintenance(r.value.maintenance_mode);
      }
    });
    return () => {
      active = false;
    };
  }, [reload]);
  function patch(values: Partial<Options>) {
    setOptions((o) => (o ? { ...o, ...values } : o));
    setSaved(false);
  }
  async function save() {
    if (!options || !canManage || busy) return;
    setBusy(true);
    setError(undefined);
    const result = await callAction(() => savePlatformOptions(options));
    setBusy(false);
    setConfirm(false);
    if (result.error !== undefined) {
      setError(result.error);
      return;
    }
    setOptions(result.value);
    setOriginalMaintenance(result.value.maintenance_mode);
    setSaved(true);
  }
  function submit() {
    if (!options || !canManage || busy) return;
    const languages = options.languages;
    if (!languages.some((l) => l.code === 'en' && l.is_active !== false)) {
      setError('Keep English (en) active as the default device language.');
      return;
    }
    if (
      !options.display_name.trim() ||
      !languages.length ||
      new Set(languages.map((l) => l.code)).size !== languages.length ||
      languages.some(
        (l) =>
          !l.name.trim() ||
          !/^[a-z]{2,3}(-[A-Z]{2})?$/.test(l.code) ||
          !/^[a-z]{2,3}-[A-Z]{2}$/.test(l.speech_locale ?? ''),
      )
    ) {
      setError(
        'Complete the display name and each language. Use unique language codes such as en and speech locales such as en-IN.',
      );
      return;
    }
    if (options.maintenance_mode !== originalMaintenance) setConfirm(true);
    else void save();
  }
  return (
    <div className={`pms-page ${styles.page}`}>
      <BackNavigation href="/settings" label="Back to settings" />
      <PageHeader overline="Settings" title="Platform options"
        lede="Manage platform identity, access, cloud providers and device languages." />
      {error && <Notice tone="danger" title="Unable to update options" action={
        <Button variant="ghost" disabled={busy} onClick={() => setReload(x => x + 1)}>Reload</Button>
      }>{error}</Notice>}
      {saved && <Notice tone="success" title="Options saved">The platform options have been updated.</Notice>}
      {!options ? (!error && <div className={styles.loading} role="status">Loading platform options…</div>) : (
        <form className={styles.form} onSubmit={event => { event.preventDefault(); submit(); }}>
          {!canManage && <Notice tone="info">You have read-only access to platform options.</Notice>}
          <fieldset className={styles.controls} disabled={!canManage || busy} aria-label="Platform settings">
            <div className={styles.overview}>
              <section className={styles.section} aria-labelledby="platform-general-heading">
                <header className={styles.sectionHeader}>
                  <div><h2 id="platform-general-heading">General settings</h2><p>Set the platform name and how new accounts register.</p></div>
                </header>
                <div className={styles.generalFields}>
                  <TextField label="Platform display name" required maxLength={256} value={options.display_name}
                    onChange={event => patch({ display_name: event.target.value })} />
                  <Select label="Registration" options={[
                    { value: 'self_service', label: 'Self service' },
                    { value: 'invite_only', label: 'Invitation only' },
                  ]} value={options.registration_mode}
                    onChange={value => patch({ registration_mode: value as Options['registration_mode'] })} />
                </div>
              </section>
              <section className={styles.section} aria-labelledby="platform-maintenance-heading">
                <header className={styles.sectionHeader}>
                  <div><h2 id="platform-maintenance-heading">Maintenance</h2><p>Control availability while the platform is being maintained.</p></div>
                </header>
                <div className={styles.maintenance}>
                  <Checkbox checked={options.maintenance_mode} aria-describedby="maintenance-description"
                    onChange={event => patch({ maintenance_mode: event.target.checked })}>Maintenance mode</Checkbox>
                  <p id="maintenance-description">Pauses new processing and configuration writes when enabled.</p>
                </div>
              </section>
            </div>
            <section className={styles.section} aria-labelledby="platform-providers-heading">
              <header className={styles.sectionHeader}>
                <div><h2 id="platform-providers-heading">Cloud providers</h2><p>Choose which providers are available for cloud processing.</p></div>
              </header>
              <div className={styles.providers}>
                {[{ id: 'aws', name: 'Amazon Web Services', label: 'AWS' }, { id: 'azure', name: 'Microsoft Azure', label: 'Azure' }].map(provider => (
                  <div className={styles.provider} key={provider.id} data-enabled={options.enabled_providers.includes(provider.id)}>
                    <Checkbox checked={options.enabled_providers.includes(provider.id)}
                      onChange={event => patch({ enabled_providers: event.target.checked
                        ? [...options.enabled_providers, provider.id]
                        : options.enabled_providers.filter(value => value !== provider.id) })}>
                      <span className={styles.providerName}>{provider.label}</span>
                      <span className={styles.providerDescription}>{provider.name}</span>
                    </Checkbox>
                  </div>
                ))}
              </div>
            </section>
            <section className={styles.section} aria-labelledby="platform-languages-heading">
              <header className={styles.sectionHeader}>
                <div><h2 id="platform-languages-heading">Language options <span className={styles.count}>{options.languages.length}</span></h2>
                  <p>Manage the languages available to devices. Keep English active as the default.</p></div>
                {canManage && <Button type="button" variant="ghost" disabled={options.languages.length >= 100}
                  onClick={() => patch({ languages: [...options.languages, { code: '', name: '', speech_locale: '', is_active: true }] })}>
                  Add language option
                </Button>}
              </header>
              <div className={styles.languageList}>
                {options.languages.map((language, index) => (
                  <fieldset className={styles.language} key={index} aria-label={`Language ${index + 1}`}>
                    <div className={styles.languageHeader}>
                      <h3>{language.name.trim() || 'New language'}</h3>
                      {language.code === 'en' && <span className={styles.defaultBadge}>Default</span>}
                    </div>
                    <div className={styles.languageFields}>
                      {(['name', 'code', 'speech_locale'] as const).map(key => (
                        <TextField key={key} label={{ code: 'Language code', name: 'Language name', speech_locale: 'Speech locale' }[key]}
                          hint={{ code: 'For example, en or hi', name: 'Display name on devices', speech_locale: 'For example, en-IN or hi-IN' }[key]}
                          required maxLength={80} value={language[key] ?? ''}
                          onChange={event => patch({ languages: options.languages.map((item, i) => i === index ? { ...item, [key]: event.target.value } : item) })} />
                      ))}
                    </div>
                    <div className={styles.languageActions}>
                      <Checkbox checked={language.is_active ?? true}
                        onChange={event => patch({ languages: options.languages.map((item, i) => i === index ? { ...item, is_active: event.target.checked } : item) })}>
                        Active language
                      </Checkbox>
                      {canManage && <Button type="button" variant="ghost" disabled={options.languages.length <= 1}
                        aria-label={`Remove language ${language.code || index + 1}`}
                        onClick={() => patch({ languages: options.languages.filter((_, i) => i !== index) })}>Remove language</Button>}
                    </div>
                  </fieldset>
                ))}
              </div>
              <p className={styles.languageNote}>Conversation support requires an installed language pack and complete case translations.</p>
            </section>
          </fieldset>
          {canManage && <footer className={styles.saveBar}>
            <p>Changes apply across the platform when saved.</p>
            <Button type="submit" loading={busy} disabled={busy}>Save options</Button>
          </footer>}
        </form>
      )}
      <ConfirmDialog open={confirm} busy={busy}
        title={options?.maintenance_mode ? 'Enable maintenance mode?' : 'Disable maintenance mode?'}
        confirmLabel="Save options" onCancel={() => setConfirm(false)} onConfirm={() => void save()}>
        This changes whether new processing and configuration writes are available across the platform.
      </ConfirmDialog>
    </div>
  );
}
