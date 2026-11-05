import { CloseIcon } from './icons-console';

type FilterChipProps = {
  /** The field being filtered, in the user's words — "Status", "Posted on". */
  label: string;
  /**
   * The applied value, already formatted. A money or date filter must arrive through the shared
   * formatters like every other figure, so this component never sees a raw decimal string.
   */
  value: string;
  /**
   * How the value is being compared, when it is not equality: "is any of", "on or after".
   * Omitted for `eq`, where "Status: Posted" already reads correctly.
   */
  operator?: string;
  /** Omit to render a fixed chip — a filter forced by the screen, which a user may not lift. */
  onRemove?: () => void;
};

/**
 * One applied filter, shown above the table.
 *
 * Chips exist because a filtered list that does not say it is filtered is the most common cause
 * of "the record is missing". Every predicate the query carries has a chip, including one that
 * arrived from the URL, and removing a chip is the only way to lift a filter — so the set of
 * chips is a complete and honest account of what is being excluded.
 */
export function FilterChip({ label, value, operator, onRemove }: FilterChipProps) {
  return (
    <span className="pms-filter-chip">
      <span className="pms-filter-chip__label">{label}</span>
      {/* No `aria-hidden` on the operator: "Posted on 01 Apr 2026" and "Posted on or after
          01 Apr 2026" are different filters, and the difference is only in this word. */}
      <span className="pms-filter-chip__op">{operator ?? 'is'}</span>
      <span className="pms-filter-chip__value">{value}</span>
      {onRemove ? (
        <button
          type="button"
          className="pms-filter-chip__remove"
          // Named, not "Remove": a row of eight identical "Remove" buttons is unusable on a
          // screen reader, and the whole chip list is one of those rows.
          aria-label={`Remove filter: ${label} ${operator ?? 'is'} ${value}`}
          onClick={onRemove}
        >
          <CloseIcon size={12} />
        </button>
      ) : null}
    </span>
  );
}
