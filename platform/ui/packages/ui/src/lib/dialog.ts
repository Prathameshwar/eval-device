'use client';

import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from 'react';

/**
 * The accessibility mechanism shared by every modal surface — `ConfirmDialog`, `Modal`, `Drawer`.
 * Written once here rather than per component: a focus trap that lets Tab wander out
 * of one dialog but not another is exactly the kind of drift that a second copy invites.
 *
 * It owns four things and no markup: where focus goes on open, where it returns on close, the Tab
 * cycle inside the panel, and the body scroll lock. The scrim, the panel and its contents belong to
 * the caller — this only needs a ref to the panel and a keydown handler to put on it.
 */

/** Candidates; visibility and native focusability are checked before each use. */
export const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function isAvailable(element: HTMLElement): boolean {
  if (element.matches(':disabled, input[type="hidden"]') || element.closest('[hidden], [inert]')) {
    return false;
  }
  const view = element.ownerDocument.defaultView;
  if (!view) return false;
  const visibility = view.getComputedStyle(element).visibility;
  if (visibility === 'hidden' || visibility === 'collapse') return false;
  for (let ancestor: HTMLElement | null = element; ancestor; ancestor = ancestor.parentElement) {
    if (view.getComputedStyle(ancestor).display === 'none') return false;
    if (ancestor.matches('details:not([open])')) {
      const summary = ancestor.querySelector('summary');
      if (!summary?.contains(element)) return false;
    }
  }
  return true;
}

function tabStops(panel: HTMLElement): HTMLElement[] {
  return [...panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)]
    .filter((element) => element.tabIndex >= 0 && isAvailable(element))
    // Positive tabindex participates before the ordinary document-order controls.
    .sort((a, b) => (a.tabIndex || Infinity) - (b.tabIndex || Infinity));
}

type OpenDialog = { panel: HTMLElement; opener: HTMLElement | null };
const dialogs = new WeakMap<Document, OpenDialog[]>();
const scrollLocks = new WeakMap<Document, { count: number; value: string; priority: string }>();

export type UseDialogA11yOptions = {
  open: boolean;
  /** Called on Escape, and by the caller's scrim — only fires when `dismissible`. */
  onClose: () => void;
  /**
   * Escape (and the caller's scrim, which checks the same flag) are ignored when false: an action
   * in flight cannot be recalled, so dismissing here would leave the user believing nothing happened.
   */
  dismissible?: boolean;
  /**
   * The element to focus on open, given the panel. Return `null` to fall back to the first focusable
   * child, and then to the panel itself. A destructive dialog focuses Cancel; a form focuses its
   * first field.
   */
  initialFocus?: (panel: HTMLElement | null) => HTMLElement | null;
  /** Lock body scroll while open, restoring whatever was set before. Default `true`. */
  lockScroll?: boolean;
};

export type DialogA11y = {
  panelRef: RefObject<HTMLDivElement | null>;
  onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
};

export function useDialogA11y({
  open,
  onClose,
  dismissible = true,
  initialFocus,
  lockScroll = true,
}: UseDialogA11yOptions): DialogA11y {
  const panelRef = useRef<HTMLDivElement | null>(null);
  // The callbacks live in a ref so the focus and scroll effects depend only on `open`: a caller that
  // passes a fresh `onClose` closure every render must not tear the trap down and rebuild it.
  const latest = useRef({ onClose, dismissible, initialFocus });
  latest.current = { onClose, dismissible, initialFocus };

  // Focus in on open; back out to whatever opened it on close — a kebab item, usually, which has
  // itself unmounted by then, so the fallback is to leave focus alone.
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;
    const doc = panel.ownerDocument;
    const stack = dialogs.get(doc) ?? [];
    dialogs.set(doc, stack);
    const entry = { panel, opener: doc.activeElement as HTMLElement | null };
    stack.push(entry);
    const preferred = latest.current.initialFocus?.(panel);
    const target = preferred && isAvailable(preferred) ? preferred : tabStops(panel)[0] ?? panel;
    target.focus();

    return () => {
      const index = stack.indexOf(entry);
      const wasTop = index === stack.length - 1;
      stack.splice(index, 1);
      // A lower dialog can disappear before the one it opened. Carry its return target forward.
      for (const remaining of stack) {
        if (remaining.opener && panel.contains(remaining.opener)) remaining.opener = entry.opener;
      }
      if (!wasTop) return;
      const remaining = stack[stack.length - 1];
      const opener = entry.opener;
      if (
        opener?.isConnected &&
        isAvailable(opener) &&
        (!remaining || remaining.panel.contains(opener))
      ) {
        opener.focus();
      } else if (remaining) {
        (tabStops(remaining.panel)[0] ?? remaining.panel).focus();
      }
    };
  }, [open]);

  // Body scroll lock. Restores the previous inline value rather than clearing it, so a stacked
  // overlay or an app that set its own overflow both survive the close.
  useEffect(() => {
    if (!open || !lockScroll || typeof document === 'undefined') return;
    const doc = panelRef.current?.ownerDocument ?? document;
    const style = doc.body.style;
    const lock = scrollLocks.get(doc) ?? {
      count: 0,
      value: style.getPropertyValue('overflow'),
      priority: style.getPropertyPriority('overflow'),
    };
    if (lock.count === 0) {
      scrollLocks.set(doc, lock);
      style.setProperty('overflow', 'hidden');
    }
    lock.count += 1;
    return () => {
      lock.count -= 1;
      if (lock.count === 0) {
        if (lock.value) style.setProperty('overflow', lock.value, lock.priority);
        else style.removeProperty('overflow');
        scrollLocks.delete(doc);
      }
    };
  }, [open, lockScroll]);

  function onKeyDown(event: ReactKeyboardEvent<HTMLElement>): void {
    if (event.defaultPrevented) return;
    const panel = panelRef.current;
    if (!panel) return;
    const stack = dialogs.get(panel.ownerDocument);
    if (stack?.[stack.length - 1]?.panel !== panel) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      if (latest.current.dismissible) latest.current.onClose();
      return;
    }
    if (event.key !== 'Tab') return;

    const focusable = tabStops(panel);
    if (focusable.length === 0) {
      event.preventDefault();
      panel.focus();
      return;
    }
    const first = focusable[0] as HTMLElement;
    const last = focusable[focusable.length - 1] as HTMLElement;
    const active = panel.ownerDocument.activeElement;

    // Only the two edges are handled; in between, the browser's own order is the right one.
    const outsideTabOrder = !focusable.includes(active as HTMLElement);
    if (event.shiftKey && (active === first || outsideTabOrder)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || outsideTabOrder)) {
      event.preventDefault();
      first.focus();
    }
  }

  return { panelRef, onKeyDown };
}
