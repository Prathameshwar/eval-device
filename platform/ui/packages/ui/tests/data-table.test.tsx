/**
 * `DataTable` — the shared table.
 *
 * The behaviours worth testing here are the ones a screen would otherwise get wrong on its own,
 * one page at a time:
 *
 *  - **A missing value is an em dash and a zero is a zero.** Every list-item field except `id` is
 *    nullable, so this is the common path, and getting it backwards is a money defect rather than
 *    a cosmetic one.
 *  - **Formatting comes from the config, never the environment** — amounts, quantities, business
 *    dates and instants all go through the bound formatters.
 *  - **Each of the four states is a distinct, intended screen**, not a blank body.
 *  - **A column the actor may not read is absent**, and a row that can no longer change says so.
 *
 * The suite runs with `css: false`, so anything structural that only CSS can express — the height
 * cap that makes the frozen header work, the clipped heading row in the stacked layout — is
 * asserted against the stylesheet text instead.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DataTable } from '../src/components/DataTable';
import { DisplayConfigProvider } from '../src/lib/display-config';
import { PermissionProvider } from '../src/lib/permissions';
import type { Column } from '../src/lib/table';

const TABLE_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'table.css'), 'utf8');

const EM_DASH = '—';

type Invoice = {
  id: string;
  number: string | null;
  customer: string | null;
  total: string | null;
  currency: string | null;
  quantity: string | null;
  margin: string | null;
  status: string | null;
  tags: readonly string[];
  collected: string | null;
  postedOn: string | null;
  createdAt: string | null;
  recurring: boolean | null;
  card: string | null;
};

const INVOICE: Invoice = {
  id: 'inv-1',
  number: 'INV-2026-0004',
  customer: 'Northwind Traders Private Limited',
  total: '1234567.895',
  currency: 'INR',
  quantity: '2.5',
  margin: '18.55',
  status: 'POSTED',
  tags: ['GST', 'EXPORT', 'REVERSE_CHARGE', 'SEZ', 'RCM'],
  collected: '250000',
  postedOn: '2026-03-31',
  createdAt: '2026-03-05T18:30:00Z',
  recurring: true,
  card: '4242',
};

/** A row where every nullable field is null — the case the API contract makes ordinary. */
const BLANK_INVOICE: Invoice = {
  id: 'inv-blank',
  number: null,
  customer: null,
  total: null,
  currency: null,
  quantity: null,
  margin: null,
  status: null,
  tags: [],
  collected: null,
  postedOn: null,
  createdAt: null,
  recurring: null,
  card: null,
};

const COLUMNS: readonly Column<Invoice>[] = [
  { key: 'number', header: 'Number', type: 'code' },
  { key: 'customer', header: 'Customer', truncate: true },
  { key: 'total', header: 'Total', type: 'money', currencyKey: 'currency' },
  { key: 'quantity', header: 'Qty', type: 'quantity' },
  { key: 'margin', header: 'Margin', type: 'percent' },
  {
    key: 'status',
    header: 'Status',
    type: 'status',
    tone: (value) => (value === 'POSTED' ? 'success' : 'neutral'),
    label: (value) => (value === 'POSTED' ? 'Posted' : value),
  },
  { key: 'tags', header: 'Tags', type: 'chips' },
  { key: 'collected', header: 'Collected', type: 'meter', total: (row) => row.total },
  { key: 'postedOn', header: 'Posted on', type: 'date' },
  { key: 'createdAt', header: 'Created', type: 'datetime' },
  { key: 'recurring', header: 'Recurring', type: 'boolean' },
  { key: 'card', header: 'Card', type: 'masked' },
];

const wrap = (node: ReactNode, permissions: readonly string[] = ['*']) =>
  render(
    <PermissionProvider permissions={permissions}>
      <DisplayConfigProvider>{node}</DisplayConfigProvider>
    </PermissionProvider>,
  );

/** A body cell, by the heading it belongs to. `data-label` is the same string the header shows. */
const cell = (container: HTMLElement, header: string): HTMLElement => {
  const found = container.querySelector<HTMLElement>(`tbody td[data-label="${header}"]`);
  if (found === null) throw new Error(`no cell for column "${header}"`);
  return found;
};

const table = (rows: readonly Invoice[], extra: Record<string, unknown> = {}) => (
  <DataTable
    caption="Invoices"
    columns={COLUMNS}
    rows={rows}
    rowId={(row) => row.id}
    {...extra}
  />
);

afterEach(() => {
  vi.useRealTimers();
});

describe('DataTable structure', () => {
  it('names the table with a caption, so two tables on a page are distinguishable', () => {
    const { container } = wrap(table([INVOICE]));

    const caption = container.querySelector('caption');
    expect(caption).toHaveTextContent('Invoices');
    // Present for a screen reader, absent from the visual design.
    expect(caption).toHaveClass('pms-visually-hidden');
  });

  it('renders one scoped column header per column', () => {
    wrap(table([INVOICE]));

    const headers = screen.getAllByRole('columnheader');
    expect(headers).toHaveLength(COLUMNS.length);
    expect(headers[0]).toHaveTextContent('Number');
    for (const header of headers) expect(header).toHaveAttribute('scope', 'col');
  });

  it('carries column widths on the colgroup, not on every cell', () => {
    const { container } = wrap(
      table([INVOICE], { columns: [{ key: 'number', header: 'Number', width: '12rem' }] }),
    );

    expect(container.querySelector('col')).toHaveStyle({ width: '12rem' });
  });

  it('renders a row per record, keyed by its id', () => {
    wrap(table([INVOICE, { ...BLANK_INVOICE, id: 'inv-2' }]));

    // Header row plus two body rows.
    expect(screen.getAllByRole('row')).toHaveLength(3);
  });

  it('drops a column marked hidden', () => {
    const { container } = wrap(
      table([INVOICE], {
        columns: [
          { key: 'number', header: 'Number' },
          { key: 'customer', header: 'Customer', hidden: true },
        ],
      }),
    );

    expect(screen.getByRole('columnheader', { name: 'Number' })).toBeInTheDocument();
    expect(container.querySelector('td[data-label="Customer"]')).toBeNull();
  });

  it('drops a column the actor may not read, and keeps one they may', () => {
    const columns: readonly Column<Invoice>[] = [
      { key: 'number', header: 'Number' },
      { key: 'total', header: 'Total', type: 'money', permission: 'invoice.amount.read' },
    ];

    const { container } = wrap(table([INVOICE], { columns }), ['invoice.read']);
    expect(container.querySelector('td[data-label="Total"]')).toBeNull();

    const permitted = wrap(table([INVOICE], { columns }), ['invoice.amount.read']);
    expect(permitted.container.querySelector('td[data-label="Total"]')).not.toBeNull();
  });

  it('keeps a hidden heading in the accessibility tree and out of the stacked labels', () => {
    const { container } = wrap(
      table([INVOICE], {
        columns: [{ key: 'number', header: 'Number' }, { key: 'x', header: 'Actions', hideHeader: true, type: 'actions' }],
      }),
    );

    // Still a named column for a screen reader …
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeInTheDocument();
    // … but no stacked caption, or every phone-width row would grow an "Actions" line.
    expect(container.querySelector('td[data-label="Actions"]')).toBeNull();
  });

  it('restates the table roles when stacking, because display:block strips them', () => {
    const { container } = wrap(table([INVOICE]));

    expect(container.querySelector('table')).toHaveAttribute('role', 'table');
    expect(container.querySelector('tbody')).toHaveAttribute('role', 'rowgroup');
    expect(container.querySelector('tbody td')).toHaveAttribute('role', 'cell');
  });

  it('leaves the roles implicit when the table never stacks', () => {
    const { container } = wrap(table([INVOICE], { stack: false }));

    expect(container.querySelector('table')).not.toHaveAttribute('role');
    expect(container.querySelector('tbody td')).not.toHaveAttribute('role');
    // The semantics are unchanged either way — this is markup noise, not behaviour.
    expect(screen.getAllByRole('row')).toHaveLength(2);
  });
});

