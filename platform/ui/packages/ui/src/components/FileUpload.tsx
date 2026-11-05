'use client';

import {
  useCallback,
  useId,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from 'react';
import {
  CheckCircleIcon,
  CloseIcon,
  DocumentIcon,
  RefreshIcon,
  UploadIcon,
  WarnTriangleIcon,
  XCircleIcon,
} from './icons-console';

/**
 * `FileUpload` — attach files to a document.
 *
 * Like `SearchSelect`, it deliberately does two things less than it looks like it does:
 *
 *  - **It never uploads.** The caller receives the accepted `File`s and owns the transport, the
 *    idempotency key and the retry policy. That is not squeamishness: an upload belongs to a
 *    service and a tenant, and a component that posted on its own would have to know both.
 *  - **It never decides what is allowed.** `accept`, `maxSizeBytes` and `maxFiles` are there so
 *    a person is told before they wait for a 10 MB round trip. They are presentation, and the
 *    server must re-validate every one of them — a request can be replayed without ever going
 *    near this control.
 *
 * The rendered list is `items`, held by the caller, so an edit form can show attachments that
 * were stored months ago beside one being uploaded right now.
 */

export type FileUploadStatus = 'pending' | 'uploading' | 'done' | 'failed';

export type FileUploadItem = {
  /** The caller's id — an upload id while in flight, the attachment id once stored. */
  id: string;
  name: string;
  /** Bytes. Absent for a stored attachment whose size the caller does not hold. */
  size?: number;
  status: FileUploadStatus;
  /** 0–100 while `uploading`. Absent means in flight with no measurable progress. */
  progress?: number;
  /** Why it failed, in the words the service used. */
  error?: string;
  /**
   * A **signed, expiring** URL. Never a public object-storage URL: an
   * attachment on an invoice is someone's commercial document.
   */
  href?: string;
};

export type FileRejectionReason = 'type' | 'size' | 'count' | 'duplicate' | 'empty';

export type FileRejection = {
  /** The name as offered, already stripped of bidi overrides — safe to render. */
  name: string;
  reason: FileRejectionReason;
  /** A whole sentence, ready to show. */
  message: string;
};

type FileUploadProps = {
  label: string;
  /** What to render, newest wherever the caller puts it. This control never reorders it. */
  items?: readonly FileUploadItem[];
  /** The files that passed every stated limit, in the order they were offered. */
  onSelect: (files: File[]) => void;
  /** Renders a remove button per row when supplied, and nothing when not. */
  onRemove?: (item: FileUploadItem) => void;
  /** Renders a retry button on a failed row when supplied. */
  onRetry?: (item: FileUploadItem) => void;
  /** The files that did not pass. The control shows them regardless — this is for logging. */
  onReject?: (rejections: FileRejection[]) => void;
  /** Native `accept` syntax: `.pdf`, `image/*`, `application/pdf`, or a comma-separated list. */
  accept?: string;
  /** The human phrase for `accept`, e.g. "PDF or image". Falls back to `accept` verbatim. */
  acceptLabel?: string;
  maxSizeBytes?: number;
  maxFiles?: number;
  multiple?: boolean;
  /** Overrides the zone's own sentence. */
  prompt?: string;
  hint?: ReactNode;
  error?: string;
  /** Right-aligned note beside the label, e.g. "kept for seven years". */
  optionalNote?: string;
  /** Right-aligned interactive element beside the label. */
  action?: ReactNode;
  hideLabel?: boolean;
  disabled?: boolean;
  /** At least one file. Enforced natively, and only while nothing has been attached yet. */
  required?: boolean;
};

/**
 * Powers of two, labelled the way every file dialog labels them.
 *
 * Deliberately not routed through `useFormatters`: a byte count is not an amount and carries no
 * company display config, so `company.amount_precision` would render a 1 MB file as
 * `1,048,576.0000`.
 */
const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const;

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '';
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  // One decimal below 10, none above: "9.4 MB" is useful, "9.4 GB" is, "947.3 KB" is noise.
  return `${value >= 10 ? Math.round(value) : value.toFixed(1)} ${UNITS[unit]}`;
}

/**
 * Bidi controls and zero-width marks, stripped before a name is ever rendered.
 *
 * A file named `invoice<U+202E>gnp.exe` displays as `invoice` then `exe.png` — the override flips
 * the rest of the string, so the extension a person reads is not the extension that will run.
 * It is an old trick and it works because everyone renders the name the OS handed them. React
 * escapes markup; it does not undo this.
 */
const BIDI = /[\u202A-\u202E\u2066-\u2069\u200E\u200F\u061C]/g;

function safeName(name: string): string {
  return name.replace(BIDI, '').trim() || 'Unnamed file';
}

