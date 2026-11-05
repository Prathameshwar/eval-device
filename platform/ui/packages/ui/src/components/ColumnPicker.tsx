'use client';

import { useGranted } from '../lib/permissions';
import type { Column } from '../lib/table';
import { Menu, type MenuItem } from './Menu';
import { ColumnsIcon } from './icons-table';

const RESET = '__reset';

export type ColumnPickerProps<Row> = {
  /** Every column the table could show, in declaration order — `useColumnPreferences().choices`. */
  columns: readonly Column<Row>[];
  /** The keys currently turned off — `useColumnPreferences().hidden`. */
  hidden: ReadonlySet<string>;
  onToggle: (key: string) => void;
  /** Offers "Reset columns". Omit it and the entry is absent rather than dead. */
  onReset?: () => void;
  label?: string;
};

/**
 * Which columns a wide table shows.
 *
 * A `Menu` of checkbox items rather than a popover of its own: a menu of toggles is the WAI-ARIA
 * pattern for exactly this, so the panel stays open while several are set, and the keyboard contract
 * — the expensive part — is not written a second time.
 *
 * A column the actor may not read is not offered, for the same reason the table does not draw it:
 * the field never arrives in the payload, so a toggle for it would reveal that it exists and then do
 * nothing.
 */
export function ColumnPicker<Row>({
  columns,
  hidden,
  onToggle,
  onReset,
  label = 'Columns',
}: ColumnPickerProps<Row>) {
  const granted = useGranted();
  const offered = columns.filter((column) => granted(column.permission));
  const shownCount = offered.filter((column) => !hidden.has(column.key)).length;

  const items: MenuItem[] = offered.map((column) => ({
    id: column.key,
    label: column.header,
    checked: !hidden.has(column.key),
    /*
     * The reason is stated, not merely enforced. `useColumnPreferences` refuses both of these too —
     * it is the authority, this is the explanation — because a screen can call `toggle` directly.
     */
    disabledReason: column.locked
      ? 'Always shown'
      : shownCount <= 1 && !hidden.has(column.key)
        ? 'At least one column must be shown'
        : undefined,
  }));

  if (onReset) {
    // Not a checkbox item, so choosing it closes the menu — it is a verb, and the panel it would
    // stay open for has just been rewritten under the reader.
    items.push({ id: RESET, label: 'Reset columns' });
  }

  return (
    <Menu
      label={label}
      triggerLabel={label}
      icon={<ColumnsIcon size={14} />}
      items={items}
      onSelect={(id) => (id === RESET ? onReset?.() : onToggle(id))}
    />
  );
}
