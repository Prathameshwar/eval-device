'use client';

import { useLayoutEffect, useState, type CSSProperties, type RefObject } from 'react';

/**
 * Places a portalled panel against an anchor, in the viewport rather than in the anchor's parent.
 *
 * Absolute positioning inside the parent is what made `UserMenu` render as a clipped sliver
 * inside the top bar: any ancestor with `overflow` clips a descendant popover. A picker, a menu
 * and a row kebab all sit inside cards, toolbars and scroll regions — and `DataTable`'s own
 * horizontal scroller is exactly such an ancestor — so a panel cannot depend on its ancestors.
 * Hence a portal, `position: fixed`, and re-placing on **capture-phase** scroll so an ancestor
 * scrolling counts too.
 *
 * Shared because this is the second control that needs it (`SearchSelect`, then `Menu`), and two
 * copies of viewport flipping is how they drift apart.
 */

/** Geometry only — no token can express a rectangle measured at runtime. */
export type Placement = { style: CSSProperties; flipped: boolean };

export type PlacementOptions = {
  /**
   * The panel spans the anchor's width — a dropdown *list*, whose rows belong to the field above
   * them. A menu instead takes its own width and lines up by `align`.
   */
  matchWidth?: boolean;
  /** Which anchor edge an intrinsic-width panel lines up with. Ignored when `matchWidth`. */
  align?: 'start' | 'end';
  gap?: number;
  minHeight?: number;
  maxHeight?: number;
  /** Below this much room beneath the anchor, the panel may flip above it. */
  flipBelow?: number;
};

/**
 * Whether two measurements would paint the same panel.
 *
 * `place()` runs on every capture-phase scroll event, and returning a fresh object each time is a
 * fresh render of the anchor *and* every row on screen — for a rectangle that, while someone
 * scrolls a page with the panel open, usually has not moved. Comparing six numbers is far cheaper
 * than re-rendering two hundred options per scroll frame.
 */
function samePlacement(a: Placement, b: Placement): boolean {
  return (
    a.flipped === b.flipped &&
    a.style.left === b.style.left &&
    a.style.right === b.style.right &&
    a.style.width === b.style.width &&
    a.style.maxHeight === b.style.maxHeight &&
    a.style.top === b.style.top &&
    a.style.bottom === b.style.bottom
  );
}

export function usePlacement(
  anchor: RefObject<HTMLElement | null>,
  open: boolean,
  options: PlacementOptions = {},
): Placement | null {
  const {
    matchWidth = false,
    align = 'start',
    gap = 6,
    minHeight = 120,
    maxHeight = 340,
    flipBelow = 200,
  } = options;
  const [placement, setPlacement] = useState<Placement | null>(null);

  useLayoutEffect(() => {
    const node = anchor.current;
    if (!open || !node) {
      setPlacement(null);
      return;
    }

    const place = () => {
      const rect = node.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom - gap;
      const above = rect.top - gap;
      // Flip only when below is genuinely too tight and above is roomier — flipping on a
      // near-tie makes the panel appear to jump as the page scrolls.
      const flipped = below < flipBelow && above > below;
      const room = Math.max(minHeight, Math.min(maxHeight, flipped ? above : below));

      // `right` rather than a computed `left`, so an intrinsic-width menu stays pinned to the
      // anchor's trailing edge whatever it measures — a kebab at the end of a row must not
      // hang off the page because its longest label grew.
      const across: CSSProperties = matchWidth
        ? { left: rect.left, width: rect.width }
        : align === 'end'
          ? { right: Math.max(0, window.innerWidth - rect.right) }
          : { left: rect.left };

      const next: Placement = {
        flipped,
        style: {
          position: 'fixed',
          ...across,
          maxHeight: room,
          ...(flipped ? { bottom: window.innerHeight - rect.top + gap } : { top: rect.bottom + gap }),
        },
      };
      setPlacement((prev) => (prev && samePlacement(prev, next) ? prev : next));
    };

    place();
    /* Passive, because nothing in here calls `preventDefault`: a non-passive scroll listener on
     * the document keeps the browser from scrolling until it has run. */
    window.addEventListener('scroll', place, { capture: true, passive: true });
    window.addEventListener('resize', place, { passive: true });
    // jsdom has no ResizeObserver, and an anchor that never resizes is not worth a polyfill.
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(place);
    observer?.observe(node);

    return () => {
      window.removeEventListener('scroll', place, { capture: true });
      window.removeEventListener('resize', place);
      observer?.disconnect();
    };
  }, [anchor, open, matchWidth, align, gap, minHeight, maxHeight, flipBelow]);

  return placement;
}
