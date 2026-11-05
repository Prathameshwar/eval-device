'use client';

import {
  useCallback,
  Fragment,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';

import { Avatar } from './Avatar';
import { ChevronDownIcon } from './icons-console';

export type UserMenuItem = { id: string; label: string; icon?: ReactNode; href?: string; separated?: boolean };

/**
 * The account menu. Hand-rolled rather than a popover library because the keyboard
 * contract *is* the component: a `role="menu"` that does not cycle with the arrow keys and
 * return focus on Escape is a worse control than a plain list of links.
 *
 * There is deliberately no focus trap — a menu is not a dialog, and Tab is expected to
 * leave it (and therefore to close it).
 */
export function UserMenu({
  name,
  secondary,
  email,
  items,
  onSelect,
}: {
  name: string;
  secondary?: string;
  /**
   * The signed-in address. Supplying it adds the identity block at the head of the open menu —
   * name, address, and the `secondary` line repeated — which is where a console user looks to
   * check *which* account they are on before acting.
   *
   * It is a prop rather than a free-form slot because the block belongs to the menu's own
   * chrome: a caller passing arbitrary markup would be styling the inside of this component, and
   * `role="menu"` has opinions about what may sit in it.
   */
  email?: string;
  items: UserMenuItem[];
  onSelect?: (id: string) => void;
}) {
  // An items array can arrive empty — every entry permission-filtered out at the call site,
  // say. `items.length - 1` is then -1, which left `activeIndex` outside the list and opened an
  // empty `role="menu"` with nothing focusable in it. A menu with no items simply does not open.
  const hasItems = items.length > 0;
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | HTMLAnchorElement | null>>([]);
  const menuId = useId();

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false);
    // Escape and selection put focus back where the user left it; an outside click does
    // not, because the click has already chosen the next focus target.
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    itemRefs.current[activeIndex]?.focus();
  }, [open, activeIndex]);

  useEffect(() => {
    if (!open) return;
    // `mousedown`, not `click`: dismiss before the press lands, so the click's real target
    // still receives it.
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  function onTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>): void {
    if (!hasItems) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex(0);
      setOpen(true);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex(items.length - 1);
      setOpen(true);
    }
    // Enter and Space are left to the button's native activation, which fires `onClick`.
  }

  function onMenuKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
    const last = items.length - 1;
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
        close(false);
        break;
      case ' ':
        // Anchors need menu-style Space activation; buttons already provide it natively.
        if (items[activeIndex]?.href) {
          event.preventDefault();
          itemRefs.current[activeIndex]?.click();
        }
        break;
      default:
        break;
    }
  }

  return (
    <div className="pms-usermenu" ref={rootRef}>
      <button
        type="button"
        ref={triggerRef}
        className="pms-usermenu__trigger"
        /*
         * Named explicitly rather than by its visible text, because that text is hidden in two
         * places — a collapsed rail and a narrow top bar — and a trigger whose accessible name
         * disappears with its label is an unlabelled button. `secondary` is deliberately left
         * out of the name: it is context, not identity.
         */
        aria-label={name}
        // With nothing to show, the trigger stops claiming to have a popup: `aria-haspopup`
        // on a control that never opens is a promise to a screen-reader user that is not kept.
        aria-haspopup={hasItems ? 'menu' : undefined}
        aria-expanded={hasItems ? open : undefined}
        aria-controls={open ? menuId : undefined}
        onClick={() => {
          if (!hasItems) return;
          setActiveIndex(0);
          setOpen((wasOpen) => !wasOpen);
        }}
        onKeyDown={onTriggerKeyDown}
      >
        <Avatar name={name} shape="round" size="sm" />
        <span className="pms-usermenu__text">
          <span className="pms-usermenu__name">{name}</span>
          {secondary ? <span className="pms-usermenu__secondary">{secondary}</span> : null}
        </span>
        <ChevronDownIcon className="pms-usermenu__chevron" size={16} />
      </button>

      {open && hasItems ? (
        <div
          className="pms-usermenu__menu"
          id={menuId}
          role="menu"
          aria-label={`${name} account menu`}
          onKeyDown={onMenuKeyDown}
        >
          {/*
           * `role="presentation"` strips this container's own semantics, because `role="menu"`
           * admits menu items, groups and separators — not arbitrary blocks. The text inside
           * still reaches assistive technology, and the trigger's accessible name remains the
           * authoritative statement of whose menu this is.
           */}
          {email ? (
            <div className="pms-usermenu__header" role="presentation">
              <span className="pms-usermenu__header-name">{name}</span>
              <span className="pms-usermenu__header-meta">{email}</span>
              {secondary ? (
                <span className="pms-usermenu__header-meta">{secondary}</span>
              ) : null}
            </div>
          ) : null}

          {items.map((item, index) => {
            const Element = item.href ? 'a' : 'button';
            return <Fragment key={item.id}>
            {item.separated ? <div role="separator" className="pms-usermenu__separator" /> : null}
            <Element
              href={item.href}
              type={item.href ? undefined : 'button'}
              role="menuitem"
              className="pms-usermenu__item"
              // One tab stop for the whole menu; the arrow keys move within it.
              tabIndex={index === activeIndex ? 0 : -1}
              onFocus={() => setActiveIndex(index)}
              ref={(element: HTMLButtonElement | HTMLAnchorElement | null) => {
                itemRefs.current[index] = element;
              }}
              onClick={() => {
                onSelect?.(item.id);
                close(true);
              }}
            >
              {item.icon ? (
                <span className="pms-usermenu__item-icon" aria-hidden="true">
                  {item.icon}
                </span>
              ) : null}
              <span>{item.label}</span>
            </Element>
            {item.separated ? <div role="separator" className="pms-usermenu__separator" /> : null}
            </Fragment>;
          })}
        </div>
      ) : null}
    </div>
  );
}
