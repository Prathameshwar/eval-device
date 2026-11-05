'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import {
  Button, ConfirmDialog, CopyIcon, DataTable, EditIcon, ErrorState,
  EyeIcon, FilterBar, Menu, Notice, PageHeader, Pager, PlusIcon, Select, TableSearch,
  TrashIcon, useFormatters, useGranted, useToast,
  type Column, type MenuItem, type Sort,
} from '@pms/ui';
import {
  MODEL_PAGE_LIMITS,
  type ModelDefinition, type ModelQuery, type ModelCategory,
} from '@/lib/model-directory';

import { ModelEditor } from './ModelEditor';
import type { ModelDraft } from '@/lib/model-editor';
import { useModelDirectory } from './ModelDirectoryProvider';
import { ModelLifecycleBadge, ModelAdapterBadge } from './ModelStatusBadge';
import { PROVIDER_LABELS } from './provider-labels';

const SORT_OPTIONS = [
  { value: 'display_name:asc', label: 'Name A–Z' },
  { value: 'display_name:desc', label: 'Name Z–A' },
  { value: 'provider:asc', label: 'Provider A–Z' },
  { value: 'provider:desc', label: 'Provider Z–A' },
  { value: 'created_at:desc', label: 'Registered newest' },
  { value: 'created_at:asc', label: 'Registered oldest' },
];

const CATEGORY_OPTIONS: { value: ModelCategory; label: string }[] = [
  { value: 'text', label: 'Text Processing' },
  { value: 'conversation', label: 'Conversation' },
  { value: 'asr', label: 'Speech Recognition' },
  { value: 'tts', label: 'Text To Speech' },
  { value: 'vision', label: 'Computer Vision' },
  { value: 'video', label: 'Video Indexing' },
  { value: 'ocr', label: 'OCR' },
  { value: 'embedding', label: 'Embedding' },
  { value: 'reranking', label: 'Reranking' },
  { value: 'image_generation', label: 'Image Generation' },
  { value: 'video_generation', label: 'Video Generation' },
];

