'use client';

import {
  Fragment,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { useGranted } from '../lib/permissions';
import { usePlacement } from '../lib/placement';
import { IconButton } from './IconButton';
import { CheckIcon } from './icons';
import { ChevronDownIcon } from './icons-console';
import { MoreVerticalIcon } from './icons-table';

export type MenuItem = {
  id: string;
  label: string;
  icon?: ReactNode;
  /**
   * Why this item cannot be used *right now* — "already posted", "no open period". Disables the
   * item and is shown beneath the label. Required rather than a bare boolean on purpose: a greyed
   * row with no explanation is a support ticket, and the reason is always known at the call site.
   */
  disabledReason?: string;
  /** Danger tone, and separated from the ordinary verbs above it. */
  destructive?: boolean;
  /**
   * Makes this item a checkbox rather than a verb — a column in the column picker, a saved-view
   * toggle. Two things follow from it, both from the WAI-ARIA menu pattern: the item is a
   * `menuitemcheckbox` carrying its own state, and choosing it **does not close the menu**, because
   * the point of a list of toggles is to set more than one.
   */
  checked?: boolean;
  /**
   * Presentation gate. The item is **absent**, not disabled, when the actor lacks the key — a
   * disabled control still tells them the capability exists. The server enforces regardless
   * (see `lib/permissions`).
   */
  permission?: string;
};

type MenuProps = {
  /**
   * The trigger's accessible name, and the menu's. Required: the default trigger is icon-only,
   * so there is no visible text to fall back on.
   */
  label: string;
  items: readonly MenuItem[];
  onSelect: (id: string) => void;
  /** Visible trigger text. With it the trigger is a labelled button with a caret; without, an icon. */
  triggerLabel?: string;
  /** Overrides the kebab — `ColumnsIcon` for the column picker, say. */
  icon?: ReactNode;
  /**
   * Icon-trigger emphasis, matching `IconButton`. Ignored when `triggerLabel` is set: a labelled
   * trigger is always the outlined `ghost` button, since a borderless one beside a toolbar's other
   * buttons reads as text rather than as a control.
   */
  variant?: 'ghost' | 'outline';
  /**
   * Which trigger edge the panel lines up with. `end` by default, because the common case is the
   * last column of a table or the right end of a toolbar, where a `start`-aligned panel would
   * hang off the page.
   */
  align?: 'start' | 'end';
  disabled?: boolean;
};

/**
 * A popover menu: the row kebab and the toolbar overflow.
 *
 * Hand-rolled rather than a popover library, for the same reason as `UserMenu` — the keyboard
 * contract *is* the component. Two things it does that `UserMenu` does not, and both are why this
 * exists as a second control rather than a prop on that one:
 *
 *  - **It portals.** A row kebab lives inside `DataTable`'s horizontal scroller, and any ancestor
 *    with `overflow` clips an absolutely positioned descendant. `UserMenu` rendering as a clipped
 *    sliver inside the top bar is the same bug (see `lib/placement`).
 *  - **Items carry a permission and a disabled reason,** because a row's verbs are conditional in
 *    a way an account menu's never are.
 *
 * An item may also be a checkbox (`checked`), which is what the column picker is built from rather
 * than a second popover implementation — the keyboard contract is the expensive part, and it is
 * identical for a list of verbs and a list of toggles.
 *
 * Deliberately no focus trap: a menu is not a dialog, and Tab is expected to leave it.
 */
export function Menu({
  label,
  items,
  onSelect,
  triggerLabel,
  icon,
  variant = 'ghost',
  align = 'end',
  disabled = false,
}: MenuProps) {
  const granted = useGranted();
  /*
   * Permission-filtered before anything else measures the list, so `activeIndex` and the
   * "is there anything to show" test both speak about what is actually rendered. Filtering at
   * render time instead left the roving index pointing past the end of a shortened list.
   */
  const visible = items.filter((item) => granted(item.permission));

  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const menuId = useId();

  // A menu with nothing in it does not open, and stops claiming to have a popup: `aria-haspopup`
  // on a control that never opens is a promise to a screen-reader user that is not kept.
  const usable = !disabled && visible.length > 0;
  const placement = usePlacement(triggerRef, open, { align, minHeight: 80 });
  /*
   * Placement is measured in a layout effect, so the first render after `open` has none and the
   * panel is not in the DOM yet. Everything that touches an item — focus, above all — has to wait
   * for this rather than for `open`, or it runs against refs that are still null.
   */
  const mounted = open && usable && placement !== null;

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false);
    // Escape and selection put focus back where the user left it; an outside click does not,
    // because the click has already chosen the next focus target.
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!mounted) return;
    itemRefs.current[activeIndex]?.focus();
  }, [mounted, activeIndex]);

  /* An items array can shrink while the menu is open — a row's actions re-resolving after a
   * refetch. Clamping here keeps the roving index inside the list rather than focusing nothing. */
  useEffect(() => {
    setActiveIndex((index) => (index > visible.length - 1 ? Math.max(0, visible.length - 1) : index));
  }, [visible.length]);

  useEffect(() => {
    if (!open) return;
    // `mousedown`, not `click`: dismiss before the press lands, so the click's real target still
    // receives it. Both the trigger and the portalled panel count as inside — the panel is not a
    // DOM descendant of the trigger, so testing one element would close the menu on its own items.
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  function openAt(index: number): void {
    if (!usable) return;
    setActiveIndex(index);
    setOpen(true);
  }

  function onTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>): void {
    if (!usable) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      openAt(0);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      openAt(visible.length - 1);
    }
    // Enter and Space are left to the button's native activation, which fires `onClick`.
  }

  function onPanelKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
    const last = visible.length - 1;
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setActiveIndex((index) => (index >= last ? 0 : index + 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setActiveIndex((index) => (index <= 0 ? last : index - 1));
        break;
      case 'Home':
        event.preventDefault();
        setActiveIndex(0);
        break;
      case 'End':
        event.preventDefault();
        setActiveIndex(last);
        break;
      case 'Escape':
        event.preventDefault();
        close(true);
        break;
      case 'Tab':
        /*
         * Deliberately not prevented. The panel is portalled to the end of the body, so letting
         * Tab run from a menu item would jump to the end of the document. Moving focus back to
         * the trigger *synchronously*, before the default action, makes the browser compute the
         * next tab stop from the trigger instead — which is where the user expects to continue.
         */
        close(true);
        break;
      default:
        break;
    }
  }

  function choose(item: MenuItem): void {
    // `aria-disabled` rather than `disabled`, so the item stays focusable and its reason is
    // readable (WAI-ARIA menu pattern) — which means activation has to be refused here.
    if (item.disabledReason) return;
    onSelect(item.id);
    // A checkbox item leaves the menu open: the reader is setting a set, not choosing a verb, and
    // reopening the panel between every column would make hiding three of them three round trips.
    if (item.checked === undefined) close(true);
  }

  const triggerProps = {
    'aria-haspopup': usable ? ('menu' as const) : undefined,
    'aria-expanded': usable ? open : undefined,
    'aria-controls': open ? menuId : undefined,
    disabled,
    onClick: () => (open ? close(false) : openAt(0)),
    onKeyDown: onTriggerKeyDown,
  };

  // The index of the first destructive item, so one separator divides the ordinary verbs from
  // the dangerous ones. Computed once rather than per row.
  const firstDestructive = visible.findIndex((item) => item.destructive);

  const panel =
    mounted && placement ? (
      <div
        ref={panelRef}
        id={menuId}
        className="pms-menu__panel"
        role="menu"
        aria-label={label}
        data-flipped={placement.flipped ? 'true' : undefined}
        style={placement.style}
        onKeyDown={onPanelKeyDown}
      >
        {visible.map((item, index) => (
          // A fragment, not a wrapper element: `role="menu"` requires its `menuitem`s as
          // children, and a generic div between them breaks that relationship.
          <Fragment key={item.id}>
            {index === firstDestructive && index > 0 ? (
              <div className="pms-menu__sep" role="separator" />
            ) : null}
            <button
              type="button"
              role={item.checked === undefined ? 'menuitem' : 'menuitemcheckbox'}
              aria-checked={item.checked}
              className="pms-menu__item"
              data-tone={item.destructive ? 'danger' : undefined}
              aria-disabled={item.disabledReason ? true : undefined}
              // One tab stop for the whole menu; the arrow keys move within it.
              tabIndex={index === activeIndex ? 0 : -1}
              ref={(element) => {
                itemRefs.current[index] = element;
              }}
              onClick={() => choose(item)}
            >
              {/* A checkbox item's state has to be *visible*, not only in `aria-checked`. The slot
                * is kept when unchecked so the labels of a toggle list stay in one column. */}
              {item.checked === undefined ? (
                item.icon ? (
                  <span className="pms-menu__item-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                ) : null
              ) : (
                <span className="pms-menu__item-check" aria-hidden="true">
                  {item.checked ? <CheckIcon size={14} /> : null}
                </span>
              )}
              <span className="pms-menu__item-text">
                <span>{item.label}</span>
                {item.disabledReason ? (
                  <span className="pms-menu__item-note">{item.disabledReason}</span>
                ) : null}
              </span>
            </button>
          </Fragment>
        ))}
      </div>
    ) : null;

  return (
    <span className="pms-menu">
      {triggerLabel === undefined ? (
        <IconButton
          ref={triggerRef}
          label={label}
          icon={icon ?? <MoreVerticalIcon size={18} />}
          variant={variant}
          {...triggerProps}
        />
      ) : (
        <button
          ref={triggerRef}
          type="button"
          className="pms-btn pms-btn--ghost pms-menu__trigger"
          {...triggerProps}
        >
          {icon ? (
            <span className="pms-menu__trigger-icon" aria-hidden="true">
              {icon}
            </span>
          ) : null}
          {triggerLabel}
          <ChevronDownIcon size={14} />
        </button>
      )}
      {panel && typeof document !== 'undefined' ? createPortal(panel, document.body) : null}
    </span>
  );
}
