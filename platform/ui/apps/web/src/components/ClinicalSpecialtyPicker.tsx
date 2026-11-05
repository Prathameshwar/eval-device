'use client';
import { useRef, useState } from 'react';
import { Button, Notice, Select, TextField } from '@pms/ui';
import { callAction } from '@/lib/call-action';
import { saveCatalog } from '@/lib/catalog-actions';
import styles from './ClinicalSpecialtyPicker.module.css';

export type SpecialtyOption = { id: string; code: string; name?: string; is_active: boolean };

function codeFor(name: string) {
  const slug = name.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '').slice(0, 40);
  return /^[a-z]/.test(slug) ? slug : `specialty_${slug.slice(0, 30)}`;
}

export function ClinicalSpecialtyPicker({ value, options, onChange, onCreated, canCreate, disabled = false, selectedLabel }: {
  value: string;
  options: SpecialtyOption[];
  onChange: (value: string) => void;
  onCreated: (option: SpecialtyOption) => void;
  canCreate: boolean;
  disabled?: boolean;
  selectedLabel?: string;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const details = useRef<HTMLDetailsElement>(null);

  async function create() {
    if (!name.trim() || !description.trim()) {
      setError('Enter a name and description for the specialty.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    const result = await callAction(() => saveCatalog('categories', {
      id: '', code: codeFor(name), name: name.trim(), description: description.trim(),
      version: 0, is_active: true, sort_order: 100,
    }));
    setBusy(false);
    if (result.error !== undefined) { setError(result.error); return; }
    onCreated(result.value);
    onChange(result.value.id);
    setName('');
    setDescription('');
    setNotice(`${result.value.name || result.value.code} added and selected.`);
    if (details.current) details.current.open = false;
  }

  return <div className={styles.picker}>
    <Select label="Clinical specialty" value={value} disabled={disabled || busy}
      options={[{ value: '', label: 'Choose a specialty' },
        ...(value && !options.some((item) => item.id === value)
          ? [{ value, label: selectedLabel || 'Saved clinical specialty' }] : []),
        ...options.map((item) => ({ value: item.id, label: item.name || item.code }))]}
      onChange={onChange} />
    {notice ? <p className="pms-meta" role="status">{notice}</p> : null}
    {canCreate && !disabled ? <details ref={details} className={styles.create}>
      <summary>Add a clinical specialty</summary>
      <div className={styles.fields}>
        {error ? <Notice tone="danger" title="Specialty could not be added">{error}</Notice> : null}
        <TextField label="Specialty name" maxLength={120} value={name} disabled={busy}
          onChange={(event) => setName(event.target.value)} />
        <TextField label="Description" maxLength={600} value={description} disabled={busy}
          onChange={(event) => setDescription(event.target.value)} />
        <Button type="button" disabled={busy} loading={busy} onClick={() => void create()}>
          Add specialty
        </Button>
      </div>
    </details> : null}
  </div>;
}