export function ModelList() {
  const { providers, query, setQuery, setPageIndex, savedModel, setSavedModel, page, loading, error: loadError, reload,
    listBookmark, save: saveRecord, retire: retireRecord, restore: restoreRecord } = useModelDirectory();
  const [retiring, setRetiring] = useState<ModelDefinition | null>(null);
  const [restoring, setRestoring] = useState<ModelDefinition | null>(null);
  const [editor, setEditor] = useState<{ model: ModelDefinition | null } | null>(null);
  const [actionError, setActionError] = useState<string>();
  const container = useRef<HTMLDivElement>(null);
  const granted = useGranted();
  const toast = useToast();
  const format = useFormatters();
  const [busy, setBusy] = useState(false);

  // Only the platform catalog can be written to. The tenant-facing read never sees retired rows.
  const canManage = granted('platform.settings.manage');
  const isAdmin = canManage || granted('platform.settings.read');
  const canRead = isAdmin || granted('org.configuration.read');

  const sort: readonly Sort[] = [{ key: query.sort_by, direction: query.sort_order }];

  function changeQuery(patch: Partial<ModelQuery>) {
    setQuery((current) => ({ ...current, ...patch }));
    setPageIndex(0);
  }

  function changeSort(next: readonly Sort[]) {
    const selected = next[0];
    if (!selected || !['display_name', 'provider', 'created_at'].includes(selected.key)) return;
    changeQuery({ sort_by: selected.key as ModelQuery['sort_by'], sort_order: selected.direction });
  }

  function openEditor(model: ModelDefinition | null = null) {
    if (!canManage || (model && model.lifecycle === 'retired')) return;
    setEditor({ model });
  }

  function focusList(id?: string) {
    requestAnimationFrame(() => {
      const button = id ? [...(container.current?.querySelectorAll<HTMLElement>('[data-model-view]') ?? [])]
        .find((element) => element.dataset.modelView === id) : undefined;
      (button ?? container.current?.querySelector<HTMLElement>('[role="region"]'))?.focus();
    });
  }

  function rememberList(id: string) {
    listBookmark.current = {
      id, tableTop: container.current?.querySelector('.pms-table-shell')?.scrollTop ?? 0,
      pageTop: container.current?.closest('.pms-main')?.scrollTop ?? 0,
    };
  }

  useEffect(() => {
    const bookmark = listBookmark.current;
    if (!bookmark) return;
    const frame = requestAnimationFrame(() => {
      const button = [...(container.current?.querySelectorAll<HTMLElement>('[data-model-view]') ?? [])]
        .find((element) => element.dataset.modelView === bookmark.id);
      (button ?? container.current?.querySelector<HTMLElement>('[role="region"]'))?.focus({ preventScroll: true });
      const table = container.current?.querySelector('.pms-table-shell');
      const main = container.current?.closest('.pms-main');
      if (table) table.scrollTop = bookmark.tableTop;
      if (main) main.scrollTop = bookmark.pageTop;
    });
    return () => cancelAnimationFrame(frame);
  }, [listBookmark]);

  async function save(draft: ModelDraft): Promise<string | undefined> {
    if (!editor) return 'Reopen the form to continue.';
    const result = await saveRecord(draft, editor.model);
    if (!result.model) return result.error;
    setEditor(null);
    focusList(result.model.id);
    return undefined;
  }

  async function copyId(row: ModelDefinition) {
    try {
      await navigator.clipboard.writeText(row.id);
      toast.success(`Copied the ID for ${row.display_name}.`, { title: 'Model ID copied' });
    } catch {
      toast.error('Open View to select and copy the model ID manually.', { title: 'Could not copy ID' });
    }
  }

  async function doRetire() {
    if (!canManage || !retiring || busy) return;
    setBusy(true);
    const error = await retireRecord(retiring);
    setBusy(false);
    if (error) { setActionError(error); return; }
    setRetiring(null);
    toast.success(`${retiring.display_name} was retired.`, { title: 'Model retired' });
    requestAnimationFrame(() => container.current?.querySelector<HTMLElement>('[role="region"]')?.focus());
  }

  async function doRestore() {
    if (!canManage || !restoring || busy) return;
    setBusy(true);
    const error = await restoreRecord(restoring);
    setBusy(false);
    if (error) { setActionError(error); return; }
    setRestoring(null);
    toast.success(`${restoring.display_name} was restored as deprecated.`, { title: 'Model restored' });
  }

  function menuItems(row: ModelDefinition): MenuItem[] {
    if (row.lifecycle === 'retired') {
      return [
        { id: 'copy', label: 'Copy ID', icon: <CopyIcon size={16} /> },
        { id: 'restore', label: 'Restore', icon: <EditIcon size={16} />, permission: 'platform.settings.manage' },
      ];
    }
    return [
      { id: 'edit', label: 'Edit', icon: <EditIcon size={16} />, permission: 'platform.settings.manage' },
      { id: 'copy', label: 'Copy ID', icon: <CopyIcon size={16} /> },
      { id: 'delete', label: 'Retire', icon: <TrashIcon size={16} />, destructive: true, permission: 'platform.settings.manage' },
    ];
  }

  const columns: Column<ModelDefinition>[] = [
    {
      key: 'name', header: 'Model Specification', type: 'custom', sortable: true, width: '35%',
      render: (row) => (
        <div className="pms-console__tenant-cell">
          <strong>{row.display_name}</strong>
          <span className="pms-meta">Key: <code>{row.model_key}</code></span>
        </div>
      ),
    },
    {
      key: 'provider', header: 'Provider', type: 'custom', sortable: true, width: '20%',
      render: (row) => <span>{PROVIDER_LABELS[row.provider] ?? row.provider.toUpperCase()}</span>,
    },
    {
      key: 'status', header: 'Status', type: 'custom', width: '25%',
      render: (row) => (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <ModelLifecycleBadge lifecycle={row.lifecycle} />
          <ModelAdapterBadge adapterStatus={row.adapter_status} />
        </div>
      ),
    },
    {
      key: 'actions', header: 'Actions', type: 'custom', align: 'end', width: '20%',
      render: (row) => (
        <div className="pms-console__tenant-actions">
          <Link className="pms-btn pms-btn--ghost" aria-label={`View ${row.display_name}`} data-model-view={row.id} href={`/models/${encodeURIComponent(row.id)}`} onClick={() => rememberList(row.id)}>
            <EyeIcon size={16} />View
          </Link>
          <Menu label={`Actions for ${row.display_name}`} items={menuItems(row)} onSelect={(action) => {
            if (action === 'copy') void copyId(row);
            if (action === 'edit') openEditor(row);
            if (action === 'delete' && canManage && row.lifecycle !== 'retired') { setActionError(undefined); setRetiring(row); }
            if (action === 'restore' && canManage && row.lifecycle === 'retired') { setActionError(undefined); setRestoring(row); }
          }} />
        </div>
      ),
    },
  ];

  const filtered = Boolean(query.q || query.provider !== undefined || query.category !== undefined || query.lifecycle !== 'active' || query.adapter_status !== undefined);
  const clearFilters = () => changeQuery({ q: '', provider: undefined, category: undefined, lifecycle: 'active', adapter_status: undefined });

  if (!canRead) {
    return <div className="pms-page"><ErrorState status={403} /></div>;
  }

  return (
    <div className="pms-page pms-console__tenant-page" ref={container}>
      <PageHeader overline="Console Settings" title="Model catalog" lede={isAdmin
        ? 'Register and manage the AI models available across the platform.'
        : 'Browse the AI models registered on the platform for use in your tenant.'}
        actions={canManage ? <Button onClick={() => openEditor()}><PlusIcon size={16} />Register model</Button> : undefined} />

      <div className="pms-console__tenant-directory">
        {savedModel ? (
          <Notice tone="success" title={savedModel.created ? 'Model registered' : 'Model details updated'}
            onDismiss={() => setSavedModel(null)} action={
              <Link className="pms-btn pms-btn--ghost" href={`/models/${encodeURIComponent(savedModel.id)}`} onClick={() => rememberList(savedModel.id)}>
                <EyeIcon size={16} />View model
              </Link>
            }>
            {savedModel.name} was {savedModel.created ? 'registered' : 'updated'}.
            {!page.items.some((row) => row.id === savedModel.id) ? ' It is outside the current filters or page. Use View model to see details.' : ''}
          </Notice>
        ) : null}

        {!isAdmin ? <Notice tone="info">This catalog is read only in your tenant. Contact a platform administrator to register or change models.</Notice> : null}

        <FilterBar>
          <TableSearch value={query.q} onChange={(q) => changeQuery({ q })} label="Search models" placeholder="Search models by name or key…" minLength={1} maxLength={128} />

          <Select label="Provider" value={query.provider === undefined ? 'all' : query.provider} options={[
            { value: 'all', label: 'All providers' },
            ...(providers.length
              ? providers.map((provider) => ({ value: provider.id, label: PROVIDER_LABELS[provider.id] ?? provider.id.toUpperCase() }))
              : Object.entries(PROVIDER_LABELS).map(([value, label]) => ({ value, label }))),
          ]} onChange={(value) => changeQuery({ provider: value === 'all' ? undefined : value })} />

          <Select label="Category" value={query.category === undefined ? 'all' : query.category} options={[
            { value: 'all', label: 'All categories' },
            ...CATEGORY_OPTIONS,
          ]} onChange={(value) => changeQuery({ category: value === 'all' ? undefined : value as ModelCategory })} />

          <Select label="Lifecycle" value={query.lifecycle === undefined ? 'all' : String(query.lifecycle)} options={[
            { value: 'active', label: 'Active models' },
            { value: 'deprecated', label: 'Deprecated models' },
            /* Retired definitions only exist behind the platform catalog; the tenant-facing read can never return them. */
            ...(isAdmin ? [{ value: 'retired', label: 'Retired models' }, { value: 'all', label: 'All models' }] : []),
          ]} onChange={(value) => changeQuery({ lifecycle: value === 'all' ? undefined : value as ModelDefinition['lifecycle'] })} />

          <Select label="Sort models" value={`${query.sort_by}:${query.sort_order}`} options={SORT_OPTIONS} onChange={(value) => {
            const [key, direction] = value.split(':');
            if (key) changeSort([{ key, direction: direction as Sort['direction'] }]);
          }} />
        </FilterBar>

        <DataTable caption="Models" rows={page.items} loading={loading} error={loadError ? 500 : null} errorDetail={loadError} onRetry={reload} columns={columns} rowId={(row) => row.id} rowLabel={(row) => row.display_name}
          sort={sort} onSortChange={changeSort} filtered={filtered}
          emptyTitle={filtered ? 'No matching models' : 'No models registered yet'}
          emptyBody={filtered ? 'Try another search query or clear the filters.' : 'AI models will appear here once registered.'}
          onClearFilters={clearFilters}
          emptyAction={canManage ? <Button onClick={() => openEditor()}>Register model</Button> : undefined} />

        <div className="pms-console__tenant-footer">
          <p className="pms-meta" role="status">{format.quantity(String(page.total), { precision: 0 })} {page.total === 1 ? 'model' : 'models'}</p>
          <Pager count={page.items.length} from={page.from} limit={query.limit} limitOptions={MODEL_PAGE_LIMITS} noun="model"
            hasPrevious={page.page > 0} hasNext={page.has_more} onPrevious={() => setPageIndex(page.page - 1)} onNext={() => setPageIndex(page.page + 1)}
            onLimitChange={(limit) => changeQuery({ limit })} />
        </div>
      </div>

      {editor && canManage ? (
        <ModelEditor model={editor.model} providers={providers} onSave={save} onClose={() => {
          const id = editor.model?.id;
          setEditor(null);
          if (id) focusList(id);
        }} />
      ) : null}

      <ConfirmDialog open={Boolean(retiring)} title={`Retire ${retiring?.display_name ?? 'model'}?`} confirmLabel="Retire model" tone="danger"
        busy={busy} error={actionError} onConfirm={doRetire} onCancel={() => setRetiring(null)}>
        This marks the model definition as retired. It can no longer be selected for new configuration profiles;
        existing profiles that already reference it are unaffected. A model with an active connection cannot be retired.
      </ConfirmDialog>

      <ConfirmDialog open={Boolean(restoring)} title={`Restore ${restoring?.display_name ?? 'model'}?`} confirmLabel="Restore model" tone="default"
        busy={busy} error={actionError} onConfirm={doRestore} onCancel={() => setRestoring(null)}>
        This returns the model to the catalog as deprecated. It will not be selectable for new configuration until it is made active again.
      </ConfirmDialog>
    </div>
  );
}
