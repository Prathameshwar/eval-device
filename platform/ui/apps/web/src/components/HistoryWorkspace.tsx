'use client';
import { BackNavigation } from './BackNavigation';
import { callAction } from '@/lib/call-action';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
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
  type Column,
} from '@pms/ui';
import {
  listHistory,
  readHistory,
  stopHistory,
  sessionRubric,
  saveFeedback,
  historyStats,
  listMedia,
  openMedia,
  type HistoryRow,
  type MediaItem,
} from '@/lib/history-actions';
import { useApiDirectory } from '@/lib/use-api-directory';
import { FormTextArea } from './FormTextArea';
const active = ['authorized', 'active', 'queued', 'awaiting_upload', 'awaiting_device', 'running'];
export function HistoryWorkspace({
  contextId,
  mode,
  canManage,
  canMedia,
  canStart = false,
  earlier = false,
  viewerId,
}: {
  contextId: string;
  mode: 'sessions' | 'reports' | 'recordings';
  canManage: boolean;
  canMedia: boolean;
  canStart?: boolean;
  earlier?: boolean;
  viewerId?: string;
}) {
  const kind = mode === 'recordings' ? 'runs' : 'sessions';
  const [view, setView] = useState<HistoryRow>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState('');
  const fetchPage = useCallback(
    (q: { limit: number; mine: boolean; kind: 'runs' | 'sessions' }, cursor?: string) =>
      callAction(() => listHistory(contextId, q, cursor)),
    [contextId],
  );
  const dir = useApiDirectory({ limit: 25, mine: false, kind }, fetchPage);
  const [stats, setStats] = useState<{
    sessions: number;
    hours_practiced: number;
    average_score: number | null;
    awaiting_review: number;
  }>();
  const [rubric, setRubric] = useState<{ id: string; description: string }[]>([]);
  const [scores, setScores] = useState<Record<string, string>>({});
  const [comments, setComments] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [media, setMedia] = useState<MediaItem[]>([]);
  const [play, setPlay] = useState<{
    url: string;
    type: string;
    until: number;
  }>();
  useEffect(() => {
    let live = true;
    if (mode === 'reports')
      void callAction(() => historyStats(contextId)).then((r) => {
        if (live) {
          if (r.error !== undefined) setError(r.error);
          else setStats(r.value);
        }
      });
    return () => {
      live = false;
    };
  }, [contextId, mode]);
  useEffect(() => {
    if (!play) return;
    const timer = setTimeout(() => setPlay(undefined), Math.max(0, play.until - Date.now()));
    return () => clearTimeout(timer);
  }, [play]);
  async function open(row: HistoryRow) {
    setBusy(true);
    setError(undefined);
    setPlay(undefined);
    setMedia([]);
    setRubric([]);
    const r = await callAction(() => readHistory(contextId, row.id, kind));
    if (r.error !== undefined) {
      setBusy(false);
      setError(r.error);
      return;
    }
    setView(r.value);
    setComments(r.value.feedback?.comments ?? '');
    setScores(r.value.feedback?.scores ?? {});
    if (kind === 'sessions' && canManage && viewerId && r.value.instructor_id === viewerId && !active.includes(r.value.status)) {
      const result = await callAction(() => sessionRubric(contextId, row.id));
      if (result.error !== undefined) setError(result.error);
      else {
        setRubric(result.value.items);
        setScores(
          Object.fromEntries(
            result.value.items.map((i) => [i.id, r.value.feedback?.scores[i.id] ?? 'not_observed']),
          ),
        );
      }
    }
    if (kind === 'runs' && canMedia && r.value.media_available && r.value.status === 'succeeded') {
      const result = await callAction(() => listMedia(contextId, row.id));
      if (result.error !== undefined) setError(result.error);
      else setMedia(result.value);
    }
    setBusy(false);
  }
  async function stop() {
    if (!view) return;
    setBusy(true);
    setError(undefined);
    const r = await callAction(() => stopHistory(contextId, view.id, kind));
    setBusy(false);
    if (r.error !== undefined) {
      setError(r.error);
      return;
    }
    setView(r.value);
    setConfirm(false);
    setNotice('Stop request recorded.');
    dir.reload();
  }
  async function feedback() {
    if (!view) return;
    setBusy(true);
    setError(undefined);
    const r = await callAction(() => saveFeedback(contextId, view, scores, comments));
    setBusy(false);
    if (r.error !== undefined) {
      setError(r.error);
      return;
    }
    setView(r.value);
    setNotice('Feedback saved.');
    dir.reload();
  }
  async function playback(item: MediaItem) {
    if (!view) return;
    setBusy(true);
    setError(undefined);
    const r = await callAction(() => openMedia(contextId, view.id, item.index));
    setBusy(false);
    if (r.error !== undefined) {
      setError(r.error);
      return;
    }
    setPlay({
      url: r.value.url,
      type: item.content_type,
      until: Date.now() + r.value.expires_in * 1000,
    });
  }
  const columns: Column<HistoryRow>[] = [
    {
      key: 'created',
      header: 'Created',
      type: 'custom',
      render: (r) => new Date(r.created_at).toLocaleString(),
    },
    {
      key: 'kind',
      header: kind === 'runs' ? 'Operation' : 'Session',
      type: 'custom',
      render: (r) => r.operation ?? r.id.slice(0, 8),
    },
    {
      key: 'status',
      header: 'Status',
      type: 'custom',
      render: (r) => r.status.replaceAll('_', ' '),
    },
    {
      key: 'review',
      header: kind === 'runs' ? 'Media' : 'Feedback',
      type: 'custom',
      render: (r) =>
        kind === 'runs'
          ? r.media_available
            ? 'Available'
            : 'Unavailable'
          : r.feedback
            ? 'Reviewed'
            : 'Pending',
    },
    {
      key: 'actions',
      header: 'Actions',
      type: 'custom',
      render: (r) => (
        <Button variant="ghost" disabled={busy} onClick={() => void open(r)}>
          View details
        </Button>
      ),
    },
  ];
  return (
    <div className="pms-page">
      {view ? <BackNavigation label={mode === 'reports' ? 'Back to reports' : mode === 'recordings' ? 'Back to recordings' : earlier ? 'Back to earlier sessions' : 'Back to sessions'}
        disabled={busy} onBack={() => { setView(undefined); setPlay(undefined); setError(undefined); }} />
        : <BackNavigation href={earlier ? '/sessions' : '/home'} label={earlier ? 'Back to sessions' : 'Back to home'} />}
      <PageHeader
        overline="Tenant history"
        title={
          mode === 'reports' ? 'Reports' : mode === 'recordings' ? 'Recordings & processing' : earlier ? (view ? 'Earlier session details' : 'Earlier sessions') : 'Sessions'
        }
        lede={
          mode === 'recordings'
            ? 'Inspect processing results and available recordings within your access scope.'
            : earlier ? 'Review older training sessions, their status and educator feedback.' : 'Review training sessions, their status and educator feedback.'
        }
        actions={
          !view && mode === 'sessions' && canStart ? (
            <Link className="pms-btn" href="/sessions/new">Start session</Link>
          ) : !view ? (
            <Button variant="ghost" onClick={dir.reload}>
              Refresh
            </Button>
          ) : undefined
        }
      />
      {error || dir.error ? (
        <Notice
          tone="danger"
          title="Request failed"
          action={
            <Button variant="ghost" onClick={() => (view ? void open(view) : dir.reload())}>
              Retry
            </Button>
          }
        >
          {error ?? dir.error}
        </Notice>
      ) : null}
      {notice ? (
        <Notice tone="success" title="Updated">
          {notice}
        </Notice>
      ) : null}
      {stats && !view ? (
        <Card>
          <CardBody>
            <h2>My practice summary</h2>
            <dl className="pms-console__tenant-form-grid">
              <div>
                <dt>Sessions</dt>
                <dd>{stats.sessions}</dd>
              </div>
              <div>
                <dt>Hours practiced</dt>
                <dd>{stats.hours_practiced}</dd>
              </div>
              <div>
                <dt>Average assessed score</dt>
                <dd>{stats.average_score === null ? 'Not assessed' : stats.average_score + '%'}</dd>
              </div>
              <div>
                <dt>Awaiting review</dt>
                <dd>{stats.awaiting_review}</dd>
              </div>
            </dl>
          </CardBody>
        </Card>
      ) : null}
      {!view ? (
        <>
          {kind === 'sessions' ? (
            <FilterBar>
              <Select
                label="Session scope"
                value={dir.query.mine ? 'mine' : 'permitted'}
                options={[
                  { value: 'permitted', label: 'All permitted sessions' },
                  { value: 'mine', label: 'My sessions' },
                ]}
                onChange={(v) => dir.setQuery({ ...dir.query, mine: v === 'mine' })}
              />
            </FilterBar>
          ) : null}
          <DataTable
            caption={kind === 'runs' ? 'Processing history' : 'Training sessions'}
            rows={dir.error ? [] : dir.page.items}
            columns={columns}
            rowId={(r) => r.id}
            loading={dir.loading}
            emptyTitle="No history available"
            emptyBody="Records appear after processing or training starts. Expired records are excluded."
          />
          <Pager
            count={dir.page.items.length}
            from={dir.page.from}
            limit={dir.query.limit}
            hasPrevious={dir.pageIndex > 0}
            hasNext={dir.page.has_more}
            onPrevious={() => dir.setPageIndex(dir.pageIndex - 1)}
            onNext={() => dir.setPageIndex(dir.pageIndex + 1)}
            busy={dir.loading}
          />
        </>
      ) : (
        <>
          <Card>
            <CardBody>
              <h2>{view.operation ?? 'Training session'}</h2>
              <dl className="pms-console__tenant-form-grid">
                <div>
                  <dt>Status</dt>
                  <dd>{view.status}</dd>
                </div>
                <div>
                  <dt>Device</dt>
                  <dd>
                    <Link href={'/devices/' + view.device_id}>{view.device_id}</Link>
                  </dd>
                </div>
                <div>
                  <dt>Language</dt>
                  <dd>{view.language ?? 'Not applicable'}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{new Date(view.created_at).toLocaleString()}</dd>
                </div>
                {view.result?.turns !== undefined ? (
                  <div>
                    <dt>Conversation turns</dt>
                    <dd>{view.result.turns}</dd>
                  </div>
                ) : null}
              </dl>
              {view.result ? (
                <details>
                  <summary>Result details</summary>
                  <dl>
                    {Object.entries(view.result)
                      .filter(
                        ([k, v]) =>
                          !k.endsWith('_recordings') &&
                          (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'),
                      )
                      .map(([k, v]) => (
                        <div key={k}>
                          <dt>{k.replaceAll('_', ' ')}</dt>
                          <dd>{String(v)}</dd>
                        </div>
                      ))}
                  </dl>
                </details>
              ) : null}
              {canManage && (kind === 'runs' || (!!viewerId && view.instructor_id === viewerId)) && active.includes(view.status) ? (
                <Button variant="danger" disabled={busy} onClick={() => setConfirm(true)}>
                  Stop {kind === 'runs' ? 'processing' : 'session'}
                </Button>
              ) : null}
              {kind === 'sessions' &&
              canMedia &&
              (view.result?.audio_recordings?.length || view.result?.video_recordings?.length) ? (
                <Link href="/recordings">Browse recordings</Link>
              ) : null}
              {view.feedback && !rubric.length ? (
                <>
                  <h3>Educator feedback</h3>
                  <p>{view.feedback.comments || 'No comments.'}</p>
                  <dl>
                    {Object.entries(view.feedback.scores).map(([k, v]) => (
                      <div key={k}>
                        <dt>{k}</dt>
                        <dd>{v.replaceAll('_', ' ')}</dd>
                      </div>
                    ))}
                  </dl>
                </>
              ) : null}
            </CardBody>
          </Card>
          {rubric.length ? (
            <Card>
              <CardBody>
                <h2>Educator feedback</h2>
                <form
                  className="pms-console__tenant-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void feedback();
                  }}
                >
                  {rubric.map((r) => (
                    <Select
                      key={r.id}
                      label={r.description}
                      value={scores[r.id] ?? 'not_observed'}
                      options={[
                        { value: 'met', label: 'Met' },
                        { value: 'partial', label: 'Partially met' },
                        { value: 'not_met', label: 'Not met' },
                        { value: 'not_observed', label: 'Not observed' },
                      ]}
                      onChange={(v) => setScores({ ...scores, [r.id]: v })}
                    />
                  ))}
                  <FormTextArea
                    label="Feedback comments"
                    maxLength={4000}
                    value={comments}
                    onChange={(e) => setComments(e.target.value)}
                  />
                  <Button type="submit" loading={busy}>
                    Save feedback
                  </Button>
                </form>
              </CardBody>
            </Card>
          ) : null}
          {media.length ? (
            <Card>
              <CardBody>
                <h2>Recordings</h2>
                <p className="pms-meta">
                  Playback access expires after a short period. Open again if the link expires.
                </p>
                {media.map((m) => (
                  <Button key={m.index} variant="ghost" disabled={busy} onClick={() => void playback(m)}>
                    Open {m.role} {m.format.toUpperCase()}
                  </Button>
                ))}
                {play ? (
                  play.type.startsWith('video/') ? (
                    <video controls preload="none" src={play.url} style={{ maxWidth: '100%' }} />
                  ) : play.type.startsWith('audio/') ? (
                    <audio controls preload="none" src={play.url} />
                  ) : (
                    <a href={play.url} rel="noreferrer">
                      Download recording
                    </a>
                  )
                ) : null}
              </CardBody>
            </Card>
          ) : null}
        </>
      )}
      <ConfirmDialog
        open={confirm}
        title="Stop this operation?"
        confirmLabel="Stop"
        tone="danger"
        busy={busy}
        error={error}
        onCancel={() => setConfirm(false)}
        onConfirm={() => void stop()}
      >
        This cancels active work. Existing results remain subject to the retention policy.
      </ConfirmDialog>
    </div>
  );
}
