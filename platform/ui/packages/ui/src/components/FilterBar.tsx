import type { ReactNode } from 'react';
import { Button } from './Button';
import { FilterChip } from './FilterChip';

export type AppliedFilter = {
  /** Stable identity of this predicate — the React key, and what `onRemove` reports. */
  id: string;
  /** The field, in the reader's words: "Status", "Posted on". */
  label: string;
  /** The value, already formatted through the shared formatters — never a raw decimal or ISO date. */
  value: string;
  /** The comparison, when it is not equality: "is any of", "on or after". */
  operator?: string;
  /**
   * Imposed by the screen rather than chosen — the company scope of a list, a status a page is
   * dedicated to. It is still shown, because a filtered list must say what it excludes, but it
   * has no remove button and "Clear all" leaves it alone.
   */
  fixed?: boolean;
};

type FilterBarProps = {
  /** The controls this list filters by — `TableSearch`, selects, a date range. */
  children?: ReactNode;
  /** Every predicate the query carries, including the ones that arrived in the URL. */
  applied?: readonly AppliedFilter[];
  onRemove?: (id: string) => void;
  onClearAll?: () => void;
  /** Trailing actions such as Apply/Clear, columns or export. Wraps as a group after the fields. */
  actions?: ReactNode;
};

/**
 * The strip above a table: what narrows the list, and an account of what is currently narrowing it.
 *
 * The chip row is the point of this component. A list that is filtered without saying so is the
 * most common cause of "the record is missing" — and because a filter can arrive from the URL, from
 * a saved view, or from the screen itself, the reader may never have chosen the one hiding their
 * row. So every predicate in force gets a chip, and removing a chip is the only way to lift one.
 */
export function FilterBar({
  children,
  applied = [],
  onRemove,
  onClearAll,
  actions,
}: FilterBarProps) {
  /* "Clear all" is offered only when it would actually do something. A screen-imposed filter is
   * not clearable, so a bar holding nothing but those does not grow a button that changes nothing. */
  const removable = applied.filter((filter) => !filter.fixed);

  return (
    <div className="pms-filter-bar">
      {children || actions ? (
        <div className="pms-filter-bar__row">
          {children ? <div className="pms-filter-bar__controls">{children}</div> : null}
          {actions ? <div className="pms-filter-bar__actions">{actions}</div> : null}
        </div>
      ) : null}

      {applied.length > 0 ? (
        /*
         * A group, named: a bare row of chips is a pile of unrelated buttons to a screen reader,
         * and the name is what makes it "the filters in force" rather than "eight remove buttons".
         */
        <div className="pms-filter-bar__chips" role="group" aria-label="Filters in force">
          {applied.map((filter) => (
            <FilterChip
              key={filter.id}
              label={filter.label}
              value={filter.value}
              operator={filter.operator}
              onRemove={filter.fixed || !onRemove ? undefined : () => onRemove(filter.id)}
            />
          ))}
          {onClearAll && removable.length > 1 ? (
            <Button variant="ghost" className="pms-filter-bar__clear" onClick={onClearAll}>
              Clear all
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
