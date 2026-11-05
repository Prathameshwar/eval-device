/**
 * `ColumnPicker` and `useColumnPreferences` — which columns a wide table shows.
 *
 * The hook is the authority and the picker is the explanation: both refuse a locked column and both
 * refuse to hide the last column standing, because a screen can call `toggle` directly. The stored
 * set is treated as untrusted input throughout — it comes from a store the reader can edit — and it
 * is layout only: hiding a column here changes what is drawn and nothing about what the API returns.
 */
import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ColumnPicker, type ColumnPickerProps } from '../src/components/ColumnPicker';
import { columnPrefsKey, useColumnPreferences } from '../src/lib/column-prefs';
import { PermissionProvider } from '../src/lib/permissions';
import type { Column } from '../src/lib/table';

type Invoice = { id: string; number: string; customer: string; notes: string; margin: string };

const COLUMNS: readonly Column<Invoice>[] = [
  { key: 'number', header: 'Number', type: 'code', locked: true },
  { key: 'customer', header: 'Customer' },
  { key: 'notes', header: 'Notes', hidden: true },
  { key: 'margin', header: 'Margin', type: 'money', permission: 'invoice.read_margin' },
];

const TABLE_ID = 'invoices';

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

/* ---------- the control ---------- */

function openPicker(
  props: Partial<ColumnPickerProps<Invoice>> = {},
  permissions: readonly string[] = ['*'],
) {
  const onToggle = vi.fn();
  render(
    <PermissionProvider permissions={permissions}>
      <ColumnPicker<Invoice>
        columns={COLUMNS}
        hidden={new Set(['notes'])}
        onToggle={onToggle}
        {...props}
      />
    </PermissionProvider>,
  );
  return { onToggle, trigger: screen.getByRole('button', { name: /Columns/ }) };
}

