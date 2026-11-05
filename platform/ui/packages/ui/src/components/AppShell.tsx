'use client';

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { IconButton } from './IconButton';
import { CloseIcon, MenuIcon } from './icons-console';

/**
 * The console shell: one grid, one scroll container.
 *
 *   columns  rail | content        rows  top bar | main
 *   the rail spans both rows, so the lockup sits in the top bar's band
 *   `main` is the only `overflow-y:auto`, so the rail and top bar never move
 *
 * Below the drawer breakpoint the rail leaves the grid and becomes an off-canvas drawer.
 * That state is the shell's own, because "is the drawer showing" is transient. `collapsed`
 * belongs to the caller instead: it is a preference about how the person likes to work, so the
 * app decides whether to remember it and where.
 *
 * Today the console keeps it in component state, which means it resets on reload. Persisting it
 * needs the same pre-paint treatment as the theme — read before the first frame, or the rail
 * renders at 288px and snaps to 72px after hydration, which looks like a bug rather than a
 * restored preference.
 */
export function AppShell({
  rail,
  topBar,
  footer,
  collapsed = false,
  onToggleCollapsed,
  navigationKey,
  children,
}: {
  rail: ReactNode;
  topBar: ReactNode;
  footer?: ReactNode;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  /** The current route; dismiss the mobile drawer after client-side navigation. */
  navigationKey?: string;
  children: ReactNode;
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const previousNavigationKey = useRef(navigationKey);
  const uid = useId();
  const railId = `${uid}-rail`;
  const mainId = `${uid}-main`;
  const menuId = `${uid}-menu`;
  const railRef = useRef<HTMLDivElement | null>(null);

  /**
   * Closing the drawer applies `visibility: hidden` to the rail — which is what keeps a
   * closed drawer out of the tab order — so anything focused inside it stops being focusable
   * and focus falls to `<body>`. A user who tabbed into the drawer and pressed Escape lost
   * their place entirely, which is the failure the Escape key was meant to avoid.
   */
  const closeDrawer = useCallback((): void => {
    const active = document.activeElement;
    const insideRail = active instanceof HTMLElement && railRef.current?.contains(active) === true;
    setDrawerOpen(false);
    if (insideRail) document.getElementById(menuId)?.focus();
  }, [menuId]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') closeDrawer();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [drawerOpen, closeDrawer]);

  useEffect(() => {
    if (previousNavigationKey.current === navigationKey) return;
    previousNavigationKey.current = navigationKey;
    // Only a completed route change dismisses the drawer. A cancelled navigation or a
    // link opened in another tab leaves this page alone, as do ordinary shell updates.
    if (drawerOpen) closeDrawer();
  }, [navigationKey, drawerOpen, closeDrawer]);

  function toggleDrawer(): void {
    if (drawerOpen) {
      closeDrawer();
      return;
    }
    setDrawerOpen(true);
    // A drawer is full width; showing the icon-only rail inside it would be a bug, so
    // opening one expands a collapsed rail through the caller's own state.
    if (collapsed) onToggleCollapsed?.();
  }

  return (
    <div
      className="pms-shell"
      data-collapsed={collapsed ? 'true' : undefined}
      data-drawer={drawerOpen ? 'open' : 'closed'}
    >
      {/* The bypass mechanism (WCAG 2.4.1): the rail precedes the content with a dozen-odd
          links, so the first focusable element in the shell jumps over them. */}
      <a className="pms-skip-link" href={`#${mainId}`}>
        Skip to main content
      </a>

      <div className="pms-shell__rail" id={railId} ref={railRef}>
        {rail}
      </div>

      {/* The drawer control shares the top bar's leading edge with the caller's
          CollapseToggle; CSS shows exactly one of them at any width. */}
      <div className="pms-shell__topbar">
        <IconButton
          id={menuId}
          className="pms-shell__menu"
          label={drawerOpen ? 'Close navigation' : 'Open navigation'}
          icon={drawerOpen ? <CloseIcon /> : <MenuIcon />}
          aria-expanded={drawerOpen}
          aria-controls={railId}
          onClick={toggleDrawer}
        />
        {topBar}
      </div>

      {/* The scroll container is the grid cell; `main` and the page footer are siblings inside
          it. A `<footer>` nested in `<main>` maps to `generic`, not `contentinfo`, so the
          landmark only exists if the footer sits outside — while still scrolling with the
          content rather than stealing a band of every screen. `tabIndex={-1}` makes `main` a
          valid target for the skip link. */}
      <div className="pms-main">
        <main id={mainId} tabIndex={-1}>
          {children}
        </main>
        {footer}
      </div>

      {/* Dismissal only — never a tab stop, and hidden from assistive tech, which reaches
          the same exit through Escape. It closes through `closeDrawer` too: a click normally
          moves focus itself, but if it did not, focus would still be inside a hidden rail. */}
      {drawerOpen ? (
        <div className="pms-shell__scrim" aria-hidden="true" onClick={closeDrawer} />
      ) : null}
    </div>
  );
}