describe('DataTable cell types', () => {
  it('formats an amount from the display config, with the company symbol and grouping', () => {
    const { container } = wrap(table([INVOICE]));

    expect(cell(container, 'Total')).toHaveTextContent('₹12,34,567.90');
  });

  it('states the code and drops the symbol for a row in another currency', () => {
    const { container } = wrap(table([{ ...INVOICE, currency: 'USD' }]));

    const total = cell(container, 'Total');
    // `₹` against a USD amount would be a money-correctness defect, not a formatting preference.
    expect(total).not.toHaveTextContent('₹');
    expect(total).toHaveTextContent('12,34,567.90');
    expect(total.querySelector('.pms-table__ccy')).toHaveTextContent('USD');
  });

  it('renders a zero amount as zero — never as a missing value', () => {
    const { container } = wrap(table([{ ...INVOICE, total: '0' }]));

    const total = cell(container, 'Total');
    expect(total).toHaveTextContent('₹0.00');
    expect(total).not.toHaveAttribute('data-empty');
  });

  it('em-dashes every absent value and marks the cell empty', () => {
    const { container } = wrap(table([BLANK_INVOICE]));

    for (const header of ['Number', 'Total', 'Qty', 'Margin', 'Status', 'Tags', 'Collected', 'Posted on', 'Created', 'Recurring', 'Card']) {
      const target = cell(container, header);
      expect(target).toHaveTextContent(EM_DASH);
      expect(target).toHaveAttribute('data-empty', 'true');
    }
  });

  it('formats quantities and percentages at the configured precision', () => {
    const { container } = wrap(table([INVOICE]));

    expect(cell(container, 'Qty')).toHaveTextContent('2.5000');
    expect(cell(container, 'Margin')).toHaveTextContent('18.6%');
  });

  it('formats a business date off its own string, with no timezone shift', () => {
    const { container } = wrap(table([INVOICE]));

    // 31 March is the fiscal year end; a timezone would make it 30 March somewhere.
    expect(cell(container, 'Posted on')).toHaveTextContent('31 Mar 2026');
  });

  it('renders an instant in the configured display timezone', () => {
    const { container } = wrap(table([INVOICE]));

    // 18:30Z is already the next day in Asia/Kolkata.
    expect(cell(container, 'Created')).toHaveTextContent('06 Mar 2026, 00:00');
  });

  it('shows an instant as elapsed time, keeping the stamp as its tooltip', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-05T21:30:00Z'));

    const { container } = wrap(
      table([INVOICE], { columns: [{ key: 'createdAt', header: 'Created', type: 'relative' }] }),
    );

    const time = container.querySelector('time');
    expect(time).toHaveTextContent('3 hours ago');
    // The reader scans the elapsed time; an audit trail eventually needs the absolute value.
    expect(time).toHaveAttribute('title', '06 Mar 2026, 00:00');
    expect(time).toHaveAttribute('datetime', '2026-03-05T18:30:00Z');
  });

  it('renders a status code as its label, in its tone', () => {
    const { container } = wrap(table([INVOICE]));

    const badge = cell(container, 'Status').querySelector('.pms-badge');
    expect(badge).toHaveTextContent('Posted');
    expect(badge).toHaveAttribute('data-tone', 'success');
  });

  it('caps a chip list and keeps the rest reachable in the overflow count', () => {
    const { container } = wrap(table([INVOICE]));

    const tags = cell(container, 'Tags');
    expect(tags.querySelectorAll('.pms-badge')).toHaveLength(3);
    const more = tags.querySelector('.pms-table__chips-more');
    expect(more).toHaveTextContent('+2');
    expect(more).toHaveAttribute('title', 'GST, EXPORT, REVERSE_CHARGE, SEZ, RCM');
  });

  it('treats an empty chip list as no value at all', () => {
    const { container } = wrap(table([{ ...INVOICE, tags: [] }]));

    expect(cell(container, 'Tags')).toHaveAttribute('data-empty', 'true');
  });

  it('draws a share as a named progress bar', () => {
    const { container } = wrap(table([INVOICE]));

    const bar = within(cell(container, 'Collected')).getByRole('progressbar');
    expect(bar).toHaveAccessibleName('Collected share');
    // 250,000 of 1,234,567.895.
    expect(bar).toHaveAttribute('aria-valuetext', '20%');
  });

  it('em-dashes a share with no denominator rather than drawing nought per cent', () => {
    const { container } = wrap(table([{ ...INVOICE, total: null }]));

    const collected = cell(container, 'Collected');
    expect(collected).toHaveAttribute('data-empty', 'true');
    expect(collected.querySelector('[role="progressbar"]')).toBeNull();
  });

  it('renders a link, and says when it leaves the app', () => {
    const { container } = wrap(
      table([INVOICE], {
        columns: [
          { key: 'number', header: 'Number', type: 'link', href: (row: Invoice) => `/invoices/${row.id}` },
          { key: 'customer', header: 'Customer', type: 'link', href: () => 'https://example.test', external: true },
        ],
      }),
    );

    const internal = within(cell(container, 'Number')).getByRole('link');
    expect(internal).toHaveAttribute('href', '/invoices/inv-1');
    expect(internal).not.toHaveAttribute('target');

    const external = within(cell(container, 'Customer')).getByRole('link');
    expect(external).toHaveAttribute('target', '_blank');
    expect(external).toHaveAttribute('rel', 'noreferrer noopener');
    expect(external).toHaveAccessibleName(/opens in a new tab/);
  });

  it('keeps the text when there is no target — a dead link is worse than none', () => {
    const { container } = wrap(
      table([INVOICE], {
        columns: [{ key: 'number', header: 'Number', type: 'link', href: () => null }],
      }),
    );

    const number = cell(container, 'Number');
    expect(number).toHaveTextContent('INV-2026-0004');
    expect(number.querySelector('a')).toBeNull();
  });

  it('refuses a script URL, however it is spelled, and keeps the text', () => {
    /*
     * `column.href` reads a payload — `external` exists because a link legitimately points off-site —
     * so a `javascript:` URL in a supplier's website field would otherwise execute on click, in the
     * reader's session. The scheme is allowlisted (`lib/url`), and a refused href degrades to plain
     * text rather than to an anchor with nowhere to go.
     */
    const hostile = [
      'javascript:alert(1)',
      'JaVaScRiPt:alert(1)',
      ' javascript:alert(1)',
      'java\nscript:alert(1)',
      'data:text/html,<script>alert(1)</script>',
      'vbscript:msgbox(1)',
      'file:///etc/passwd',
    ];

    for (const href of hostile) {
      const { container, unmount } = wrap(
        table([INVOICE], {
          columns: [{ key: 'number', header: 'Number', type: 'link', href: () => href }],
        }),
      );
      const number = cell(container, 'Number');
      expect(number.querySelector('a')).toBeNull();
      expect(number).toHaveTextContent('INV-2026-0004');
      unmount();
    }
  });

  it('renders a boolean as words, and honours the caller’s pair', () => {
    const { container } = wrap(
      table([INVOICE], {
        columns: [
          { key: 'recurring', header: 'Recurring', type: 'boolean' },
          // A second column over the same field needs its own key — `key` is the column's
          // identity, for the picker and for sorting — and reads the field explicitly.
          {
            key: 'recurring_words',
            header: 'Repeats',
            type: 'boolean',
            value: (row: Invoice) => row.recurring,
            words: ['Every month', 'Once'],
          },
        ],
      }),
    );

    expect(cell(container, 'Recurring')).toHaveTextContent('Yes');
    expect(cell(container, 'Repeats')).toHaveTextContent('Every month');
  });

  it('reads a serialiser’s 1 and 0 as a boolean, not as text', () => {
    const columns = [{ key: 'flag', header: 'Flag', type: 'boolean' as const }];
    const rows = [
      { id: 'a', flag: 1 },
      { id: 'b', flag: 0 },
    ];

    const { container } = wrap(
      <DataTable caption="Flags" columns={columns} rows={rows} rowId={(row) => row.id} />,
    );

    const cells = container.querySelectorAll('tbody td[data-label="Flag"]');
    expect(cells[0]).toHaveTextContent('Yes');
    expect(cells[1]).toHaveTextContent('No');
  });

  it('em-dashes an unset flag — unknown is not "No"', () => {
    const { container } = wrap(table([{ ...INVOICE, recurring: null }]));

    expect(cell(container, 'Recurring')).toHaveAttribute('data-empty', 'true');
  });

  it('shows a redacted value as a tail behind the mask', () => {
    const { container } = wrap(table([INVOICE]));

    // The server only ever sent the last four — this adds the redaction mark.
    expect(cell(container, 'Card')).toHaveTextContent('•••• 4242');
  });

  it('hands a custom cell the bound formatters, so it cannot format by hand', () => {
    const { container } = wrap(
      table([INVOICE], {
        columns: [
          {
            key: 'total',
            header: 'Balance',
            type: 'custom',
            render: (row: Invoice, format: { money: (v: string | null) => string }) => (
              <b>{format.money(row.total)}</b>
            ),
          },
        ],
      }),
    );

    expect(cell(container, 'Balance').querySelector('b')).toHaveTextContent('₹12,34,567.90');
  });

  it('puts the full text in a truncated cell’s tooltip', () => {
    const { container } = wrap(table([INVOICE]));

    const clipped = cell(container, 'Customer').querySelector('.pms-table__ellipsis');
    expect(clipped).toHaveAttribute('title', 'Northwind Traders Private Limited');
  });

  it('does not caption an empty truncated cell with an em dash', () => {
    const { container } = wrap(table([BLANK_INVOICE]));

    expect(cell(container, 'Customer').querySelector('.pms-table__ellipsis')).not.toHaveAttribute(
      'title',
    );
  });

  it('marks figure columns for tabular alignment and right-aligns them', () => {
    const { container } = wrap(table([INVOICE]));

    for (const header of ['Total', 'Qty', 'Margin', 'Collected']) {
      expect(cell(container, header)).toHaveAttribute('data-figure', 'true');
      expect(cell(container, header)).toHaveAttribute('data-align', 'end');
    }
    expect(cell(container, 'Customer')).toHaveAttribute('data-align', 'start');
    expect(cell(container, 'Customer')).not.toHaveAttribute('data-figure');
  });
});

