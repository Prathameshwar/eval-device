'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { IconButton } from './IconButton';
import { CloseIcon } from './icons-console';
import { TONE_ICONS, type NoticeTone } from './Notice';

/** A toast carries the same four tones as `Notice`; `error` in the API maps to `danger`. */
export type ToastTone = NoticeTone;

/** Where the stack anchors. `bottom-end`/`top-end` are the inline-end corner — right in LTR. */
export type ToastPlacement = 'bottom-end' | 'top-end';

export type ToastOptions = {
  /** A short heading above the message — "Saved", "Payment failed". */
  title?: ReactNode;
  /**
   * Milliseconds on screen before it dismisses itself, or `null` to stay until dismissed. Omit to
   * take the per-tone default: an error stays, because it may be something the reader has to act on
   * and a message that vanishes is a message that was never read.
   */
  duration?: number | null;
};

type ToastRecord = {
  id: string;
  tone: ToastTone;
  message: ReactNode;
  title?: ReactNode;
  duration: number | null;
};

export type ToastApi = {
  /** The general form; the four named helpers below are the ones to reach for. */
  show: (tone: ToastTone, message: ReactNode, opts?: ToastOptions) => string;
  info: (message: ReactNode, opts?: ToastOptions) => string;
  success: (message: ReactNode, opts?: ToastOptions) => string;
  warning: (message: ReactNode, opts?: ToastOptions) => string;
  /** A failure. Persists until dismissed unless `duration` is given. */
  error: (message: ReactNode, opts?: ToastOptions) => string;
  dismiss: (id: string) => void;
  clear: () => void;
};

/*
 * A success or an info is transient — it confirms something the reader already knows they did, so
 * it fades. A warning lingers longer. An error does not leave on its own: `null` keeps it until the
 * reader dismisses it, so a failed save is not a flash they can miss.
 */
const DEFAULT_DURATION: Record<ToastTone, number | null> = {
  info: 5000,
  success: 5000,
  warning: 8000,
  danger: null,
};

const ToastContext = createContext<ToastApi | null>(null);

/**
 * The imperative handle. Throws when there is no `ToastProvider` above it, rather than silently
 * dropping notifications — a save that reports success into the void is worse than a crash in dev.
 */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (ctx === null) {
    throw new Error('useToast must be used within a <ToastProvider>.');
  }
  return ctx;
}

type ToastProviderProps = {
  children: ReactNode;
  /** The stack is capped so a burst cannot bury the screen; the oldest drops first. */
  max?: number;
  placement?: ToastPlacement;
};

/**
 * Transient status messages floated over the page. The visual language is
 * `Notice`'s — same tone triple, same icon, same leading edge — because an inline banner and a
 * floated toast saying "success" should not be two different greens.
 *
 * Notifications are ephemeral UI, never the record of what happened: the durable trail is the audit
 * log (audit), and authorization is server-side. A toast that never
 * showed changes nothing about either.
 */
export function ToastProvider({ children, max = 4, placement = 'bottom-end' }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  // A monotonic counter, not a random id: two toasts pushed in the same tick still need distinct
  // keys, and `Math.random` would make the render non-deterministic to test.
  const idRef = useRef(0);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const clear = useCallback(() => setToasts([]), []);

  const show = useCallback(
    (tone: ToastTone, message: ReactNode, opts: ToastOptions = {}): string => {
      idRef.current += 1;
      const id = `toast-${idRef.current}`;
      const duration = opts.duration === undefined ? DEFAULT_DURATION[tone] : opts.duration;
      setToasts((prev) => {
        const next = [...prev, { id, tone, message, title: opts.title, duration }];
        // Keep the newest `max`; a flood of the same error should not push the page out of reach.
        return next.length > max ? next.slice(next.length - max) : next;
      });
      return id;
    },
    [max],
  );

  const api = useMemo<ToastApi>(
    () => ({
      show,
      info: (message, opts) => show('info', message, opts),
      success: (message, opts) => show('success', message, opts),
      warning: (message, opts) => show('warning', message, opts),
      error: (message, opts) => show('danger', message, opts),
      dismiss,
      clear,
    }),
    [show, dismiss, clear],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} placement={placement} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

function ToastViewport({
  toasts,
  placement,
  onDismiss,
}: {
  toasts: ToastRecord[];
  placement: ToastPlacement;
  onDismiss: (id: string) => void;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  // Portals have no server markup. Wait until hydration completes before adding one.
  if (!mounted) return null;

  return createPortal(
    /*
     * A landmark, not a live region: each toast announces itself through its own `role`, so making
     * the container `aria-live` too would re-read the whole stack every time one arrives.
     */
    <div className="pms-toasts" data-placement={placement} role="region" aria-label="Notifications">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>,
    document.body,
  );
}

function ToastItem({ toast, onDismiss }: { toast: ToastRecord; onDismiss: (id: string) => void }) {
  const { id, tone, title, message, duration } = toast;
  // Pointer or keyboard focus freezes the countdown: a toast the reader is reading, or has tabbed
  // to in order to dismiss, must not disappear mid-read.
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (duration === null || paused) return;
    const timer = setTimeout(() => onDismiss(id), duration);
    return () => clearTimeout(timer);
  }, [id, duration, paused, onDismiss]);

  // A failure or a caution interrupts (`alert`); a confirmation waits its turn (`status`). Same
  // split as `Notice`, for the same reason.
  const assertive = tone === 'danger' || tone === 'warning';

  return (
    <div
      className="pms-toast"
      data-tone={tone}
      role={assertive ? 'alert' : 'status'}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <span className="pms-toast__icon" aria-hidden="true">
        {TONE_ICONS[tone]}
      </span>
      <div className="pms-toast__body">
        {title ? <p className="pms-toast__title">{title}</p> : null}
        <div className="pms-toast__text">{message}</div>
      </div>
      <IconButton label="Dismiss" icon={<CloseIcon size={14} />} onClick={() => onDismiss(id)} />
    </div>
  );
}
