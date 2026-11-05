'use client';
import { BackNavigation } from './BackNavigation';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Button, CalendarIcon, Card, CardBody, CheckCircleIcon, ClockIcon,
  ConfirmDialog, CopyIcon, EditIcon, EmptyState, ErrorState,
  Menu, Notice, PageHeader, TrashIcon,
  useFormatters, useGranted, useToast, ActivityIcon, Badge,
} from '@pms/ui';
import { ModelIcon } from './icons-product';
import { ModelEditor } from './ModelEditor';
import { useModelDirectory } from './ModelDirectoryProvider';
import { ModelLifecycleBadge, ModelAdapterBadge } from './ModelStatusBadge';
import { PROVIDER_LABELS } from './provider-labels';
import type { ModelDefinition } from '@/lib/model-directory';

function DetailCard({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <Card>
      <header className="pms-card__header">
        <div className="pms-card__heading">
          <span className="pms-card__icon" aria-hidden="true">{icon}</span>
          <h2 className="pms-card__title">{title}</h2>
        </div>
      </header>
      <CardBody>{children}</CardBody>
    </Card>
  );
}

export function ModelDetails({ modelId, initialModel }: { modelId: string; initialModel?: ModelDefinition }) {
  const { rows, providers, save, retire, restore, savedModel, setSavedModel } = useModelDirectory();
  const model = rows.find((row) => row.id === modelId) ?? initialModel;
  const granted = useGranted();
  const format = useFormatters();
  const toast = useToast();

  const [editing, setEditing] = useState<ModelDefinition | null>(null);
  const [retiring, setRetiring] = useState<ModelDefinition | null>(null);
  const [restoring, setRestoring] = useState<ModelDefinition | null>(null);
  const [actionError, setActionError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  const root = useRef<HTMLDivElement>(null);
  const identifier = useRef<HTMLElement>(null);

  const canManage = granted('platform.settings.manage');
  const isAdmin = canManage || granted('platform.settings.read');
  const canRead = isAdmin || granted('org.configuration.read');

  useEffect(() => {
    const heading = root.current?.querySelector('h1');
    heading?.setAttribute('tabindex', '-1');
    heading?.focus({ preventScroll: true });
    const scroller = root.current?.closest('.pms-main');
    if (scroller) scroller.scrollTop = 0;
    setCopyFailed(false);
  }, [modelId]);

  const back = <BackNavigation href="/models?tab=catalog" label="Back to models" />;

  if (!canRead) return <div className="pms-page"><BackNavigation href="/home" label="Back to home" /><ErrorState status={403} /></div>;

  if (!model) return (
    <div className="pms-page pms-console__tenant-view" ref={root}>
      {back}
      <PageHeader title="Model not available" overline="Settings" />
      <EmptyState icon={<ModelIcon size={28} />} title="This model is unavailable"
        body="Return to the catalog to choose an available model definition." />
    </div>
  );

  const canEdit = canManage && model.lifecycle !== 'retired';

  async function copyId() {
    if (!model) return;
    try {
      await navigator.clipboard.writeText(model.id);
      setCopyFailed(false);
      toast.success('The full model definition ID is ready to paste.', { title: 'Model ID copied' });
    } catch {
      setCopyFailed(true);
      identifier.current?.focus();
      const selection = window.getSelection();
      if (identifier.current && selection) {
        const range = document.createRange();
        range.selectNodeContents(identifier.current);
        selection.removeAllRanges(); selection.addRange(range);
      }
    }
  }

  return (
    <div className="pms-page pms-console__tenant-view" ref={root}>
      {back}

      <PageHeader overline="Model specifications" title={model.display_name} lede="Core key identifiers, capabilities, publisher details and lifecycle status."
        actions={<>
          {canEdit ? <Button onClick={() => setEditing(model)}><EditIcon size={16} />Edit model</Button> : null}
          <Menu label="Model actions" items={[
            { id: 'copy', label: 'Copy ID', icon: <CopyIcon size={16} /> },
            ...(model.lifecycle === 'retired'
              ? [{ id: 'restore', label: 'Restore', icon: <EditIcon size={16} />, permission: 'platform.settings.manage' }]
              : [{ id: 'delete', label: 'Retire', icon: <TrashIcon size={16} />, destructive: true, permission: 'platform.settings.manage' }]),
          ]} onSelect={(action) => {
            if (action === 'copy') void copyId();
            if (action === 'delete' && canManage && model.lifecycle !== 'retired') { setActionError(undefined); setRetiring(model); }
            if (action === 'restore' && canManage && model.lifecycle === 'retired') { setActionError(undefined); setRestoring(model); }
          }} />
        </>} />

      <div className="pms-console__tenant-overview">
        {model.lifecycle === 'retired' ? (
          <Notice tone="warning" title="Retired model definition" live="off">
            This model definition is retired. It cannot be edited or selected for new configuration until it is restored.
          </Notice>
        ) : model.lifecycle === 'deprecated' ? (
          <Notice tone="warning" title="Deprecated model definition" live="off">
            This model definition is deprecated. It can still be edited, but should not be selected for new configuration profiles.
          </Notice>
        ) : null}

        {savedModel?.id === model.id ? (
          <Notice tone="success" title={savedModel.created ? 'Model registered' : 'Model details updated'} onDismiss={() => setSavedModel(null)}>
            The saved details are shown below.
          </Notice>
        ) : null}

        <Card className="pms-console__tenant-summary">
          <dl style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
            <div>
              <dt><CheckCircleIcon size={18} />Lifecycle</dt>
              <dd><ModelLifecycleBadge lifecycle={model.lifecycle} /></dd>
            </div>
            <div>
              <dt><ActivityIcon size={18} />Adapter</dt>
              <dd><ModelAdapterBadge adapterStatus={model.adapter_status} /></dd>
            </div>
            <div>
              <dt><CalendarIcon size={18} />Registered on</dt>
              <dd><time dateTime={model.created_at}>{format.date(model.created_at.slice(0, 10))}</time></dd>
            </div>
            <div>
              <dt><ClockIcon size={18} />Last updated</dt>
              <dd><time dateTime={model.updated_at}>{format.dateTime(model.updated_at)}</time></dd>
            </div>
          </dl>
        </Card>

        <div className="pms-console__tenant-view-grid">
          <div className="pms-console__tenant-view-main">
            <DetailCard title="About this model" icon={<ModelIcon size={20} />}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--pms-space-4)' }}>
                <div>
                  <h3 className="pms-label">Provider</h3>
                  <p>{PROVIDER_LABELS[model.provider] ?? model.provider.toUpperCase()}</p>
                </div>
                <div>
                  <h3 className="pms-label">Model Key</h3>
                  <p><code>{model.model_key}</code></p>
                </div>
                <div>
                  <h3 className="pms-label">Description</h3>
                  <p className="pms-console__tenant-description">{model.description || 'No description provided.'}</p>
                </div>
                <div>
                  <h3 className="pms-label">Capability categories</h3>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '4px' }}>
                    {model.categories.map((cat) => (
                      <Badge key={cat} tone="info">{cat.toUpperCase()}</Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <h3 className="pms-label">Operations</h3>
                  <p className="pms-hint">{model.operations.join(', ')}</p>
                </div>
              </div>
            </DetailCard>

            <DetailCard title="Publisher & Metadata" icon={<ActivityIcon size={20} />}>
              <dl className="pms-console__tenant-contact">
                <div>
                  <dt>Publisher</dt>
                  <dd>{model.publisher || 'Not configured'}</dd>
                </div>
                <div>
                  <dt>Model Family</dt>
                  <dd>{model.model_family || 'Not configured'}</dd>
                </div>
                <div>
                  <dt>Model Version</dt>
                  <dd>{model.model_version || 'Not configured'}</dd>
                </div>
              </dl>
            </DetailCard>
          </div>

          <DetailCard title="Record information" icon={<ClockIcon size={20} />}>
            <dl className="pms-console__tenant-record">
              <div>
                <dt>Model ID</dt>
                <dd>
                  <code ref={identifier} tabIndex={-1}>{model.id}</code>
                  <Button variant="ghost" onClick={() => void copyId()}><CopyIcon size={16} />Copy ID</Button>
                  {copyFailed ? <p role="alert" className="pms-hint">Clipboard access is unavailable. Select and copy the ID above.</p> : null}
                </dd>
              </div>
              <div>
                <dt>Record version</dt>
                <dd><code>v{model.version}</code></dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd><time dateTime={model.created_at}>{format.dateTime(model.created_at)}</time></dd>
              </div>
              <div>
                <dt>Last Updated</dt>
                <dd><time dateTime={model.updated_at}>{format.dateTime(model.updated_at)}</time></dd>
              </div>
            </dl>
          </DetailCard>
        </div>

        <div className="pms-console__tenant-view-footer"><span className="pms-meta">Saved model record.</span></div>
      </div>

      {editing && canEdit ? (
        <ModelEditor model={editing} providers={providers} onClose={() => setEditing(null)} onSave={async (draft) => {
          const result = await save(draft, editing);
          if (!result.model) return result.error;
          setEditing(null);
          return undefined;
        }} />
      ) : null}

      <ConfirmDialog open={Boolean(retiring) && canManage} title={`Retire ${model.display_name}?`} confirmLabel="Retire model" tone="danger"
        busy={busy} error={actionError} onCancel={() => setRetiring(null)} onConfirm={async () => {
          if (!retiring || busy) return;
          setBusy(true);
          const error = await retire(retiring);
          setBusy(false);
          if (error) { setActionError(error); return; }
          setRetiring(null);
          toast.success('This model is retired. Its details remain available.', { title: 'Model retired' });
        }}>
        This retires the model definition. It can no longer be selected for new configuration profiles.
        A model with an active connection cannot be retired.
      </ConfirmDialog>

      <ConfirmDialog open={Boolean(restoring) && canManage} title={`Restore ${model.display_name}?`} confirmLabel="Restore model" tone="default"
        busy={busy} error={actionError} onCancel={() => setRestoring(null)} onConfirm={async () => {
          if (!restoring || busy) return;
          setBusy(true);
          const error = await restore(restoring);
          setBusy(false);
          if (error) { setActionError(error); return; }
          setRestoring(null);
          toast.success('This model is restored as deprecated.', { title: 'Model restored' });
        }}>
        This returns the model to the catalog as deprecated. It will not be selectable for new configuration until it is made active again.
      </ConfirmDialog>
    </div>
  );
}
