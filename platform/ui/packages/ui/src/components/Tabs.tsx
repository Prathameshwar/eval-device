'use client';

import { useId, useRef, type KeyboardEvent } from 'react';

export type Tab = { id: string; label: string };

/**
 * The DOM id of a tab button. Pass the same unique panel id as the scope on both sides of the
 * relationship. Tabs without a panel use a generated instance scope. A panel points back with
 * `aria-labelledby={tabButtonId(active, panelId)}`, which is the other half of the pattern: without it a
 * `role="tabpanel"` is an unnamed region.
 */
export function tabButtonId(id: string, scope?: string): string {
  return scope === undefined
    ? `pms-tab-${encodeURIComponent(id)}`
    : `pms-tab-${scope.length}-${encodeURIComponent(scope)}--${encodeURIComponent(id)}`;
}

type TabsProps = {
  tabs: ReadonlyArray<Tab>;
  /** The selected tab's `id`. Tabs are client state, not routes. */
  active: string;
  onChange: (id: string) => void;
  /** The tablist's accessible name. A tablist without one is an unnamed group. */
  label: string;
  /**
   * The `id` of the element holding the tabs' content. Given one, every tab declares
   * `aria-controls`, which is what makes `aria-selected="true"` a promise the component can
   * keep: the caller renders that element with `role="tabpanel"` and
   * `aria-labelledby={tabButtonId(active, panelId)}`. Omitted when the tabs drive something that is not
   * a single panel — better no `aria-controls` than one pointing at nothing.
   */
  panelId?: string;
};

/**
 * Underline tabs with the real ARIA tab pattern: one tab stop for the whole list, arrow keys
 * that move *and* activate with wrapping, Home/End to the ends. The roles alone are not the
 * pattern — a tablist that needs Tab to reach each tab is a row of buttons,
 * and a `role="tab"` with no panel to control is a state change announced but never made.
 */
export function Tabs({ tabs, active, onChange, label, panelId }: TabsProps) {
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const autoId = useId();
  const scope = panelId ?? autoId;
  const tabStop = Math.max(0, tabs.findIndex((tab) => tab.id === active));

  const activateAt = (index: number): void => {
    const tab = tabs[index];
    if (!tab) return;
    onChange(tab.id);
    // Activation follows focus here, so focus has to follow the arrow key too.
    buttons.current[index]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number): void => {
    const last = tabs.length - 1;
    let next: number | null = null;

    switch (event.key) {
      case 'ArrowRight':
        next = index === last ? 0 : index + 1;
        break;
      case 'ArrowLeft':
        next = index === 0 ? last : index - 1;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = last;
        break;
      default:
        return;
    }

    event.preventDefault();
    activateAt(next);
  };

  return (
    <div className="pms-tabs" role="tablist" aria-label={label}>
      {tabs.map((tab, index) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            ref={(node) => {
              buttons.current[index] = node;
            }}
            type="button"
            role="tab"
            id={tabButtonId(tab.id, scope)}
            className="pms-tabs__tab"
            aria-selected={selected}
            aria-controls={panelId}
            tabIndex={index === tabStop ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