describe('DataTable row actions', () => {
  const withActions = (extra: Record<string, unknown> = {}) =>
    wrap(
      table([INVOICE], {
        columns: [
          { key: 'number', header: 'Number', type: 'code' },
          {
            key: 'actions',
            header: 'Actions',
            type: 'actions',
            hideHeader: true,
            actions: () => [
              { id: 'view', label: 'View' },
              { id: 'void', label: 'Void', destructive: true },
            ],
          },
        ],
        ...extra,
      }),
    );

  it('names the row’s menu after the row, so eight kebabs are not all called "Actions"', () => {
    withActions({ rowLabel: (row: Invoice) => `Invoice ${row.number}` });

    expect(
      screen.getByRole('button', { name: 'Actions for Invoice INV-2026-0004' }),
    ).toBeInTheDocument();
  });

  it('falls back to the row id when there is no human label', () => {
    withActions();

    expect(screen.getByRole('button', { name: 'Actions for inv-1' })).toBeInTheDocument();
  });

  it('reports the chosen verb with the row it belongs to', async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    withActions({ onAction });

    await user.click(screen.getByRole('button', { name: 'Actions for inv-1' }));
    await user.click(screen.getByRole('menuitem', { name: 'View' }));

    expect(onAction).toHaveBeenCalledWith('view', INVOICE);
  });

  it('renders nothing for a row with no verbs at all', () => {
    wrap(
      table([INVOICE], {
        columns: [
          { key: 'number', header: 'Number' },
          { key: 'actions', header: 'Actions', type: 'actions', hideHeader: true, actions: () => [] },
        ],
      }),
    );

    // An always-disabled kebab in every row is noise, not an affordance.
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('DataTable table-level row actions', () => {
  const verbs = () => [{ id: 'view', label: 'View' }];

  it('adds the trailing kebab column itself, so a screen does not declare one per table', () => {
    wrap(
      table([INVOICE], {
        columns: [{ key: 'number', header: 'Number' }],
        rowActions: verbs,
        rowLabel: (row: Invoice) => `Invoice ${row.number}`,
      }),
    );

    expect(
      screen.getByRole('button', { name: 'Actions for Invoice INV-2026-0004' }),
    ).toBeInTheDocument();
    // The heading stays in the accessibility tree while being out of sight.
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeInTheDocument();
  });

  it('defers to a column the screen declared, rather than drawing a second kebab', () => {
    const { container } = wrap(
      table([INVOICE], {
        columns: [
          { key: 'number', header: 'Number' },
          { key: 'verbs', header: 'Actions', type: 'actions', hideHeader: true, actions: verbs },
        ],
        rowActions: verbs,
      }),
    );

    expect(screen.getAllByRole('button', { name: 'Actions for inv-1' })).toHaveLength(1);
    expect(container.querySelectorAll('thead th')).toHaveLength(2);
  });

  it('reports the chosen verb with its row', async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    wrap(
      table([INVOICE], {
        columns: [{ key: 'number', header: 'Number' }],
        rowActions: verbs,
        onAction,
      }),
    );

    await user.click(screen.getByRole('button', { name: 'Actions for inv-1' }));
    await user.click(screen.getByRole('menuitem', { name: 'View' }));

    expect(onAction).toHaveBeenCalledWith('view', INVOICE);
  });
});

/**
 * Selection is **page-scoped by construction**: every set the table reports is drawn from the rows
 * on screen. That is not a convenience — a bulk verb over rows nobody has seen is how one mistaken
 * filter becomes forty wrong documents, and a keyset list has no total to name the wider set with
 * anyway. These tests are what holds that shape in place.
 */
describe('DataTable selection', () => {
  const SECOND: Invoice = { ...INVOICE, id: 'inv-2', number: 'INV-2026-0005' };

  const selecting = (extra: Record<string, unknown> = {}) => {
    const onSelectionChange = vi.fn();
    const view = wrap(
      table([INVOICE, SECOND], {
        columns: [{ key: 'number', header: 'Number' }],
        selectable: true,
        onSelectionChange,
        rowLabel: (row: Invoice) => `Invoice ${row.number}`,
        ...extra,
      }),
    );
    return { ...view, onSelectionChange };
  };

  const allBox = () => screen.getByRole('checkbox', { name: 'Select all rows on this page' });

  it('draws no checkbox at all without a handler to report to', () => {
    wrap(
      table([INVOICE], { columns: [{ key: 'number', header: 'Number' }], selectable: true }),
    );

    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('names each row’s box after the row, not "Select row"', () => {
    selecting();

    expect(screen.getByRole('checkbox', { name: 'Select Invoice INV-2026-0004' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Select Invoice INV-2026-0005' })).toBeInTheDocument();
  });

  it('names the header box for the page it actually selects', () => {
    selecting();

    // Never "Select all": across a keyset walk that is a promise the control cannot keep.
    expect(allBox()).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Select all rows' })).not.toBeInTheDocument();
  });

  it('reports the whole new selection when a row is ticked', async () => {
    const user = userEvent.setup();
    const { onSelectionChange } = selecting({ selected: ['inv-1'] });

    await user.click(screen.getByRole('checkbox', { name: 'Select Invoice INV-2026-0005' }));

    expect(onSelectionChange).toHaveBeenCalledWith(['inv-1', 'inv-2']);
  });

  it('reports the removal when one is unticked', async () => {
    const user = userEvent.setup();
    const { onSelectionChange } = selecting({ selected: ['inv-1', 'inv-2'] });

    await user.click(screen.getByRole('checkbox', { name: 'Select Invoice INV-2026-0004' }));

    expect(onSelectionChange).toHaveBeenCalledWith(['inv-2']);
  });

  it('drops an id that is not on this page, so a bulk verb cannot reach an unseen row', async () => {
    const user = userEvent.setup();
    // `inv-99` was selected on a page the reader has left. It is not in what the table reports.
    const { onSelectionChange } = selecting({ selected: ['inv-1', 'inv-99'] });

    await user.click(screen.getByRole('checkbox', { name: 'Select Invoice INV-2026-0005' }));

    expect(onSelectionChange).toHaveBeenCalledWith(['inv-1', 'inv-2']);
  });

  it('selects and clears the page from the header box', async () => {
    const user = userEvent.setup();
    const { onSelectionChange, rerender } = selecting();

    await user.click(allBox());
    expect(onSelectionChange).toHaveBeenLastCalledWith(['inv-1', 'inv-2']);

    rerender(
      <PermissionProvider permissions={['*']}>
        <DisplayConfigProvider>
          {table([INVOICE, SECOND], {
            columns: [{ key: 'number', header: 'Number' }],
            selectable: true,
            onSelectionChange,
            selected: ['inv-1', 'inv-2'],
          })}
        </DisplayConfigProvider>
      </PermissionProvider>,
    );
    await user.click(allBox());

    expect(onSelectionChange).toHaveBeenLastCalledWith([]);
  });

  it('is mixed for a partly selected page and checked only when all of it is', () => {
    const { rerender } = selecting({ selected: ['inv-1'] });

    // A tick here would claim the row that is not in the set — and a bulk verb would then act on it.
    expect(allBox()).toBePartiallyChecked();
    expect(allBox()).not.toBeChecked();

    rerender(
      <PermissionProvider permissions={['*']}>
        <DisplayConfigProvider>
          {table([INVOICE, SECOND], {
            columns: [{ key: 'number', header: 'Number' }],
            selectable: true,
            onSelectionChange: vi.fn(),
            selected: ['inv-1', 'inv-2'],
          })}
        </DisplayConfigProvider>
      </PermissionProvider>,
    );

    expect(allBox()).toBeChecked();
    expect(allBox()).not.toBePartiallyChecked();
  });

  it('gives a row that may not be selected no box, and leaves it out of the page', async () => {
    const user = userEvent.setup();
    const { onSelectionChange } = selecting({
      rowSelectable: (row: Invoice) => row.id !== 'inv-2',
    });

    expect(
      screen.queryByRole('checkbox', { name: 'Select Invoice INV-2026-0005' }),
    ).not.toBeInTheDocument();

    await user.click(allBox());

    expect(onSelectionChange).toHaveBeenCalledWith(['inv-1']);
  });

  it('holds the header box when nothing on the page can be selected', () => {
    selecting({ rowSelectable: () => false });

    expect(allBox()).toBeDisabled();
  });

  it('marks the selected rows, so the set is visible and not only in the bar above', () => {
    const { container } = selecting({ selected: ['inv-2'] });

    const rows = container.querySelectorAll('tbody tr');
    expect(rows[0]).not.toHaveAttribute('data-selected');
    expect(rows[1]).toHaveAttribute('data-selected', 'true');
  });

  it('offers nothing to select while the page is loading', () => {
    selecting({ loading: true });

    expect(allBox()).toBeDisabled();
    expect(screen.queryByRole('checkbox', { name: /^Select Invoice/ })).not.toBeInTheDocument();
  });
});

describe('DataTable row expansion', () => {
  const SECOND: Invoice = { ...INVOICE, id: 'inv-2', number: 'INV-2026-0005' };

  const expanding = (extra: Record<string, unknown> = {}) => {
    const renderDetail = vi.fn((row: Invoice) => <p>{`Lines for ${row.number}`}</p>);
    const view = wrap(
      table([INVOICE, SECOND], {
        columns: [{ key: 'number', header: 'Number' }],
        renderDetail,
        rowLabel: (row: Invoice) => `Invoice ${row.number}`,
        ...extra,
      }),
    );
    return { ...view, renderDetail };
  };

  it('draws no toggle column when there is nothing to expand', () => {
    wrap(table([INVOICE], { columns: [{ key: 'number', header: 'Number' }] }));

    expect(screen.queryByRole('button', { name: /details/i })).not.toBeInTheDocument();
  });

  it('starts collapsed, with a toggle named after its row', () => {
    expanding();

    const toggle = screen.getByRole('button', { name: 'Show details for Invoice INV-2026-0004' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).not.toHaveAttribute('aria-controls');
    expect(screen.queryByText('Lines for INV-2026-0004')).not.toBeInTheDocument();
  });

  it('builds the panel only for the row that is open', async () => {
    const user = userEvent.setup();
    const { renderDetail } = expanding();

    // A page of 200 rows builds one panel, not 200 — which is why `renderDetail` is called lazily.
    expect(renderDetail).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Show details for Invoice INV-2026-0004' }));

    expect(screen.getByText('Lines for INV-2026-0004')).toBeInTheDocument();
    expect(renderDetail).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Lines for INV-2026-0005')).not.toBeInTheDocument();
  });

  it('points at the panel it opened, and only while it exists', async () => {
    const user = userEvent.setup();
    const { container } = expanding();

    await user.click(screen.getByRole('button', { name: 'Show details for Invoice INV-2026-0004' }));

    const toggle = screen.getByRole('button', { name: 'Hide details for Invoice INV-2026-0004' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const panelId = toggle.getAttribute('aria-controls');
    expect(panelId).not.toBeNull();
    expect(container.querySelector(`#${panelId}`)).toHaveTextContent('Lines for INV-2026-0004');
  });

  it('closes again', async () => {
    const user = userEvent.setup();
    expanding();

    await user.click(screen.getByRole('button', { name: 'Show details for Invoice INV-2026-0004' }));
    await user.click(screen.getByRole('button', { name: 'Hide details for Invoice INV-2026-0004' }));

    expect(screen.queryByText('Lines for INV-2026-0004')).not.toBeInTheDocument();
  });

  it('gives a row with nothing to show no toggle', () => {
    expanding({ rowExpandable: (row: Invoice) => row.id === 'inv-1' });

    expect(
      screen.getByRole('button', { name: 'Show details for Invoice INV-2026-0004' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /details for Invoice INV-2026-0005/ }),
    ).not.toBeInTheDocument();
  });

  it('spans the whole row, control columns included, so the panel is not a value in a column', async () => {
    const user = userEvent.setup();
    const { container } = wrap(
      table([INVOICE], {
        columns: [
          { key: 'number', header: 'Number' },
          { key: 'customer', header: 'Customer' },
        ],
        selectable: true,
        onSelectionChange: vi.fn(),
        renderDetail: () => <p>Lines</p>,
      }),
    );

    await user.click(screen.getByRole('button', { name: 'Show details for inv-1' }));

    // Two data columns plus the select and expand columns.
    expect(container.querySelector('.pms-table__detail')).toHaveAttribute('colspan', '4');
  });
});

describe('DataTable sorting', () => {
  const SORTABLE: readonly Column<Invoice>[] = [
    { key: 'number', header: 'Number', type: 'code', sortable: true },
    { key: 'customer', header: 'Customer' },
    { key: 'total', header: 'Total', type: 'money', sortable: true },
    { key: 'postedOn', header: 'Posted on', type: 'date', sortable: true },
    { key: 'status', header: 'Status', type: 'status', sortable: true, defaultSortDirection: 'desc' },
  ];

  const sortable = (extra: Record<string, unknown> = {}) =>
    wrap(table([INVOICE], { columns: SORTABLE, ...extra }));

  const header = (name: string): HTMLElement => screen.getByRole('columnheader', { name });

  it('makes a sortable heading a real button, and leaves the others as text', () => {
    sortable({ onSortChange: vi.fn() });

    expect(within(header('Number')).getByRole('button', { name: 'Number' })).toBeInTheDocument();
    expect(within(header('Customer')).queryByRole('button')).not.toBeInTheDocument();
  });

  it('leaves every heading inert without a change handler, however many say sortable', () => {
    // A control that cannot report anywhere is a dead control — better absent than deceptive.
    const { container } = sortable();

    expect(container.querySelectorAll('.pms-table__sort')).toHaveLength(0);
    expect(header('Number')).not.toHaveAttribute('aria-sort');
  });

  it('states the sort on the header cell, and only on sortable columns', () => {
    sortable({ sort: [{ key: 'total', direction: 'desc' }], onSortChange: vi.fn() });

    expect(header('Total')).toHaveAttribute('aria-sort', 'descending');
    expect(header('Total')).toHaveAttribute('data-sorted', 'desc');
    expect(header('Number')).toHaveAttribute('aria-sort', 'none');
    expect(header('Number')).not.toHaveAttribute('data-sorted');
    // `none` on a column that can never sort promises a control the reader will not find.
    expect(header('Customer')).not.toHaveAttribute('aria-sort');
  });

  it('reports ascending on the first press of a name, and descending for a figure or a date', async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    sortable({ onSortChange });

    await user.click(screen.getByRole('button', { name: 'Number' }));
    expect(onSortChange).toHaveBeenLastCalledWith([{ key: 'number', direction: 'asc' }]);

    await user.click(screen.getByRole('button', { name: 'Total' }));
    expect(onSortChange).toHaveBeenLastCalledWith([{ key: 'total', direction: 'desc' }]);

    await user.click(screen.getByRole('button', { name: 'Posted on' }));
    expect(onSortChange).toHaveBeenLastCalledWith([{ key: 'postedOn', direction: 'desc' }]);
  });

  it('honours a column stating its own first direction', async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    sortable({ onSortChange });

    await user.click(screen.getByRole('button', { name: 'Status' }));

    expect(onSortChange).toHaveBeenCalledWith([{ key: 'status', direction: 'desc' }]);
  });

  it('flips the direction when the column already leads the sort', async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    sortable({ sort: [{ key: 'total', direction: 'desc' }], onSortChange });

    await user.click(screen.getByRole('button', { name: 'Total' }));

    expect(onSortChange).toHaveBeenCalledWith([{ key: 'total', direction: 'asc' }]);
  });

  it('replaces the sort rather than appending to it', async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    sortable({ sort: [{ key: 'total', direction: 'desc' }], onSortChange });

    await user.click(screen.getByRole('button', { name: 'Number' }));

    // The server allowlists sort *combinations*; a reader-assembled triple would earn a 422.
    expect(onSortChange).toHaveBeenCalledWith([{ key: 'number', direction: 'asc' }]);
  });

  it('keeps a hidden heading readable to a screen reader while still sorting', () => {
    wrap(
      table([INVOICE], {
        columns: [{ key: 'number', header: 'Number', sortable: true, hideHeader: true }],
        onSortChange: vi.fn(),
      }),
    );

    expect(screen.getByRole('button', { name: 'Number' })).toBeInTheDocument();
  });

  it('carries the sort control in the stylesheet as a focusable, inheriting button', () => {
    // `css: false` here, so the parts only CSS can state are asserted against its text.
    expect(TABLE_CSS).toMatch(/\.pms-table__sort\s*\{[^}]*font: inherit/);
    expect(TABLE_CSS).toMatch(/\.pms-table__sort:focus-visible\s*\{[^}]*--pms-focus-ring/);
    // Faint, never hidden: a hover-only affordance does not exist for a touch reader.
    expect(TABLE_CSS).toMatch(/\.pms-table__sort-icon\s*\{[^}]*--pms-ink-faint/);
  });
});

describe('DataTable states', () => {
  it('replaces the body with placeholders while loading, and says so', () => {
    const { container } = wrap(table([INVOICE], { loading: true, skeletonRows: 3 }));

    expect(container.querySelector('table')).toHaveAttribute('aria-busy', 'true');
    expect(container.querySelectorAll('.pms-skeleton')).toHaveLength(3 * COLUMNS.length);
    // The previous page's rows are not left on screen pretending to be current.
    expect(screen.queryByText('INV-2026-0004')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Loading rows');
  });

  it('keeps the placeholder rows out of the accessibility tree', () => {
    wrap(table([], { loading: true, skeletonRows: 4 }));

    // A screen reader should hear the live region, not four rows of grey bars.
    expect(screen.getAllByRole('row')).toHaveLength(1);
  });

  it('shows the intended copy for a permission failure, not an outage', () => {
    wrap(table([], { error: 403 }));

    expect(screen.getByText("You don't have access to this")).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('The list could not be loaded');
  });

  it('offers a retry that reruns the query', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    wrap(table([], { error: 500, onRetry }));

    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('prefers the failure over the spinner — a failed load is not still loading', () => {
    wrap(table([], { error: 500, loading: true }));

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('The list could not be loaded');
  });

  it('offers the way in for a genuinely empty list', () => {
    wrap(table([], { emptyAction: <button type="button">Create an invoice</button> }));

    expect(screen.getByText('Nothing here yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create an invoice' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('No rows');
  });

  it('offers the way out when the query is what emptied the list', async () => {
    const user = userEvent.setup();
    const onClearFilters = vi.fn();
    wrap(table([], { filtered: true, onClearFilters }));

    // Different failure, different instruction: this list is not empty, the query is too narrow.
    expect(screen.getByText('No matching rows')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(onClearFilters).toHaveBeenCalledTimes(1);
  });

  it('lets a screen override the empty copy for its own domain', () => {
    wrap(table([], { emptyTitle: 'No credit notes', emptyBody: 'Nothing has been credited yet.' }));

    expect(screen.getByText('No credit notes')).toBeInTheDocument();
    expect(screen.getByText('Nothing has been credited yet.')).toBeInTheDocument();
  });

  it('spans the state across every rendered column', () => {
    const { container } = wrap(table([]));

    expect(container.querySelector('.pms-table__state')).toHaveAttribute(
      'colspan',
      String(COLUMNS.length),
    );
  });

  it('counts the rows it actually shows, in the singular when there is one', () => {
    wrap(table([INVOICE]));
    expect(screen.getByRole('status')).toHaveTextContent('1 row');
  });

  it('counts them in the plural otherwise', () => {
    wrap(table([INVOICE, { ...BLANK_INVOICE, id: 'inv-2' }, { ...BLANK_INVOICE, id: 'inv-3' }]));
    expect(screen.getByRole('status')).toHaveTextContent('3 rows');
  });
});

describe('DataTable row locking', () => {
  const locked = (extra: Record<string, unknown> = {}) =>
    wrap(
      table([INVOICE, { ...BLANK_INVOICE, id: 'inv-2' }], {
        rowLocked: (row: Invoice) => (row.id === 'inv-1' ? 'posted on 31 Mar 2026' : null),
        ...extra,
      }),
    );

  it('marks the row that can no longer change, and only that row', () => {
    const { container } = locked();

    const rows = container.querySelectorAll('tbody tr');
    expect(rows[0]).toHaveAttribute('data-locked', 'true');
    expect(rows[1]).not.toHaveAttribute('data-locked');
  });

  it('states the reason rather than leaving a bare padlock', () => {
    const { container } = locked();

    const mark = container.querySelector('.pms-table__lock');
    // Hover and screen reader get the same sentence — the reason is always known at the call site.
    expect(mark).toHaveAttribute('title', 'posted on 31 Mar 2026');
    expect(mark).toHaveTextContent('Locked: posted on 31 Mar 2026');
  });

  it('puts the marker in the first cell, where the eye starts', () => {
    const { container } = locked();

    const cells = container.querySelectorAll('tbody tr:first-child td');
    expect(cells[0]?.querySelector('.pms-table__lock')).not.toBeNull();
    expect(cells[1]?.querySelector('.pms-table__lock')).toBeNull();
  });
});

describe('DataTable layout controls', () => {
  it('defaults to the comfortable row height and takes a compact one', () => {
    const { container } = wrap(table([INVOICE]));
    expect(container.querySelector('table')).toHaveAttribute('data-density', 'comfortable');

    const compact = wrap(table([INVOICE], { density: 'compact' }));
    expect(compact.container.querySelector('table')).toHaveAttribute('data-density', 'compact');
  });

  it('freezes the heading row by default, and caps the shell so it can', () => {
    const { container } = wrap(table([INVOICE]));

    expect(container.querySelector('table')).toHaveClass('pms-table--sticky');
    expect(container.querySelector('.pms-table-shell')).toHaveAttribute('data-sticky', 'true');
  });

  it('makes the scroll region reachable by keyboard, and says which table it is', () => {
    /* The shell scrolls — sideways always, vertically while the header is frozen — and a scroll
     * container with no tab stop is content a keyboard-only reader cannot reach (WCAG 2.1.1). Arrow
     * keys scroll it only once focus is inside, and a wide ledger's off-screen columns need hold
     * nothing focusable at all. The caption names the stop so it is not an unexplained one. */
    wrap(table([INVOICE]));

    const region = screen.getByRole('region', { name: 'Invoices' });
    expect(region).toHaveClass('pms-table-shell');
    expect(region).toHaveAttribute('tabindex', '0');
    expect(region).toContainElement(screen.getByRole('table'));
  });

  it('tells the stylesheet whether the rows will stack, so the height cap can go with the header', () => {
    const { container } = wrap(table([INVOICE]));
    expect(container.querySelector('.pms-table-shell')).toHaveAttribute('data-stack', 'true');

    const flat = wrap(table([INVOICE], { stack: false }));
    expect(flat.container.querySelector('.pms-table-shell')).not.toHaveAttribute('data-stack');
  });

  it('drops both when the header is not sticky', () => {
    const { container } = wrap(table([INVOICE], { stickyHeader: false }));

    expect(container.querySelector('table')).not.toHaveClass('pms-table--sticky');
    expect(container.querySelector('.pms-table-shell')).not.toHaveAttribute('data-sticky');
  });

  it('pins the first column only, header cell included', () => {
    const { container } = wrap(table([INVOICE], { pinFirstColumn: true }));

    expect(container.querySelectorAll('th[data-pinned="true"]')).toHaveLength(1);
    expect(container.querySelectorAll('tbody td[data-pinned="true"]')).toHaveLength(1);
    expect(cell(container, 'Number')).toHaveAttribute('data-pinned', 'true');
    expect(cell(container, 'Customer')).not.toHaveAttribute('data-pinned');
  });

  it('pins nothing unless asked', () => {
    const { container } = wrap(table([INVOICE]));

    expect(container.querySelector('[data-pinned]')).toBeNull();
  });

  it('pins the control columns with the first one, each at its own offset', () => {
    const { container } = wrap(
      table([INVOICE], {
        pinFirstColumn: true,
        selectable: true,
        onSelectionChange: vi.fn(),
        renderDetail: () => <p>Lines</p>,
      }),
    );

    const pinned = container.querySelectorAll<HTMLElement>('tbody td[data-pinned="true"]');
    // Select, expand, and the first data column — a frozen identifier with the row's own controls
    // scrolled away from it would be useless.
    expect(pinned).toHaveLength(3);
    // The first sits at the edge and takes its offset from the stylesheet; the rest are computed
    // from the control column's fixed width, which is why that width is a token and not a guess.
    expect(pinned[0]?.style.insetInlineStart).toBe('');
    expect(pinned[1]?.style.insetInlineStart).toBe('calc(var(--pms-table-ctrl-w) * 1)');
    expect(pinned[2]?.style.insetInlineStart).toBe('calc(var(--pms-table-ctrl-w) * 2)');
  });

  it('draws the separating edge once, on the last cell of the pinned run', () => {
    const { container } = wrap(
      table([INVOICE], { pinFirstColumn: true, selectable: true, onSelectionChange: vi.fn() }),
    );

    // Otherwise the frozen control column prints a hairline against the frozen identifier beside it.
    const edges = container.querySelectorAll('tbody td[data-pin-edge="true"]');
    expect(edges).toHaveLength(1);
    expect(cell(container, 'Number')).toHaveAttribute('data-pin-edge', 'true');
  });

  it('labels every cell for the stacked layout', () => {
    const { container } = wrap(table([INVOICE]));

    // `::before` prints this, so a phone-width row reads "Total ₹12,34,567.90".
    expect(cell(container, 'Total')).toHaveAttribute('data-label', 'Total');
  });
});

describe('DataTable stylesheet', () => {
  it('caps the shell height only when the header is sticky — that is what makes it stick', () => {
    // `overflow-x: auto` computes `overflow-y` to `auto`, so the shell is the scrollport the
    // sticky header resolves against. Without a cap it never scrolls, and never sticks.
    expect(TABLE_CSS).toMatch(
      /\.pms-table-shell\[data-sticky='true'\]\s*\{[^}]*max-height: var\(--pms-table-max-h\)/,
    );
    expect(TABLE_CSS).toMatch(
      /\.pms-table-shell\[data-sticky='true'\]\s*\{[^}]*overflow-y: auto/,
    );
  });

  it('keeps the borders separate, so the frozen header keeps its own rule', () => {
    expect(TABLE_CSS).toMatch(/\.pms-table\s*\{[^}]*border-collapse: separate/);
  });

  it('gives a pinned cell an opaque background, since content scrolls beneath it', () => {
    expect(TABLE_CSS).toMatch(
      /\.pms-table td\[data-pinned='true'\]\s*\{[^}]*background: var\(--pms-surface\)/,
    );
  });

  it('stacks the pinned header above both the frozen header and the pinned body cells', () => {
    const pinnedHead = /\.pms-table th\[data-pinned='true'\]\s*\{[^}]*z-index: 3/;
    const stickyHead = /\.pms-table--sticky thead th\s*\{[^}]*z-index: 2/;
    const pinnedCell = /\.pms-table td\[data-pinned='true'\]\s*\{[^}]*z-index: 1/;
    for (const rule of [pinnedHead, stickyHead, pinnedCell]) expect(TABLE_CSS).toMatch(rule);
  });

  it('gives the focusable shell a focus indicator, drawn inside its own scrollport', () => {
    // A tab stop with no visible focus state is WCAG 2.4.7, and the shared `--pms-focus-ring` is
    // drawn outside the box — which this box, being an overflow container, would clip.
    expect(TABLE_CSS).toMatch(
      /\.pms-table-shell:focus-visible\s*\{[^}]*outline: 2px solid var\(--pms-focus\)/,
    );
    expect(TABLE_CSS).toMatch(/\.pms-table-shell:focus-visible\s*\{[^}]*outline-offset: -2px/);
  });

  it('lifts the height cap once the rows stack, so a phone is not given a scroller inside a scroller', () => {
    const stacked = TABLE_CSS.slice(TABLE_CSS.indexOf('@media (max-width: 52rem)'));
    // The cap exists to make the header stick; the header is clipped here, so all it would do is
    // trap the reader in two thirds of the smallest viewport there is.
    expect(stacked).toMatch(
      /\.pms-table-shell\[data-stack='true'\]\s*\{[^}]*max-height: none/,
    );
  });

  it('switches every table element to a block in the stacked layout, thead included', () => {
    // A `thead` left as a `table-header-group` inside a `display: block` table gets wrapped in an
    // anonymous table box — a layout nobody wrote and nobody can style.
    const stacked = TABLE_CSS.slice(TABLE_CSS.indexOf('@media (max-width: 52rem)'));
    // The selector list of the one rule that turns them into blocks, comments excluded.
    const blocks = /((?:\s*\.pms-table--stack[a-z ]*,)+[^,{]*)\{\s*display: block/.exec(stacked);
    for (const element of ['thead', 'tbody', 'tr', 'td']) {
      expect(blocks?.[1]).toContain(`.pms-table--stack ${element}`);
    }
  });

  it('keeps an expanded row and its panel as one block when stacked', () => {
    /* Stacked, every row draws its own closing rule — including the one immediately above its own
     * detail, where the line makes the panel read as the next record. */
    const stacked = TABLE_CSS.slice(TABLE_CSS.indexOf('@media (max-width: 52rem)'));
    expect(stacked).toMatch(
      /tr:has\(\+ \.pms-table__detail-row\)\s*\{[^}]*border-bottom: 0/,
    );
  });

  it('clips the heading row in the stacked layout rather than removing it', () => {
    // `display: none` would take the column names out of the accessibility tree, leaving the
    // `::before` labels — which are decoration — as the only headings.
    const stacked = TABLE_CSS.slice(TABLE_CSS.indexOf('@media (max-width: 52rem)'));
    expect(stacked).toMatch(/\.pms-table--stack thead th\s*\{[^}]*clip: rect\(0 0 0 0\)/);
    expect(stacked).not.toMatch(/\.pms-table--stack thead[^{]*\{[^}]*display: none/);
  });

  it('prints each cell’s own label once the row is a block', () => {
    expect(TABLE_CSS).toMatch(/td::before\s*\{\s*content: attr\(data-label\)/);
  });

  it('pins with the logical property, the one the component sets inline', () => {
    // `left` here and `inset-inline-start` inline would not be the same property, so the computed
    // offset would lose to the stylesheet's 0 under a right-to-left script.
    expect(TABLE_CSS).toMatch(/td\[data-pinned='true'\]\s*\{[^}]*inset-inline-start: 0/);
    expect(TABLE_CSS).not.toMatch(/\[data-pinned='true'\]\s*\{[^}]*\bleft: 0/);
  });

  it('fixes the control column’s width, because the sticky offsets are computed from it', () => {
    expect(TABLE_CSS).toMatch(/--pms-table-ctrl-w: [\d.]+rem/);
  });

  it('spaces the in-cell adornments logically, so they follow the writing direction', () => {
    /* The pin badge sits after the header's text and the currency code before the amount — stated as
     * `right`/`left` they would both land on the wrong side of a right-to-left script, in a cell whose
     * own alignment already flips. The pinned offset above is logical for the same reason. */
    expect(TABLE_CSS).toMatch(/\.pms-table__lock\s*\{[^}]*margin-inline-end/);
    expect(TABLE_CSS).toMatch(/\.pms-table__ccy\s*\{[^}]*margin-inline-start/);
    expect(TABLE_CSS).not.toMatch(/\.pms-table__lock\s*\{[^}]*margin-right/);
    expect(TABLE_CSS).not.toMatch(/\.pms-table__ccy\s*\{[^}]*margin-left/);
  });

  it('keeps a selected row tinted under the pointer', () => {
    // Hover is where the pointer is; selection is what a bulk verb is about to act on. The second
    // outranks the first, or the row the reader is aiming at looks unselected.
    expect(TABLE_CSS).toMatch(
      /tr\[data-selected='true'\]:hover td\s*\{[^}]*background: var\(--pms-brand-tint\)/,
    );
  });
});
