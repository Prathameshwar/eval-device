'use client';

// `useId` is a client hook, and the rail is routinely composed in an app's root layout —
// which may be a server component — so the boundary is declared here rather than left to
// whichever consumer happens to import it first.

import { useId, type ElementType, type ReactNode } from 'react';
import { isSafeHref } from '../lib/url';

/**
 * The left rail. Four bands on an inner grid — brand · organisation switcher ·
 * navigation · pinned footer — where only the navigation band scrolls, so the lockup and
 * the user card stay put however long the nav grows.
 *
 * Every band is placed explicitly rather than by auto-flow: an absent switcher must not
 * promote the nav into the switcher's row and hand the footer the flexible one.
 */
export function Rail({
  brand,
  switcher,
  children,
  footer,
}: {
  brand: ReactNode;
  switcher?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="pms-rail">
      <div className="pms-rail__brand">{brand}</div>
      {switcher ? <div className="pms-rail__switcher">{switcher}</div> : null}
      <div className="pms-rail__nav">{children}</div>
      {footer ? <div className="pms-rail__foot">{footer}</div> : null}
    </div>
  );
}

/**
 * A named group of rail items. The overline is a real label — it names the `<nav>` via
 * `aria-labelledby`, so "Ledger" is announced as the group rather than being decorative
 * text a screen reader reads and then forgets.
 */
export function RailSection({ label, children }: { label: string; children: ReactNode }) {
  const labelId = useId();

  return (
    <nav className="pms-rail-section" aria-labelledby={labelId}>
      <p className="pms-rail-section__label" id={labelId}>
        {label}
      </p>
      <ul className="pms-rail-section__list">{children}</ul>
    </nav>
  );
}

/**
 * One navigation destination. It knows nothing about permissions — gating happens at the
 * call site by wrapping the item, so the rail stays a layout component and permission
 * logic lives in exactly one place.
 *
 * The label is both visible text and `aria-label`: a collapsed rail hides the text with
 * CSS, and `display:none` would take the accessible name with it.
 */
export function RailItem({
  icon,
  label,
  href,
  active = false,
  as,
}: {
  icon: ReactNode;
  label: string;
  href: string;
  active?: boolean;
  /**
   * The element to render a safe destination with — a router's link component, typically
   * (`next/link`, `react-router`'s `Link`). Defaults to a plain `<a>`, which in a router-based
   * app costs a full document load on every menu click.
   *
   * It is an escape hatch for *routing*, not for styling or behaviour: whatever is passed
   * receives exactly the props the anchor would have received, and an unsafe `href` still
   * degrades to a `<span>` before this is consulted.
   */
  as?: ElementType;
}) {
  /* The two conditions below used to test `Link === 'a'`, which was the same question as
   * "is the destination safe" only while `<a>` was the only link element. With `as`, a router's
   * link is also a link — so the question is asked once, of the href. */
  const linked = isSafeHref(href);
  const Link = linked ? (as ?? 'a') : 'span';
  return (
    <li className="pms-rail-item-slot">
      <Link
        className="pms-rail-item"
        href={linked ? href : undefined}
        aria-label={label}
        title={label}
        aria-current={active && linked ? 'page' : undefined}
        data-active={active ? 'true' : undefined}
      >
        <span className="pms-rail-item__icon" aria-hidden="true">
          {icon}
        </span>
        <span className="pms-rail-item__label">{label}</span>
      </Link>
    </li>
  );
}

/**
 * The rail's pinned base: help and settings, above a hairline rule.
 *
 * Its children are `RailItem`s, which render `<li>` — so this has to be a list, or they are
 * list items with no list parent (invalid HTML, and the marker is only suppressed by the
 * nav's list rule). It reuses `.pms-rail-section__list` for that suppression rather than
 * inventing a second class that would have to be kept in step with it.
 *
 * Anything that is *not* a `RailItem` — a user card, a version string — belongs beside this
 * element, not inside it, for the same reason.
 */
export function RailFooter({ children, label = 'Support' }: { children: ReactNode; label?: string }) {
  const labelId = useId();

  return (
    <nav className="pms-rail-footer" aria-labelledby={labelId}>
      <p className="pms-visually-hidden" id={labelId}>
        {label}
      </p>
      <ul className="pms-rail-section__list">{children}</ul>
    </nav>
  );
}