/** Native `accept` semantics: an extension, a `type/*` family, or an exact MIME type. */
function acceptsFile(file: File, accept: string | undefined): boolean {
  if (!accept) return true;
  const patterns = accept
    .split(',')
    .map((pattern) => pattern.trim().toLowerCase())
    .filter(Boolean);
  if (patterns.length === 0) return true;

  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();

  return patterns.some((pattern) => {
    if (pattern.startsWith('.')) return name.endsWith(pattern);
    if (pattern.endsWith('/*')) return type.startsWith(pattern.slice(0, -1));
    /* An unknown MIME type never matches a MIME pattern — the browser reports `''` for plenty of
     * legitimate files, which is exactly why an extension pattern is the safer thing to ask for. */
    return type !== '' && type === pattern;
  });
}

export function FileUpload({
  label,
  items = [],
  onSelect,
  onRemove,
  onRetry,
  onReject,
  accept,
  acceptLabel,
  maxSizeBytes,
  maxFiles,
  multiple = false,
  prompt,
  hint,
  error,
  optionalNote,
  action,
  hideLabel = false,
  disabled = false,
  required = false,
}: FileUploadProps) {
  const uid = useId();
  const inputId = `${uid}-input`;
  const labelId = `${uid}-label`;
  const constraintsId = `${uid}-constraints`;
  const hintId = `${uid}-hint`;
  const errorId = `${uid}-error`;

  const [rejections, setRejections] = useState<readonly FileRejection[]>([]);

  /*
   * Drag events fire per element, so moving the pointer from the zone onto the text inside it is
   * a `dragleave` followed by a `dragenter`. Counting them is what stops the zone flickering
   * while the pointer is still, unambiguously, over it.
   */
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);

  /** The cap is reached, so there is nothing to offer — distinct from the field being refused. */
  const atLimit = maxFiles !== undefined && items.length >= maxFiles;
  const inoperable = disabled || atLimit;

  const constraints = useMemo(() => {
    const parts: string[] = [];
    const kinds = acceptLabel ?? accept;
    if (kinds) parts.push(kinds);
    if (maxSizeBytes !== undefined) parts.push(`up to ${formatBytes(maxSizeBytes)} each`);
    if (maxFiles !== undefined) parts.push(maxFiles === 1 ? '1 file' : `${maxFiles} files at most`);
    return parts.join(' · ');
  }, [accept, acceptLabel, maxSizeBytes, maxFiles]);

  /*
   * Everything that renders, and nothing that does not: a dangling idref is dropped silently by
   * assistive technology, so listing an id whose paragraph was not rendered quietly loses the
   * description that was.
   */
  const describedBy =
    [constraints ? constraintsId : null, error ? errorId : hint ? hintId : null]
      .filter(Boolean)
      .join(' ') || undefined;

  /**
   * Screens a batch against the stated limits.
   *
   * Every rejection carries a finished sentence, because "rejected" on its own leaves someone
   * re-dropping the same file to find out why.
   */
  const screen = useCallback(
    (offered: readonly File[]): { accepted: File[]; rejected: FileRejection[] } => {
      const accepted: File[] = [];
      const rejected: FileRejection[] = [];
      /* Compared on name and size together: two files can legitimately share a name, and a
       * re-drop of the same one is the case worth catching. The separator is NUL because it
       * is the one byte a file name cannot hold, so no name can forge another name-and-size pair.
       *
       * `safeName` on both sides, or this compares two spellings of the same file: the rows show
       * the tidied name, and an offered file is keyed by its tidied name too. Seeding the set from
       * the raw one let anything carrying a bidi override or a stray space through a second time —
       * the file the user can plainly see attached, accepted again. */
      const seen = new Set(items.map((item) => `${safeName(item.name)}\u0000${item.size ?? ''}`));
      const room = maxFiles === undefined ? Infinity : maxFiles - items.length;
      const allowed = multiple ? room : Math.min(room, 1);

      for (const file of offered) {
        const name = safeName(file.name);

        if (file.size === 0) {
          /* Also what a dropped folder looks like in Chrome — size 0 and no type — so the
           * sentence has to cover both without guessing which it was. */
          rejected.push({ name, reason: 'empty', message: `${name} is empty, or is a folder.` });
          continue;
        }
        if (!acceptsFile(file, accept)) {
          rejected.push({
            name,
            reason: 'type',
            message: `${name} is not ${acceptLabel ?? `one of ${accept}`}.`,
          });
          continue;
        }
        if (maxSizeBytes !== undefined && file.size > maxSizeBytes) {
          rejected.push({
            name,
            reason: 'size',
            message: `${name} is ${formatBytes(file.size)} — the limit is ${formatBytes(maxSizeBytes)}.`,
          });
          continue;
        }
        const key = `${name}\u0000${file.size}`;
        if (seen.has(key)) {
          rejected.push({ name, reason: 'duplicate', message: `${name} is already attached.` });
          continue;
        }
        if (accepted.length >= allowed) {
          rejected.push({
            name,
            reason: 'count',
            message: multiple
              ? `${name} was not added — ${maxFiles} ${maxFiles === 1 ? 'file' : 'files'} is the maximum.`
              : `${name} was not added — only one file can be attached.`,
          });
          continue;
        }
        seen.add(key);
        accepted.push(file);
      }

      return { accepted, rejected };
    },
    [items, accept, acceptLabel, maxSizeBytes, maxFiles, multiple],
  );

  const offer = useCallback(
    (files: readonly File[]) => {
      if (inoperable || files.length === 0) return;
      const { accepted, rejected } = screen(files);
      // Replaced, not appended: a rejection belongs to the batch that produced it.
      setRejections(rejected);
      if (rejected.length > 0) onReject?.(rejected);
      if (accepted.length > 0) onSelect(accepted);
    },
    [inoperable, screen, onReject, onSelect],
  );

  /* ---------------- drag and drop ---------------- */

  /* Only a file drag lights the zone up. Dragging selected text across the page is not an
   * offer of a file, and a zone that reacts to it is a zone that lies about what it accepts. */
  const isFileDrag = (event: DragEvent) =>
    Array.from(event.dataTransfer?.types ?? []).includes('Files');

  const onDragEnter = (event: DragEvent<HTMLDivElement>) => {
    if (inoperable || !isFileDrag(event)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };

  const onDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (inoperable || !isFileDrag(event)) return;
    /* Without `preventDefault` here the browser's own default wins and `drop` never fires — the
     * single most common reason a drop zone silently does nothing. */
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
  };

  const onDragLeave = () => {
    if (inoperable) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    if (inoperable) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    offer(Array.from(event.dataTransfer?.files ?? []));
  };

  /* ---------------- rendering ---------------- */

  const uploading = items.filter((item) => item.status === 'uploading').length;
  const failed = items.filter((item) => item.status === 'failed').length;
  const done = items.filter((item) => item.status === 'done').length;

  /* One sentence, changing a handful of times per batch. A live region that re-announced every
   * progress tick would talk over everything else on the page. */
  const announcement = uploading
    ? `Uploading ${uploading} of ${items.length}`
    : failed
      ? `${failed} ${failed === 1 ? 'upload' : 'uploads'} failed`
      : done
        ? `${done} ${done === 1 ? 'file' : 'files'} uploaded`
        : '';

  /** One slot beside the label — an action wins over the note, as on every other field. */
  const beside =
    action ?? (optionalNote ? <span className="pms-optional">{optionalNote}</span> : null);

  const defaultPrompt = multiple
    ? 'Choose files, or drag them here'
    : 'Choose a file, or drag it here';

  return (
    <div
      className="pms-field pms-upload"
      data-invalid={error ? 'true' : undefined}
      data-disabled={inoperable ? 'true' : undefined}
    >
      {/*
        A `<span>`, not a `<label>`: the zone below is the input's `<label>` — it has to be, to be
        the click target — and two labels on one control concatenate into one announced name. The
        field's name comes from `aria-labelledby` pointing here, which wins.

        `hideLabel` clips the *label*, never the row: `pms-visually-hidden` hides without
        removing, so hiding the row left a link or button passed as `action` focusable and
        invisible — a tab stop a sighted keyboard user cannot see (WCAG 2.4.7). With nothing beside
        the label there is no row to render at all.
      */}
      {hideLabel && !beside ? (
        <span className="pms-label pms-visually-hidden" id={labelId}>
          {label}
        </span>
      ) : (
        <div className="pms-field__row">
          <span
            className={hideLabel ? 'pms-label pms-visually-hidden' : 'pms-label'}
            id={labelId}
          >
            {label}
          </span>
          {beside}
        </div>
      )}

      <div
        className="pms-upload__drop"
        data-dragging={dragging ? 'true' : undefined}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        {/*
          Visually hidden but still focusable and still the only tab stop: `pms-visually-hidden`
          clips, it does not `display: none`. Space or Enter on a focused file input opens the
          picker, so the keyboard path is the platform's, and the CSS projects the focus ring onto
          the zone via an adjacent-sibling selector.
        */}
        <input
          id={inputId}
          type="file"
          className="pms-upload__input pms-visually-hidden"
          accept={accept}
          multiple={multiple}
          disabled={inoperable}
          /* Only while nothing is attached. The input's own value is cleared after every
             selection, so a `required` left standing would block a submit on a form that does
             hold files. */
          required={required && items.length === 0}
          aria-labelledby={labelId}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          onChange={(event) => {
            offer(Array.from(event.target.files ?? []));
            /* Cleared so choosing the same file twice fires `change` twice. Without this, a
               failed upload cannot be retried by picking the same file again — the browser sees
               no change and stays silent. */
            event.target.value = '';
          }}
        />

        <label className="pms-upload__zone" htmlFor={inputId}>
          <span className="pms-upload__icon" aria-hidden="true">
            <UploadIcon size={20} />
          </span>
          <span className="pms-upload__prompt">
            {atLimit && !disabled
              ? `${maxFiles === 1 ? 'One file' : `${maxFiles} files`} attached — remove one to add another`
              : (prompt ?? defaultPrompt)}
          </span>
          {constraints ? (
            <span className="pms-upload__constraints" id={constraintsId}>
              {constraints}
            </span>
          ) : null}
        </label>
      </div>

      {rejections.length > 0 ? (
        <div className="pms-upload__rejects" role="alert">
          <p className="pms-upload__reject-head">
            <WarnTriangleIcon size={14} />
            {rejections.length === 1
              ? '1 file wasn’t added'
              : `${rejections.length} files weren’t added`}
          </p>
          <ul>
            {/* Keyed by position as well as identity: three copies of one file in a batch produce
              * two rejections with the same name *and* the same reason, and a key built from those
              * two alone collides. Nothing here reorders, so the index is stable. */}
            {rejections.map((rejection, index) => (
              <li key={`${index}-${rejection.name}-${rejection.reason}`}>{rejection.message}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {items.length > 0 ? (
        <ul className="pms-upload__list">
          {items.map((item) => {
            const name = safeName(item.name);
            const percent =
              item.progress === undefined
                ? undefined
                : Math.min(100, Math.max(0, Math.round(item.progress)));

            return (
              <li key={item.id} className="pms-upload__item" data-status={item.status}>
                <span className="pms-upload__item-icon" aria-hidden="true">
                  {item.status === 'done' ? (
                    <CheckCircleIcon size={16} />
                  ) : item.status === 'failed' ? (
                    <XCircleIcon size={16} />
                  ) : item.status === 'uploading' ? (
                    <span className="pms-spinner" />
                  ) : (
                    <DocumentIcon size={16} />
                  )}
                </span>

                <span className="pms-upload__item-text">
                  <span className="pms-upload__item-name">
                    {/*
                      A finished attachment is a link, because the point of attaching it is
                      reading it back. `href` is a signed, expiring URL — the control does not
                      mint it and does not check it (§5.14).
                    */}
                    {item.status === 'done' && item.href ? (
                      <a className="pms-link" href={item.href}>
                        {name}
                      </a>
                    ) : (
                      name
                    )}
                  </span>

                  <span className="pms-upload__item-meta pms-figure">
                    {[
                      item.size === undefined ? null : formatBytes(item.size),
                      item.status === 'failed'
                        ? (item.error ?? 'Upload failed')
                        : item.status === 'uploading'
                          ? percent === undefined
                            ? 'Uploading…'
                            : `Uploading… ${percent}%`
                          : item.status === 'done'
                            ? 'Uploaded'
                            : 'Waiting',
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>

                  {item.status === 'uploading' ? (
                    <span
                      className="pms-upload__bar"
                      role="progressbar"
                      aria-label={`Uploading ${name}`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      /* Omitted entirely when there is no measurement: an indeterminate
                         progressbar is a defined state, and `aria-valuenow={0}` is a claim that
                         nothing has been sent. */
                      aria-valuenow={percent}
                      data-indeterminate={percent === undefined ? 'true' : undefined}
                    >
                      <span
                        className="pms-upload__bar-fill"
                        /* A data-driven width is the one thing no token can express. */
                        style={percent === undefined ? undefined : { width: `${percent}%` }}
                      />
                    </span>
                  ) : null}
                </span>

                {item.status === 'failed' && onRetry ? (
                  <button
                    type="button"
                    className="pms-upload__action"
                    onClick={() => onRetry(item)}
                  >
                    <RefreshIcon size={14} />
                    Retry
                  </button>
                ) : null}

                {onRemove ? (
                  <button
                    type="button"
                    className="pms-upload__action pms-upload__action--icon"
                    /* Named per row: five buttons all called "Remove" is a list a screen-reader
                       user cannot navigate. */
                    aria-label={`Remove ${name}`}
                    disabled={disabled}
                    onClick={() => onRemove(item)}
                  >
                    <CloseIcon size={14} />
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}

      {error ? (
        <p className="pms-error" id={errorId} role="alert">
          <WarnTriangleIcon size={14} />
          {error}
        </p>
      ) : hint ? (
        <p className="pms-hint" id={hintId}>
          {hint}
        </p>
      ) : null}

      {/* A list of files whose states change silently does not exist to a screen reader. */}
      <span className="pms-visually-hidden" role="status" aria-live="polite">
        {announcement}
      </span>
    </div>
  );
}