describe('ColumnPicker', () => {
  it('shows every column the actor may read, ticked according to what is on', async () => {
    const user = userEvent.setup();
    const { trigger } = openPicker();

    await user.click(trigger);

    expect(screen.getByRole('menuitemcheckbox', { name: /Customer/ })).toBeChecked();
    expect(screen.getByRole('menuitemcheckbox', { name: /Notes/ })).not.toBeChecked();
  });

  it('does not offer a column the actor may not read', async () => {
    const user = userEvent.setup();
    // The field never arrives in the payload, so a toggle for it would reveal that it exists and
    // then do nothing.
    const { trigger } = openPicker({}, ['invoice.read']);

    await user.click(trigger);

    expect(screen.queryByRole('menuitemcheckbox', { name: /Margin/ })).not.toBeInTheDocument();
    expect(screen.getByRole('menuitemcheckbox', { name: /Customer/ })).toBeInTheDocument();
  });

  it('reports the key and stays open, so several can be set in one visit', async () => {
    const user = userEvent.setup();
    const { trigger, onToggle } = openPicker();
    await user.click(trigger);

    await user.click(screen.getByRole('menuitemcheckbox', { name: /Notes/ }));

    expect(onToggle).toHaveBeenCalledWith('notes');
    expect(screen.getByRole('menu')).toBeInTheDocument();

    await user.click(screen.getByRole('menuitemcheckbox', { name: /Margin/ }));
    expect(onToggle).toHaveBeenCalledWith('margin');
  });

  it('says why the identifying column cannot be turned off, and refuses it', async () => {
    const user = userEvent.setup();
    const { trigger, onToggle } = openPicker();
    await user.click(trigger);

    const number = screen.getByRole('menuitemcheckbox', { name: /Number/ });
    expect(number).toHaveTextContent('Always shown');
    expect(number).toHaveAttribute('aria-disabled', 'true');

    await user.click(number);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('says why the last column standing cannot be turned off', async () => {
    const user = userEvent.setup();
    const { trigger, onToggle } = openPicker({
      columns: [
        { key: 'customer', header: 'Customer' },
        { key: 'notes', header: 'Notes' },
      ],
      hidden: new Set(['notes']),
    });
    await user.click(trigger);

    const customer = screen.getByRole('menuitemcheckbox', { name: /Customer/ });
    expect(customer).toHaveTextContent('At least one column must be shown');

    await user.click(customer);
    expect(onToggle).not.toHaveBeenCalled();
    // The one that is off can still be turned back on.
    await user.click(screen.getByRole('menuitemcheckbox', { name: /Notes/ }));
    expect(onToggle).toHaveBeenCalledWith('notes');
  });

  it('offers the way back only when the screen can honour it', async () => {
    const user = userEvent.setup();
    const { trigger } = openPicker();
    await user.click(trigger);

    expect(screen.queryByRole('menuitem', { name: 'Reset columns' })).not.toBeInTheDocument();
  });

  it('closes on Reset, because the panel it would stay open for has just been rewritten', async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    const { trigger } = openPicker({ onReset });
    await user.click(trigger);

    await user.click(screen.getByRole('menuitem', { name: 'Reset columns' }));

    expect(onReset).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('takes its own trigger wording when a screen names it differently', () => {
    render(
      <ColumnPicker<Invoice>
        columns={COLUMNS}
        hidden={new Set<string>()}
        onToggle={vi.fn()}
        label="Fields"
      />,
    );

    expect(screen.getByRole('button', { name: /Fields/ })).toBeInTheDocument();
  });
});

/* ---------- the preference store ---------- */

describe('useColumnPreferences', () => {
  it('starts from the columns as the screen declared them', () => {
    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    expect(result.current.columns.map((column) => column.key)).toEqual([
      'number',
      'customer',
      'margin',
    ]);
    // The picker is offered every column, hidden ones included.
    expect(result.current.choices).toHaveLength(4);
    expect(result.current.hidden).toEqual(new Set(['notes']));
  });

  it('adopts the remembered layout after the first paint, not during it', () => {
    window.localStorage.setItem(columnPrefsKey(TABLE_ID), JSON.stringify(['customer']));

    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    // Reading storage in the initial state would make the server and client disagree, so the
    // remembered set arrives in an effect — by which point `notes` is back, because the reader's
    // stored opinion replaces the column's own default rather than merging with it.
    expect(result.current.hidden).toEqual(new Set(['customer']));
    expect(result.current.columns.map((column) => column.key)).toEqual([
      'number',
      'notes',
      'margin',
    ]);
  });

  it('keeps each table’s layout under its own key', () => {
    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    act(() => result.current.toggle('customer'));

    expect(window.localStorage.getItem('pms.table.invoices.hidden')).toBe(
      JSON.stringify(['notes', 'customer']),
    );
    expect(columnPrefsKey('audit-events')).toBe('pms.table.audit-events.hidden');
  });

  it('turns a column off and back on', () => {
    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    act(() => result.current.toggle('notes'));
    expect(result.current.columns.map((column) => column.key)).toContain('notes');

    act(() => result.current.toggle('notes'));
    expect(result.current.columns.map((column) => column.key)).not.toContain('notes');
  });

  it('refuses a key it does not know — the stored set is untrusted input', () => {
    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    act(() => result.current.toggle('total_amount'));

    expect(result.current.hidden).toEqual(new Set(['notes']));
    expect(window.localStorage.getItem(columnPrefsKey(TABLE_ID))).toBeNull();
  });

  it('refuses the identifying column even when asked directly', () => {
    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    // `toggle` is the authority: the picker disabling the item is the explanation, not the guard.
    act(() => result.current.toggle('number'));

    expect(result.current.columns.map((column) => column.key)).toContain('number');
  });

  it('never hides the last column standing, which would leave nothing to recover from', () => {
    const two: readonly Column<Invoice>[] = [
      { key: 'customer', header: 'Customer' },
      { key: 'notes', header: 'Notes' },
    ];
    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, two));

    act(() => result.current.toggle('customer'));
    expect(result.current.columns.map((column) => column.key)).toEqual(['notes']);

    act(() => result.current.toggle('notes'));
    expect(result.current.columns.map((column) => column.key)).toEqual(['notes']);
  });

  it('ignores a stored key for a locked column, however it got there', () => {
    window.localStorage.setItem(columnPrefsKey(TABLE_ID), JSON.stringify(['number', 'unknown']));

    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    expect(result.current.columns.map((column) => column.key)).toContain('number');
    expect(result.current.hidden.has('number')).toBe(false);
  });

  it('goes back to the declared defaults on reset', () => {
    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    act(() => result.current.toggle('notes'));
    act(() => result.current.toggle('customer'));
    act(() => result.current.reset());

    expect(result.current.hidden).toEqual(new Set(['notes']));
    expect(window.localStorage.getItem(columnPrefsKey(TABLE_ID))).toBe(JSON.stringify(['notes']));
  });

  it('renders through a browser that refuses storage', () => {
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new Error('storage denied');
    });
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('storage denied');
    });

    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));
    // A preference that cannot be saved does not survive the tab; an exception out of a click
    // handler would take the screen down with it.
    expect(() => act(() => result.current.toggle('customer'))).not.toThrow();
    expect(result.current.hidden).toEqual(new Set(['notes', 'customer']));
  });

  it('ignores a stored value that is not a list of keys', () => {
    window.localStorage.setItem(columnPrefsKey(TABLE_ID), '{"notes":true}');

    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    expect(result.current.hidden).toEqual(new Set(['notes']));
  });

  it('keeps a separate layout per table id', () => {
    window.localStorage.setItem(columnPrefsKey('other'), JSON.stringify(['customer']));

    const { result } = renderHook(() => useColumnPreferences(TABLE_ID, COLUMNS));

    expect(result.current.hidden).toEqual(new Set(['notes']));
  });
});
