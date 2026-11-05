/**
 * `SearchSelect` — entity lookup.
 *
 * The keyboard model and the async guards are the substance of this file. A combobox that moves
 * DOM focus into its own list, or that lets a stale response overwrite a fresh one, or that
 * reuses a cursor across a query change, is broken in ways nothing on screen shows: the list
 * looks right and answers a question the user has already moved on from. Each of those is
 * asserted rather than assumed.
 *
 * jsdom computes no layout and `getBoundingClientRect()` is all zeroes, so the positioning
 * contract is asserted where it is actually expressible — the portal's place in the DOM tree,
 * the inline `position`, and the stylesheet text.
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  SearchSelect,
  type SearchSelectLoader,
  type SearchSelectOption,
  type SearchSelectProps,
} from '../src/components/SearchSelect';

const CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'search-select.css'), 'utf8');

/** Seven rows, so `PageDown`/`PageUp`'s five-row jump has somewhere to land and to wrap from. */
const CUSTOMERS: readonly SearchSelectOption[] = [
  { id: 'c1', label: 'Sharma Traders', meta: 'CUST-001 · Pune', figure: '1,20,000.00' },
  { id: 'c2', label: 'Nadkarni & Sons', meta: 'CUST-002 · Mumbai' },
  { id: 'c3', label: 'Rao Industries', meta: 'CUST-003 · Hyderabad' },
  { id: 'c4', label: 'Kulkarni Exports', meta: 'CUST-004 · Nashik' },
  // Present but not selectable — the inactive-master case §5.5 calls out.
  { id: 'c5', label: 'Iyer Logistics', meta: 'CUST-005 · Chennai', disabled: true },
  { id: 'c6', label: 'Bose Chemicals', meta: 'CUST-006 · Kolkata' },
  { id: 'c7', label: 'Menon Foods', meta: 'CUST-007 · Kochi' },
];

/** Everything on `BaseProps` a test might vary. `value`/`onChange` belong to the harness. */
/**
 * Derived from the component's own props rather than restated: a hand-written copy of the prop
 * list silently stops covering whatever is added next, which is exactly what happened when
 * `hideLabel` arrived. `Extract` picks the single-selection member of the union, and dropping
 * the three identity props leaves the shared base every harness needs.
 */
type Extra = Omit<
  Extract<SearchSelectProps, { multiple?: false }>,
  'label' | 'value' | 'onChange' | 'multiple'
>;


type SingleSpy = (id: string | null, option: SearchSelectOption | null) => void;
type MultiSpy = (ids: string[], options: SearchSelectOption[]) => void;

/**
 * The control is controlled, so a bare `onChange={vi.fn()}` can never show the *result* of a
 * selection. These hold the state so the input text, the chips and the toggle-off path are real;
 * the spy still sees every raw call, which is what the `onChange` contract tests assert.
 */
function Single({
  initial = null,
  spy,
  ...rest
}: Extra & { initial?: string | null; spy?: SingleSpy }) {
  const [value, setValue] = useState<string | null>(initial);
  return (
    <SearchSelect
      label="Customer"
      {...rest}
      value={value}
      onChange={(id, option) => {
        setValue(id);
        spy?.(id, option);
      }}
    />
  );
}

function Multi({ initial = [], spy, ...rest }: Extra & { initial?: string[]; spy?: MultiSpy }) {
  const [value, setValue] = useState<readonly string[]>(initial);
  return (
    <SearchSelect
      label="Customers"
      {...rest}
      multiple
      value={value}
      onChange={(ids, options) => {
        setValue(ids);
        spy?.(ids, options);
      }}
    />
  );
}

/*
 * The listbox names itself with `aria-label={label}`, so `getByLabelText('Customer')` matches
 * two elements once the list is open. Label *association* is asserted once, explicitly, in the
 * structure block; everywhere else the field is reached by its role.
 */
const input = () => screen.getByRole('combobox') as HTMLInputElement;
/** The portalled panel is not in `container`, and the status lines carry no role. */
const panel = () => document.querySelector('.pms-search-select__panel') as HTMLElement;
const statusText = () =>
  Array.from(panel().querySelectorAll('.pms-search-select__status'))
    .map((node) => node.textContent ?? '')
    .join(' | ');
const live = () => screen.getByRole('status');
/** The highlight is `aria-activedescendant`, so "which row is active" is an id lookup. */
const activeRowText = () => {
  const id = input().getAttribute('aria-activedescendant');
  return id ? (document.getElementById(id)?.textContent ?? null) : null;
};

/**
 * Every `userEvent` API goes through RTL's `asyncWrapper`, which parks on a `setTimeout(…, 0)`
 * and only pumps the clock when it detects **jest** fake timers (`typeof jest !== 'undefined'`,
 * `@testing-library/dom/helpers.js`). Under Vitest's clock that timer never fires, so the
 * documented `userEvent.setup({ advanceTimers })` recipe deadlocks on the first `await`. The
 * shim is the smallest thing that makes the recipe work; without it the whole async block hangs.
 */
function installFakeClock() {
  vi.useFakeTimers();
  vi.stubGlobal('jest', { advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms) });
}

function restoreClock() {
  vi.unstubAllGlobals();
  vi.useRealTimers();
}

/* ------------------------------------------------------------------ structure */

describe('SearchSelect — field structure', () => {
  it('labels the input and declares the combobox pattern', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    const field = input();
    // The one place the label association itself is asserted (see the helper note above).
    expect(screen.getByLabelText('Customer')).toBe(field);
    expect(field.tagName).toBe('INPUT');
    expect(field).toHaveAttribute('role', 'combobox');
    // `list`, not `both`: inline completion fights entity search, where what you type rarely
    // prefixes what you want.
    expect(field).toHaveAttribute('aria-autocomplete', 'list');
    expect(field).toHaveAttribute('aria-expanded', 'false');
    // Pointing `aria-controls` at a listbox that does not exist yet is a promise with nothing
    // behind it, so it is absent while closed.
    expect(field).not.toHaveAttribute('aria-controls');

    await user.click(field);
    expect(field).toHaveAttribute('aria-expanded', 'true');
    expect(field).toHaveAttribute('aria-controls', screen.getByRole('listbox').id);
  });

  it('renders the list as a named listbox of options carrying selection state', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} initial="c1" />);

    await user.click(input());
    // Named "<field> results", not "<field>": naming the list the same as the field made
    // `getByLabelText` match two elements and announced the same word twice on entry.
    const list = screen.getByRole('listbox', { name: 'Customer results' });
    // Single select: no `aria-multiselectable`, or AT offers a selection model that does not exist.
    expect(list).not.toHaveAttribute('aria-multiselectable');

    const options = within(list).getAllByRole('option');
    expect(options).toHaveLength(7);
    expect(options[0]).toHaveAttribute('aria-selected', 'true');
    expect(options[1]).toHaveAttribute('aria-selected', 'false');
  });

  it('marks the listbox multiselectable only in multiple mode', async () => {
    const user = userEvent.setup();
    render(<Multi options={CUSTOMERS} />);

    await user.click(input());
    expect(screen.getByRole('listbox')).toHaveAttribute('aria-multiselectable', 'true');
  });

  it('renders meta and figure as the already-formatted strings they arrive as', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    const row = within(screen.getByRole('listbox')).getByRole('option', { name: /Sharma Traders/ });
    expect(row).toHaveTextContent('CUST-001 · Pune');
    // Figures are tabular everywhere — the control never formats, only aligns.
    expect(row.querySelector('.pms-search-select__figure')).toHaveClass('pms-figure');
    expect(row.querySelector('.pms-search-select__mark')).toHaveAttribute('aria-hidden', 'true');
  });

  it('filters on label and on meta, case-insensitively', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    await user.type(input(), 'sharma');
    expect(screen.getAllByRole('option')).toHaveLength(1);
    expect(screen.getByRole('option')).toHaveTextContent('Sharma Traders');

    // A code or a city is how people actually look a customer up, so `meta` matches too.
    await user.clear(input());
    await user.type(input(), 'PUNE');
    expect(screen.getByRole('option')).toHaveTextContent('Sharma Traders');

    await user.clear(input());
    await user.type(input(), 'cust-00');
    expect(screen.getAllByRole('option')).toHaveLength(7);
  });

  it('wires the hint through aria-describedby', () => {
    render(<Single options={CUSTOMERS} hint="Search by name or code." />);

    const hint = screen.getByText('Search by name or code.');
    expect(input()).toHaveAttribute('aria-describedby', hint.id);
    expect(input()).not.toHaveAttribute('aria-invalid');
  });

  it('wires the error through aria-describedby and aria-invalid', () => {
    const { container } = render(<Single options={CUSTOMERS} error="Pick a customer." />);

    const error = screen.getByText('Pick a customer.');
    expect(input()).toHaveAttribute('aria-describedby', error.id);
    expect(input()).toHaveAttribute('aria-invalid', 'true');
    // The invalid edge is a data attribute on the box, never colour alone in the text.
    expect(container.querySelector('.pms-search-select__control')).toHaveAttribute(
      'data-invalid',
      'true',
    );
  });

  it('shows the error in place of the hint when both are given', () => {
    render(<Single options={CUSTOMERS} hint="Search by name or code." error="Pick a customer." />);

    // One line under a field, and the one that blocks the save wins.
    expect(screen.getByText('Pick a customer.')).toBeInTheDocument();
    expect(screen.queryByText('Search by name or code.')).not.toBeInTheDocument();
  });

  it('marks required fields, and never advertises optionality', () => {
    // No "Optional" marker in either state: on a lookup it is noise, and `required` already
    // carries the semantic. A filter is not "optional", it is just a filter.
    const { unmount } = render(<Single options={CUSTOMERS} />);
    expect(screen.queryByText('Optional')).not.toBeInTheDocument();
    expect(input()).not.toHaveAttribute('aria-required');
    unmount();

    render(<Single options={CUSTOMERS} required />);
    expect(screen.queryByText('Optional')).not.toBeInTheDocument();
    expect(input()).toHaveAttribute('aria-required', 'true');
  });

  it('keeps the label as the accessible name when it is hidden from the layout', () => {
    // `hideLabel` is for a toolbar filter, where a stacked label in a row of controls is noise.
    // It may cost pixels and never the name.
    render(<Single options={CUSTOMERS} hideLabel />);

    expect(screen.getByRole('combobox', { name: 'Customer' })).toBeInTheDocument();
    expect(screen.getByText('Customer')).toHaveClass('pms-label');
  });

  it('disables the input and withdraws the clear button when disabled', () => {
    const { container } = render(<Single options={CUSTOMERS} initial="c1" disabled />);

    expect(input()).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Clear Customer' })).not.toBeInTheDocument();
    expect(container.querySelector('.pms-search-select__control')).toHaveAttribute(
      'data-disabled',
      'true',
    );
  });

  /*
   * Fixed; this is the guard. The panel is portalled, so a field disabled while its list is open
   * leaves a list of rows sitting on the page above a control that must accept nothing. Disabling
   * has to take the list with it, and no commit path may fire afterwards — not a click where a row
   * used to be, and not an Enter on what was highlighted.
   */
  it('accepts nothing once disabled, and takes its open list off the screen', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const { rerender } = render(<Single options={CUSTOMERS} spy={spy} />);

    await user.click(input());
    await user.keyboard('{ArrowDown}');
    // Held before the rerender, because clicking where a row was a moment ago is exactly what
    // someone does when the field disables under them.
    const row = screen.getByRole('option', { name: /Sharma Traders/ });

    rerender(<Single options={CUSTOMERS} spy={spy} disabled />);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(panel()).toBeNull();

    // `fireEvent`, not `user.click`: the row is detached now, which is the whole point.
    fireEvent.click(row);
    await user.keyboard('{Enter}');

    expect(spy).not.toHaveBeenCalled();
    expect(input()).toHaveValue('');
  });

  it('withholds the clear button until there is something to clear, and honours clearable', () => {
    const { unmount } = render(<Single options={CUSTOMERS} />);
    expect(screen.queryByRole('button', { name: 'Clear Customer' })).not.toBeInTheDocument();
    unmount();

    const held = render(<Single options={CUSTOMERS} initial="c1" clearable={false} />);
    expect(screen.queryByRole('button', { name: 'Clear Customer' })).not.toBeInTheDocument();
    held.unmount();

    render(<Single options={CUSTOMERS} initial="c1" />);
    expect(screen.getByRole('button', { name: 'Clear Customer' })).toBeInTheDocument();
  });

  it('emits one hidden input per selected id so a plain form submit carries the value', () => {
    const single = render(<Single options={CUSTOMERS} initial="c1" name="customer_id" />);
    let hidden = Array.from(
      single.container.querySelectorAll<HTMLInputElement>('input[type="hidden"]'),
    );
    expect(hidden.map((node) => [node.name, node.value])).toEqual([['customer_id', 'c1']]);
    single.unmount();

    const multi = render(<Multi options={CUSTOMERS} initial={['c1', 'c3']} name="customer_ids" />);
    hidden = Array.from(multi.container.querySelectorAll<HTMLInputElement>('input[type="hidden"]'));
    expect(hidden.map((node) => node.value)).toEqual(['c1', 'c3']);
    expect(hidden.every((node) => node.name === 'customer_ids')).toBe(true);
  });

  it('emits no hidden input without a name', () => {
    const { container } = render(<Single options={CUSTOMERS} initial="c1" />);
    expect(container.querySelector('input[type="hidden"]')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ keyboard */

describe('SearchSelect — keyboard model', () => {
  /** Focus lands on the input and opens the list; Escape shuts it without moving focus. */
  async function openThenClose(user: ReturnType<typeof userEvent.setup>) {
    await user.click(input());
    await user.keyboard('{Escape}');
    expect(input()).toHaveAttribute('aria-expanded', 'false');
  }

  it('opens on ArrowDown from a closed field without highlighting anything', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);
    await openThenClose(user);

    await user.keyboard('{ArrowDown}');
    expect(input()).toHaveAttribute('aria-expanded', 'true');
    // Opening is not choosing: the first ArrowDown reveals the list, the second enters it.
    expect(input()).not.toHaveAttribute('aria-activedescendant');

    await user.keyboard('{ArrowDown}');
    expect(activeRowText()).toContain('Sharma Traders');
  });

  it('opens on ArrowUp from a closed field without highlighting anything', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);
    await openThenClose(user);

    await user.keyboard('{ArrowUp}');
    expect(input()).toHaveAttribute('aria-expanded', 'true');
    expect(input()).not.toHaveAttribute('aria-activedescendant');
  });

  it('keeps DOM focus on the input while the highlight walks the list', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);
    await user.click(input());

    for (let i = 0; i < 3; i += 1) {
      await user.keyboard('{ArrowDown}');
      // The whole reason for `aria-activedescendant`: nothing to trap, nothing to restore.
      expect(input()).toHaveFocus();
    }
    expect(activeRowText()).toContain('Rao Industries');
  });

  it('points aria-activedescendant at the id of the highlighted row', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);
    await user.click(input());
    await user.keyboard('{ArrowDown}{ArrowDown}');

    const options = screen.getAllByRole('option');
    expect(input().getAttribute('aria-activedescendant')).toBe(options[1]?.id);
    expect(options[1]).toHaveAttribute('data-active', 'true');
    expect(options[0]).not.toHaveAttribute('data-active');
  });

  it('wraps ArrowDown past the last row and ArrowUp past the first', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);
    await user.click(input());

    await user.keyboard('{End}');
    expect(activeRowText()).toContain('Menon Foods');
    await user.keyboard('{ArrowDown}');
    expect(activeRowText()).toContain('Sharma Traders');
    await user.keyboard('{ArrowUp}');
    expect(activeRowText()).toContain('Menon Foods');
  });

  it('wraps ArrowUp onto the last row from an unentered list', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);
    await user.click(input());

    // Entering an open list from the bottom is the whole point of ArrowUp — landing on the first
    // row would make it a slower ArrowDown.
    await user.keyboard('{ArrowUp}');
    expect(activeRowText()).toContain('Menon Foods');
    await user.keyboard('{ArrowUp}');
    expect(activeRowText()).toContain('Bose Chemicals');
  });

  it('jumps to the ends with Home and End', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);
    await user.click(input());

    await user.keyboard('{End}');
    expect(activeRowText()).toContain('Menon Foods');
    await user.keyboard('{Home}');
    expect(activeRowText()).toContain('Sharma Traders');
    expect(input()).toHaveFocus();
  });

  it('moves five rows at a time with PageDown and PageUp, wrapping like the arrows', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);
    await user.click(input());

    // From no highlight, a page jump is five rows in: index 4 of seven.
    await user.keyboard('{PageDown}');
    expect(activeRowText()).toContain('Iyer Logistics');
    // Past the end wraps to the top rather than sticking, so the two vertical keys agree.
    await user.keyboard('{PageDown}');
    expect(activeRowText()).toContain('Sharma Traders');
    await user.keyboard('{PageUp}');
    expect(activeRowText()).toContain('Menon Foods');
    await user.keyboard('{PageUp}');
    expect(activeRowText()).toContain('Nadkarni & Sons');
  });

  it('ignores Home, End and the page keys while closed', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);
    await openThenClose(user);

    await user.keyboard('{Home}{End}{PageDown}{PageUp}');
    expect(input()).toHaveAttribute('aria-expanded', 'false');
    expect(input()).not.toHaveAttribute('aria-activedescendant');
  });

  it('selects the highlighted row on Enter', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Single options={CUSTOMERS} spy={spy} />);

    await user.click(input());
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');

    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith('c2', CUSTOMERS[1]);
  });

  it('does nothing on Enter with no row highlighted', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Single options={CUSTOMERS} spy={spy} />);

    await user.click(input());
    await user.keyboard('{Enter}');

    expect(spy).not.toHaveBeenCalled();
    // Enter is not a commit-the-first-guess key: the list stays open, unchanged.
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('closes on the first Escape and clears the typed query on the second', async () => {
    const user = userEvent.setup();
    render(<Multi options={CUSTOMERS} />);
    const field = input();

    await user.type(field, 'rao');
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    // The query survives the close, so reopening resumes where you were…
    expect(field).toHaveValue('rao');

    // …and a second Escape, with nothing left to close, is what clears it.
    await user.keyboard('{Escape}');
    expect(field).toHaveValue('');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('closes on Tab and commits nothing', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Single options={CUSTOMERS} spy={spy} />);

    await user.click(input());
    await user.keyboard('{ArrowDown}');
    await user.tab();

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    // A highlight is not a selection. Committing on Tab would put a customer on an invoice
    // because someone tabbed past the field.
    expect(spy).not.toHaveBeenCalled();
    expect(input()).not.toHaveFocus();
  });

  it('will not select a disabled option by Enter or by click', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Single options={CUSTOMERS} spy={spy} />);

    await user.click(input());
    await user.keyboard('{PageDown}');
    const row = screen.getByRole('option', { name: /Iyer Logistics/ });
    expect(row).toHaveAttribute('aria-disabled', 'true');
    expect(input().getAttribute('aria-activedescendant')).toBe(row.id);

    await user.keyboard('{Enter}');
    expect(spy).not.toHaveBeenCalled();
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    await user.click(row);
    expect(spy).not.toHaveBeenCalled();
  });

  it('leaves keys it does not own alone', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Single options={CUSTOMERS} spy={spy} />);

    await user.click(input());
    await user.keyboard('{ArrowLeft}{ArrowRight}');

    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(input()).not.toHaveAttribute('aria-activedescendant');
    expect(spy).not.toHaveBeenCalled();
  });

  it('drops the highlight when the query changes under it', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    await user.keyboard('{ArrowDown}{ArrowDown}');
    await user.type(input(), 'k');
    // The row at index 1 is a different customer now; keeping the index would commit the wrong
    // entity on the next Enter.
    expect(input()).not.toHaveAttribute('aria-activedescendant');
  });

  /*
   * Fixed; this is the guard. The highlight moves by `aria-activedescendant`, which moves no scroll
   * position — so on a list taller than its own box, arrowing down walked the highlight straight
   * out of view and the key looked dead. jsdom implements no scrolling and does not even define
   * the method, which is why the component feature-detects it and why asserting it means defining
   * it here.
   */
  it('scrolls the newly highlighted row into view, without moving the page', async () => {
    const seen: Array<{ row: Element; arg: unknown }> = [];
    const scrollIntoView = vi.fn(function (this: Element, arg: unknown) {
      seen.push({ row: this, arg });
    });
    const proto = Element.prototype as { scrollIntoView?: unknown };
    proto.scrollIntoView = scrollIntoView;

    try {
      const user = userEvent.setup();
      render(<Single options={CUSTOMERS} />);
      await user.click(input());
      await user.keyboard('{ArrowDown}{ArrowDown}');

      // `block: 'nearest'` and nothing else: a highlight already on screen must not make the list
      // jump, and the page behind the popover must not scroll at all.
      expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
      const last = seen.at(-1);
      expect(last?.row).toBe(screen.getByRole('option', { name: /Nadkarni & Sons/ }));
      expect(last?.row).toHaveAttribute('data-active', 'true');
    } finally {
      delete proto.scrollIntoView;
    }
  });

  it('does not move the highlight in an empty list', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.type(input(), 'zzzz');
    await user.keyboard('{ArrowDown}{End}{PageDown}');
    expect(input()).not.toHaveAttribute('aria-activedescendant');
  });
});

/* ------------------------------------------------------------------ selection */

describe('SearchSelect — single selection', () => {
  it('reports the id and the option, closes, and shows the label', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Single options={CUSTOMERS} spy={spy} />);

    await user.click(input());
    await user.click(screen.getByRole('option', { name: /Rao Industries/ }));

    expect(spy).toHaveBeenCalledWith('c3', CUSTOMERS[2]);
    // Picking one of one is the last thing someone wants to do here, so the list shuts.
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(input()).toHaveValue('Rao Industries');
  });

  it('shows the typed query while open and falls back to the label when closed', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    await user.click(screen.getByRole('option', { name: /Sharma Traders/ }));
    expect(input()).toHaveValue('Sharma Traders');

    await user.click(input());
    // Open, the field is a search box; the chosen label would have to be deleted to search again.
    expect(input()).toHaveValue('');
    await user.keyboard('{Escape}');
    expect(input()).toHaveValue('Sharma Traders');
  });

  /*
   * Fixed; this is the guard. The option cache is a `useRef` map filled
   * from a `useEffect`, and mutating a ref schedules no re-render, so the render that could have
   * shown the label has already happened by the time the cache knows about it. The field paints
   * empty with a value set, which is the exact case §5.5 introduces `selected` for.
   */
  it('labels a value whose option was never in a list', () => {
    render(
      <Single
        options={[]}
        initial="c99"
        selected={{ id: 'c99', label: 'Ghost Holdings', meta: 'CUST-099' }}
      />,
    );

    expect(input()).toHaveValue('Ghost Holdings');
  });

  /* Fixed; this is the guard —, same cause: even a value whose option is in `options` paints unlabelled. */
  it('labels an initial value carried by the static options', () => {
    render(<Single options={CUSTOMERS} initial="c1" />);
    expect(input()).toHaveValue('Sharma Traders');
  });

  it('clears back to null through the clear button', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Single options={CUSTOMERS} initial="c1" spy={spy} />);

    // The clear affordance keys off the *id*, not the cache, so it is there on first paint.
    await user.click(screen.getByRole('button', { name: 'Clear Customer' }));

    expect(spy).toHaveBeenCalledWith(null, null);
    expect(input()).toHaveValue('');
    expect(screen.queryByRole('button', { name: 'Clear Customer' })).not.toBeInTheDocument();
  });

  /*
   * Fixed; this is the guard. Single mode closes on commit and the input goes back to showing the
   * chosen label, so a retained `filterQuery` reopened a list narrowed by a query the box no longer
   * shows — three customers reduced to one, with nothing on screen explaining why.
   */
  it('reopens on the whole list, not on the query that produced the selection', async () => {
    const user = userEvent.setup();
    const three = CUSTOMERS.slice(0, 3);
    render(<Single options={three} />);

    await user.type(input(), 'rao');
    expect(screen.getAllByRole('option')).toHaveLength(1);
    await user.click(screen.getByRole('option', { name: /Rao Industries/ }));

    await user.click(input());
    expect(screen.getAllByRole('option')).toHaveLength(3);
    // And the live region agrees with what is on screen — a filtered list announcing "3 results"
    // would be the same defect with a second symptom.
    expect(live()).toHaveTextContent('3 results');
  });
});

describe('SearchSelect — multiple selection', () => {
  it('appends on select, removes on re-select, and keeps the list open', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Multi options={CUSTOMERS} spy={spy} />);

    await user.click(input());
    await user.click(screen.getByRole('option', { name: /Sharma Traders/ }));
    expect(spy).toHaveBeenLastCalledWith(['c1'], [CUSTOMERS[0]]);
    // Picking one of several is rarely the last thing someone wants to do.
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    await user.click(screen.getByRole('option', { name: /Rao Industries/ }));
    expect(spy).toHaveBeenLastCalledWith(['c1', 'c3'], [CUSTOMERS[0], CUSTOMERS[2]]);
    expect(screen.getByRole('option', { name: /Rao Industries/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );

    await user.click(screen.getByRole('option', { name: /Sharma Traders/ }));
    expect(spy).toHaveBeenLastCalledWith(['c3'], [CUSTOMERS[2]]);
  });

  it('renders a chip per selection with a working remove button', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const { container } = render(<Multi options={CUSTOMERS} spy={spy} />);

    await user.click(input());
    await user.click(screen.getByRole('option', { name: /Sharma Traders/ }));
    await user.click(screen.getByRole('option', { name: /Rao Industries/ }));

    const chips = container.querySelectorAll('.pms-search-select__chip-label');
    expect(Array.from(chips).map((node) => node.textContent)).toEqual([
      'Sharma Traders',
      'Rao Industries',
    ]);

    // A chip whose remove control is an icon with no name is a dead end for a screen reader.
    await user.click(screen.getByRole('button', { name: 'Remove Sharma Traders' }));
    expect(spy).toHaveBeenLastCalledWith(['c3'], [CUSTOMERS[2]]);
    expect(container.querySelectorAll('.pms-search-select__chip')).toHaveLength(1);
  });

  it('disables chip removal along with the field', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Multi options={CUSTOMERS} />);

    await user.click(input());
    await user.click(screen.getByRole('option', { name: /Sharma Traders/ }));
    rerender(<Multi options={CUSTOMERS} disabled />);

    expect(screen.getByRole('button', { name: 'Remove Sharma Traders' })).toBeDisabled();
    expect(input()).toBeDisabled();
  });

  it('removes the last chip on Backspace in an empty input', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Multi options={CUSTOMERS} initial={['c1', 'c3']} spy={spy} />);

    await user.click(input());
    await user.keyboard('{Backspace}');
    expect(spy).toHaveBeenCalledWith(['c1'], [CUSTOMERS[0]]);
  });

  it('leaves the chips alone when Backspace has text to delete', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Multi options={CUSTOMERS} initial={['c1']} spy={spy} />);

    const field = input();
    await user.type(field, 'rao');
    await user.keyboard('{Backspace}');

    expect(field).toHaveValue('ra');
    // Backspace deleting a chip while there is still a query would eat selections mid-typo.
    expect(spy).not.toHaveBeenCalled();
  });

  it('clears every selection through the clear button', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const { container } = render(<Multi options={CUSTOMERS} initial={['c1', 'c3']} spy={spy} />);

    await user.click(screen.getByRole('button', { name: 'Clear Customers' }));

    expect(spy).toHaveBeenCalledWith([], []);
    expect(container.querySelectorAll('.pms-search-select__chip')).toHaveLength(0);
  });

  /*
   * `maxChips` is what stops a toolbar filter growing until it pushes its own input out of the
   * control. The collapse must not make a selection unreachable, though: the "+N more" affordance
   * is a count, not another removable chip, so the only route to the ones past the cap is Backspace
   * — which removes from the end of the selection, which is exactly the end that is hidden.
   */
  it('collapses the chips past maxChips into a count whose selections stay removable', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const { container } = render(
      <Multi options={CUSTOMERS} initial={['c1', 'c2', 'c3']} maxChips={1} spy={spy} />,
    );

    expect(container.querySelectorAll('.pms-search-select__chip')).toHaveLength(1);
    expect(screen.getByText('+2 more')).toBeInTheDocument();
    // The two beyond the cap have no remove button of their own — that is what collapsing means.
    expect(screen.queryByRole('button', { name: 'Remove Rao Industries' })).not.toBeInTheDocument();

    await user.click(input());
    await user.keyboard('{Backspace}');
    expect(spy).toHaveBeenLastCalledWith(['c1', 'c2'], [CUSTOMERS[0], CUSTOMERS[1]]);
    expect(screen.getByText('+1 more')).toBeInTheDocument();

    await user.keyboard('{Backspace}');
    expect(spy).toHaveBeenLastCalledWith(['c1'], [CUSTOMERS[0]]);
    // Back under the cap, so the count goes rather than reading "+0 more".
    expect(container.querySelector('.pms-search-select__chip-count')).toBeNull();
    expect(container.querySelectorAll('.pms-search-select__chip')).toHaveLength(1);
  });

  /* Fixed; this is the guard — — the ref-cache-in-an-effect problem again; see the single-mode note above. */
  it('labels chips for values whose options were never in a list', () => {
    const { container } = render(
      <Multi
        options={[]}
        initial={['g1', 'g2']}
        selected={[
          { id: 'g1', label: 'Ghost Holdings' },
          { id: 'g2', label: 'Phantom Freight' },
        ]}
      />,
    );

    expect(
      Array.from(container.querySelectorAll('.pms-search-select__chip-label')).map(
        (node) => node.textContent,
      ),
    ).toEqual(['Ghost Holdings', 'Phantom Freight']);
  });
});

/* ------------------------------------------------------------------ async */

type Page = { items: SearchSelectOption[]; nextCursor: string | null };

function deferred() {
  let resolve!: (page: Page) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<Page>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const remoteRows = (prefix: string, count: number, from = 1): SearchSelectOption[] =>
  Array.from({ length: count }, (_, i) => ({
    id: `${prefix}${from + i}`,
    label: `${prefix.toUpperCase()} row ${from + i}`,
  }));

describe('SearchSelect — async loading', () => {
  beforeEach(installFakeClock);
  afterEach(restoreClock);

  const setup = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  /** Fake timers plus a promise chain: the timer has to fire *and* its microtasks drain. */
  const settle = async (ms = 300) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  };

  it('debounces a burst of keystrokes into one request for the final query', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: remoteRows('a', 2), nextCursor: null }));
    render(<Single loadOptions={load} />);

    await user.type(input(), 'shar');
    // Every intermediate query is a query someone never asked for.
    expect(load).not.toHaveBeenCalled();

    await settle();
    expect(load).toHaveBeenCalledTimes(1);
    expect(load.mock.calls[0]?.[0]).toMatchObject({ q: 'shar', cursor: null });
  });

  it('applies only the newest response when an older one settles last', async () => {
    const user = setup();
    const first = deferred();
    const second = deferred();
    const load = vi
      .fn<SearchSelectLoader>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    await user.type(input(), 'a');
    await settle();
    expect(load.mock.calls.map((call) => call[0].q)).toEqual(['sh', 'sha']);

    // The fresh answer arrives first, then the abandoned one — which is what an abort alone does
    // not prevent (decision log 23). Without the monotonic request id the list would end up
    // showing results for "sh" while the field reads "sha".
    await act(async () => {
      second.resolve({ items: [{ id: 'fresh', label: 'Fresh answer' }], nextCursor: null });
    });
    await act(async () => {
      first.resolve({ items: [{ id: 'stale', label: 'Stale answer' }], nextCursor: null });
    });

    expect(screen.getByRole('option', { name: 'Fresh answer' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Stale answer' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(1);
  });

  it('resets the cursor on every query change, never reusing the previous page token', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async ({ cursor }) => ({
      items: cursor ? remoteRows('a', 2, 3) : remoteRows('a', 2),
      nextCursor: cursor ? null : 'cursor-page-2',
    }));
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    expect(load.mock.calls[0]?.[0].cursor).toBeNull();

    // Page in, so a live cursor exists to be wrongly reused.
    await user.keyboard('{End}');
    await settle();
    expect(load.mock.calls[1]?.[0].cursor).toBe('cursor-page-2');

    await user.type(input(), 'a');
    await settle();
    // A cursor is bound to its query, filters and sort: carrying this one across the change is a
    // 422 by the API contract (api-conventions §2.1, decision log 22).
    expect(load.mock.calls[2]?.[0]).toMatchObject({ q: 'sha', cursor: null });
    expect(load.mock.calls.slice(2).every((call) => call[0].cursor === null)).toBe(true);
  });

  it('clears the previous query results rather than mixing two pages of answers', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async ({ q }) => ({
      items: [{ id: q, label: `Answer for ${q}` }],
      nextCursor: null,
    }));
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    expect(screen.getByRole('option', { name: 'Answer for sh' })).toBeInTheDocument();

    await user.type(input(), 'a');
    await settle();
    expect(screen.getAllByRole('option')).toHaveLength(1);
    expect(screen.getByRole('option', { name: 'Answer for sha' })).toBeInTheDocument();
  });

  it('clamps q to the API maximum of 200 characters', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: [], nextCursor: null }));
    render(<Single loadOptions={load} />);

    await user.click(input());
    // `maxLength` stops a human at 200; a paste, an autofill or a programmatic set does not go
    // through it, and 201 characters is a guaranteed 422 (api-conventions §2.3).
    expect(input()).toHaveAttribute('maxlength', '200');
    fireEvent.change(input(), { target: { value: 'x'.repeat(250) } });
    await settle();

    expect(load).toHaveBeenCalledTimes(1);
    expect(load.mock.calls[0]?.[0].q).toHaveLength(200);
  });

  it('holds back below the default minimum of two characters', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: remoteRows('a', 2), nextCursor: null }));
    render(<Single loadOptions={load} />);

    await user.click(input());
    await settle();
    // An unfiltered entity query is the cost this asymmetry exists to avoid (§5.5).
    expect(load).not.toHaveBeenCalled();
    expect(statusText()).toContain('Type at least 2 characters to search');
    expect(screen.queryByRole('option')).not.toBeInTheDocument();

    await user.type(input(), 's');
    await settle();
    expect(load).not.toHaveBeenCalled();

    await user.type(input(), 'h');
    await settle();
    expect(load).toHaveBeenCalledTimes(1);
    expect(statusText()).not.toContain('Type at least');
  });

  it('honours an overridden minQueryLength', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: remoteRows('a', 1), nextCursor: null }));
    render(<Single loadOptions={load} minQueryLength={4} />);

    await user.type(input(), 'sha');
    await settle();
    expect(load).not.toHaveBeenCalled();
    expect(statusText()).toContain('Type at least 4 characters to search');

    await user.type(input(), 'r');
    await settle();
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('respects a caller-supplied debounce window', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: remoteRows('a', 1), nextCursor: null }));
    render(<Single loadOptions={load} debounceMs={1000} />);

    await user.type(input(), 'sha');
    await settle(900);
    expect(load).not.toHaveBeenCalled();
    await settle(200);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('pages the next cursor in when the highlight walks onto the last row', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async ({ cursor }) =>
      cursor
        ? { items: remoteRows('a', 3, 4), nextCursor: null }
        : { items: remoteRows('a', 3), nextCursor: 'cursor-page-2' },
    );
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(within(panel()).getByRole('button', { name: 'Load more' })).toBeInTheDocument();

    await user.keyboard('{End}');
    await settle();
    expect(load).toHaveBeenCalledTimes(2);
    expect(load.mock.calls[1]?.[0].cursor).toBe('cursor-page-2');
    // Appended, not replaced: paging that resets the list loses the row you were walking towards.
    expect(screen.getAllByRole('option')).toHaveLength(6);
    expect(activeRowText()).toContain('A row 3');
    // Cursor exhausted, so the affordance goes rather than offering a page that does not exist.
    expect(within(panel()).queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });

  it('pages on the Load more button, which stays out of the tab order', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async ({ cursor }) =>
      cursor
        ? { items: remoteRows('a', 2, 3), nextCursor: null }
        : { items: remoteRows('a', 2), nextCursor: 'cursor-page-2' },
    );
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();

    const more = within(panel()).getByRole('button', { name: 'Load more' });
    // Tab is defined to close the list, so a tab stop inside it is a control you can never reach.
    expect(more).toHaveAttribute('tabindex', '-1');
    await user.click(more);
    await settle();

    expect(load.mock.calls[1]?.[0].cursor).toBe('cursor-page-2');
    expect(screen.getAllByRole('option')).toHaveLength(4);
  });

  it('de-duplicates ids across pages', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async ({ cursor }) =>
      cursor
        ? // A row that moved between pages under a concurrent write — the honest overlap case.
          { items: [...remoteRows('a', 1, 2), ...remoteRows('a', 1, 3)], nextCursor: null }
        : { items: remoteRows('a', 2), nextCursor: 'cursor-page-2' },
    );
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    await user.click(within(panel()).getByRole('button', { name: 'Load more' }));
    await settle();

    const labels = screen.getAllByRole('option').map((row) => row.textContent);
    expect(labels).toEqual(['A row 1', 'A row 2', 'A row 3']);
  });

  it('keeps the cursor when the query it belongs to is typed back verbatim', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async ({ cursor }) =>
      cursor
        ? { items: remoteRows('a', 2, 3), nextCursor: null }
        : { items: remoteRows('a', 2), nextCursor: 'cursor-page-2' },
    );
    render(<Multi loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    await user.click(screen.getByRole('option', { name: /A row 1/ }));

    /*
     * Multiple mode clears the input on a commit but deliberately keeps the results — so the
     * *same* query arriving in one change event (a paste, or a one-character search) leaves
     * `filterQuery` unchanged, the search effect never re-runs, and a cursor dropped here is
     * never minted again. The rows stay on screen with no way left to page past them.
     */
    await user.paste('sh');

    expect(within(panel()).getByRole('button', { name: 'Load more' })).toBeInTheDocument();
    await user.click(within(panel()).getByRole('button', { name: 'Load more' }));
    await settle();

    expect(load.mock.calls[1]?.[0].cursor).toBe('cursor-page-2');
    expect(screen.getAllByRole('option')).toHaveLength(4);
  });

  it('caps the accumulated list at maxOptions and says so', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: remoteRows('a', 5), nextCursor: 'cursor-page-2' }));
    render(<Single loadOptions={load} maxOptions={3} />);

    await user.type(input(), 'sh');
    await settle();

    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(statusText()).toContain('Showing the first 3. Refine your search to narrow it down.');
    // Saying "refine your search" and then offering another page would be two different answers.
    expect(within(panel()).queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });

  /*
   * Fixed; this is the guard. The cap notice keyed off `visible.length >= maxOptions` alone, so a
   * final page that happened to fill the cap exactly was reported as truncated — "refine your
   * search" about a list that is already whole, and no cursor behind it to refine towards.
   */
  it('does not claim truncation on a final page that fills the cap exactly', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: remoteRows('a', 3), nextCursor: null }));
    render(<Single loadOptions={load} maxOptions={3} />);

    await user.type(input(), 'sh');
    await settle();

    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(statusText()).not.toContain('Showing the first');
    expect(within(panel()).queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });

  it('names a failure and offers retry instead of claiming there is nothing there', async () => {
    const user = setup();
    const load = vi
      .fn<SearchSelectLoader>()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ items: remoteRows('a', 2), nextCursor: null });
    render(<Single loadOptions={load} emptyLabel="No customers found" />);

    await user.type(input(), 'sh');
    await settle();

    expect(statusText()).toContain('Couldn’t load results.');
    // Collapsing the two states tells someone their customer does not exist when in fact the
    // network did not answer (§5.5).
    expect(panel().textContent).not.toContain('No customers found');
    expect(live()).toHaveTextContent('Search failed');

    await user.click(within(panel()).getByRole('button', { name: 'Try again' }));
    await settle();

    expect(load).toHaveBeenCalledTimes(2);
    expect(load.mock.calls[1]?.[0]).toMatchObject({ q: 'sh', cursor: null });
    expect(screen.getAllByRole('option')).toHaveLength(2);
    expect(panel().textContent).not.toContain('Couldn’t load results.');
  });

  it('keeps the retry control out of the tab order, like every other row-level control', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>().mockRejectedValue(new Error('network'));
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    expect(within(panel()).getByRole('button', { name: 'Try again' })).toHaveAttribute(
      'tabindex',
      '-1',
    );
  });

  it('shows the empty state, not the error state, on an honest empty page', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: [], nextCursor: null }));
    render(<Single loadOptions={load} emptyLabel="No customers found" />);

    await user.type(input(), 'sh');
    await settle();

    expect(statusText()).toContain('No customers found');
    expect(panel().textContent).not.toContain('Couldn’t load results.');
  });

  it('aborts the in-flight request when the list closes', async () => {
    const user = setup();
    const signals: AbortSignal[] = [];
    const load = vi.fn<SearchSelectLoader>(({ signal }) => {
      signals.push(signal);
      return new Promise<Page>(() => {});
    });
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    expect(signals).toHaveLength(1);
    expect(signals[0]?.aborted).toBe(false);

    await user.keyboard('{Escape}');
    // A request nobody is waiting for is still holding a connection and will still try to write
    // state when it lands.
    expect(signals[0]?.aborted).toBe(true);
  });

  it('aborts the previous request when a new query supersedes it', async () => {
    const user = setup();
    const signals: AbortSignal[] = [];
    const load = vi.fn<SearchSelectLoader>(({ signal }) => {
      signals.push(signal);
      return new Promise<Page>(() => {});
    });
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    await user.type(input(), 'a');
    await settle();

    expect(signals).toHaveLength(2);
    expect(signals[0]?.aborted).toBe(true);
    expect(signals[1]?.aborted).toBe(false);
  });

  /*
   * Fixed; this is the guard. Aborting a request that is already past the network cancels nothing —
   * it only marks it ignorable — so closing the list has to invalidate the *request id* as well.
   * Without that, a response the user walked away from still wrote itself into the list, and the
   * next time the panel opened it was showing the answer to a question already abandoned.
   */
  it('never lets a response the user walked away from reach the list', async () => {
    const user = setup();
    const abandoned = deferred();
    const fresh = deferred();
    const load = vi
      .fn<SearchSelectLoader>()
      .mockReturnValueOnce(abandoned.promise)
      .mockReturnValueOnce(fresh.promise);
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    expect(load).toHaveBeenCalledTimes(1);

    await user.keyboard('{Escape}');
    // The abort lands, and the request settles anyway. Both things are true at once.
    await act(async () => {
      abandoned.resolve({ items: [{ id: 'stale', label: 'Stale answer' }], nextCursor: null });
    });

    await user.click(input());
    // Reopening searches immediately, so the rows on screen are page one of a *new* request.
    expect(load).toHaveBeenCalledTimes(2);
    await act(async () => {
      fresh.resolve({ items: [{ id: 'fresh', label: 'Fresh answer' }], nextCursor: null });
    });

    expect(screen.getAllByRole('option')).toHaveLength(1);
    expect(screen.getByRole('option', { name: 'Fresh answer' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Stale answer' })).not.toBeInTheDocument();
  });

  it('aborts the in-flight request when the field unmounts', async () => {
    const user = setup();
    const signals: AbortSignal[] = [];
    const load = vi.fn<SearchSelectLoader>(({ signal }) => {
      signals.push(signal);
      return new Promise<Page>(() => {});
    });
    const { unmount } = render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    expect(signals[0]?.aborted).toBe(false);

    unmount();
    // Navigating away mid-search otherwise holds the connection open and lands a response in a
    // component that no longer exists.
    expect(signals[0]?.aborted).toBe(true);
  });

  it('pages from the sentinel when an IntersectionObserver exists', async () => {
    type Entries = Array<{ isIntersecting: boolean }>;
    const observers: Array<{ callback: (entries: Entries) => void; observed: Element[] }> = [];

    class StubObserver {
      private readonly entry: { callback: (entries: Entries) => void; observed: Element[] };
      constructor(callback: (entries: Entries) => void) {
        this.entry = { callback, observed: [] };
        observers.push(this.entry);
      }
      observe(node: Element) {
        this.entry.observed.push(node);
      }
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }

    // jsdom has none, and the component guards on `typeof IntersectionObserver` — so the pointer
    // paging path is only reachable with a local stub.
    vi.stubGlobal('IntersectionObserver', StubObserver);
    try {
      const user = setup();
      const load = vi.fn<SearchSelectLoader>(async ({ cursor }) =>
        cursor
          ? { items: remoteRows('a', 2, 3), nextCursor: null }
          : { items: remoteRows('a', 2), nextCursor: 'cursor-page-2' },
      );
      render(<Single loadOptions={load} />);

      await user.type(input(), 'sh');
      await settle();

      expect(observers).toHaveLength(1);
      expect(observers[0]?.observed[0]).toHaveClass('pms-search-select__sentinel');

      await act(async () => {
        observers[0]?.callback([{ isIntersecting: true }]);
      });
      await settle();

      expect(load).toHaveBeenCalledTimes(2);
      expect(load.mock.calls[1]?.[0].cursor).toBe('cursor-page-2');
      expect(screen.getAllByRole('option')).toHaveLength(4);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('does not observe anything when scrolling past is not intersecting', async () => {
    type Entries = Array<{ isIntersecting: boolean }>;
    let callback: ((entries: Entries) => void) | null = null;

    class StubObserver {
      constructor(cb: (entries: Entries) => void) {
        callback = cb;
      }
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }

    vi.stubGlobal('IntersectionObserver', StubObserver);
    try {
      const user = setup();
      const load = vi.fn<SearchSelectLoader>(async () => ({ items: remoteRows('a', 2), nextCursor: 'cursor-page-2' }));
      render(<Single loadOptions={load} />);

      await user.type(input(), 'sh');
      await settle();

      await act(async () => {
        callback?.([{ isIntersecting: false }]);
      });
      await settle();
      expect(load).toHaveBeenCalledTimes(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('caches remote options so a selection survives the search that produced it', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async ({ q }) => ({
      items: [{ id: `id-${q}`, label: `Answer for ${q}` }],
      nextCursor: null,
    }));
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    await user.click(screen.getByRole('option', { name: 'Answer for sh' }));

    // The list that described this id has been replaced by a different search; the label has to
    // come from the cache or the field goes blank with a value still set.
    expect(input()).toHaveValue('Answer for sh');
  });

  it('makes no request in async mode until the list is opened', async () => {
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: remoteRows('a', 1), nextCursor: null }));
    render(<Single loadOptions={load} minQueryLength={0} />);

    await settle();
    expect(load).not.toHaveBeenCalled();
  });
});

/* ------------------------------------------------------------------ create-new */

describe('SearchSelect — create new', () => {
  const createRow = () => screen.queryByRole('option', { name: /^Add/ });

  it('stays hidden without the caller opting in', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} onCreate={vi.fn()} />);

    await user.type(input(), 'Zenith');
    // `canCreate` is the caller's permission check (§5.4) — presentation only, but still a gate.
    expect(createRow()).not.toBeInTheDocument();
  });

  it('stays hidden with an empty query', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} canCreate onCreate={vi.fn()} />);

    await user.click(input());
    // There is nothing to name the new entity after yet.
    expect(createRow()).not.toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(7);
  });

  it('stays hidden when an existing option already carries that exact label', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} canCreate onCreate={vi.fn()} />);

    await user.type(input(), 'rao industries');
    // Offering "Add Rao Industries" under Rao Industries is how duplicate masters get created.
    expect(createRow()).not.toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(1);
  });

  /*
   * Fixed; this is the guard. `visible` inside the debounce window still answers the *previous*
   * query, so on the async path a name the list already carries looked like a new one and the panel
   * offered to create a duplicate master. The existing duplicate-name guard above is static-mode
   * only, where filtering is synchronous — it never covered the path where this actually happens.
   */
  it('offers no create row for a name the settled async list already carries', async () => {
    installFakeClock();
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const load = vi.fn<SearchSelectLoader>(async ({ q }) => ({
        items: q.trim().toLowerCase().startsWith('rao')
          ? [{ id: 'c3', label: 'Rao Industries', meta: 'CUST-003 · Hyderabad' }]
          : [],
        nextCursor: null,
      }));
      render(<Single loadOptions={load} canCreate onCreate={vi.fn()} />);

      await user.type(input(), 'rao');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      expect(screen.getByRole('option', { name: /Rao Industries/ })).toBeInTheDocument();

      // Finish typing the name the row already shows, and stop inside the debounce window — no
      // request has gone out for the completed query yet. "Add Rao Industries" over a row reading
      // Rao Industries is how a duplicate customer master gets created.
      await user.type(input(), ' industries');
      expect(createRow()).not.toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      expect(createRow()).not.toBeInTheDocument();
      expect(screen.getAllByRole('option')).toHaveLength(1);
    } finally {
      restoreClock();
    }
  });

  /*
   * Fixed; this is the guard. Creating a customer is a write, and a write is not idempotent: a
   * second Enter while the first is still in flight is two masters with the same name and no
   * client-side undo for either.
   */
  it('creates once when Enter is pressed twice on a create still in flight', async () => {
    const user = userEvent.setup();
    let finish!: (option: SearchSelectOption | null) => void;
    const onCreate = vi.fn(
      () =>
        new Promise<SearchSelectOption | null>((resolve) => {
          finish = resolve;
        }),
    );
    render(<Single options={CUSTOMERS} canCreate onCreate={onCreate} />);

    await user.type(input(), 'Zenith Metals');
    await user.keyboard('{End}');
    expect(activeRowText()).toContain('Add “Zenith Metals”');

    await user.keyboard('{Enter}');
    // The row says it is working, which is the only thing that makes ignoring the second press
    // honest rather than silent.
    expect(panel().querySelector('.pms-btn__spinner')).toBeInTheDocument();
    await user.keyboard('{Enter}');

    expect(onCreate).toHaveBeenCalledTimes(1);

    await act(async () => {
      finish(null);
    });
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  /*
   * Fixed; this is the guard. A rejected *write* with no handling at all is worse than a failed
   * search: the spinner stops, nothing is selected, nothing is said — and the rejection escapes as
   * an unhandled promise, which vitest reports as an error on an otherwise green run.
   *
   * NOTE: what is asserted here is the recovery, not a visible failure state. The control tracks
   * `createFailed` and renders nothing from it, so there is no failure affordance on the create row
   * to assert against — see the finding reported with this change.
   */
  it('survives a rejected onCreate without letting the rejection escape', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const onCreate = vi.fn(async () => {
      throw new Error('customer create failed');
    });
    render(<Single options={CUSTOMERS} canCreate onCreate={onCreate} spy={spy} />);

    await user.type(input(), 'Zenith Metals');
    await user.click(createRow() as HTMLElement);

    expect(onCreate).toHaveBeenCalledTimes(1);
    // Nothing was created, so nothing is selected and the panel stays where the user left it —
    // rather than closing as it does on a resolved-nothing create.
    expect(spy).not.toHaveBeenCalled();
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(input()).toHaveValue('Zenith Metals');
    // The spinner stops: a create row stuck mid-flight would be a permanently dead affordance.
    expect(panel().querySelector('.pms-btn__spinner')).toBeNull();

    // And it can be tried again — the guard is the in-flight one, not a one-shot latch.
    await user.click(createRow() as HTMLElement);
    expect(onCreate).toHaveBeenCalledTimes(2);
  });

  /*
   * Fixed; this is the guard. `createFailed` was tracked and rendered nowhere, so a rejected
   * create stopped the spinner and said nothing at all — indistinguishable from the create that
   * resolved nothing and closed. On a *write* that silence is what gets retried until it
   * duplicates something.
   */
  it('names a failed create and announces it', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn(async () => {
      throw new Error('customer create failed');
    });
    render(<Single options={CUSTOMERS} canCreate onCreate={onCreate} />);

    await user.type(input(), 'Zenith Metals');
    await user.click(createRow() as HTMLElement);

    expect(statusText()).toContain('Couldn’t create “Zenith Metals”');
    // The panel's status lines are aria-hidden, so the live region is what actually says it.
    expect(live()).toHaveTextContent('Couldn’t create “Zenith Metals”');
    // The row itself stays, because the guard is the in-flight one and this is retryable.
    expect(createRow()).toBeInTheDocument();
  });

  it('drops the create failure when the query moves on', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn(async () => {
      throw new Error('customer create failed');
    });
    render(<Single options={CUSTOMERS} canCreate onCreate={onCreate} />);

    await user.type(input(), 'Zenith');
    await user.click(createRow() as HTMLElement);
    expect(statusText()).toContain('Couldn’t create “Zenith”');

    // A failure belongs to the name that produced it, not to the next one.
    await user.type(input(), ' Metals');
    expect(statusText()).not.toContain('Couldn’t create');
    expect(live()).not.toHaveTextContent('Couldn’t create');
  });

  it('appears as the last row and calls onCreate with the trimmed query', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn(async () => null);
    render(<Single options={CUSTOMERS} canCreate onCreate={onCreate} />);

    await user.type(input(), '  Zenith Metals  ');
    const rows = screen.getAllByRole('option');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent('Add “Zenith Metals”');
    expect(rows[0]).toHaveAttribute('aria-selected', 'false');

    await user.keyboard('{ArrowDown}');
    expect(input().getAttribute('aria-activedescendant')).toBe(rows[0]?.id);
    await user.keyboard('{Enter}');

    expect(onCreate).toHaveBeenCalledWith('Zenith Metals');
  });

  it('is reachable as the row after the matches', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn(async () => null);
    render(<Single options={CUSTOMERS} canCreate onCreate={onCreate} />);

    await user.type(input(), 'Rao');
    // One match, then the create row: End has to land on create, not on the match.
    await user.keyboard('{End}');
    expect(activeRowText()).toContain('Add “Rao”');
    await user.keyboard('{ArrowUp}');
    expect(activeRowText()).toContain('Rao Industries');
  });

  it('takes a caller-supplied create label', async () => {
    const user = userEvent.setup();
    render(
      <Single
        options={CUSTOMERS}
        canCreate
        onCreate={vi.fn()}
        createLabel={(q) => `Create customer ${q}`}
      />,
    );

    await user.type(input(), 'Zenith');
    expect(screen.getByRole('option', { name: 'Create customer Zenith' })).toBeInTheDocument();
    expect(createRow()).not.toBeInTheDocument();
  });

  it('selects the option onCreate resolves', async () => {
    const user = userEvent.setup();
    const created: SearchSelectOption = { id: 'new-1', label: 'Zenith Metals' };
    const spy = vi.fn();
    render(
      <Single options={CUSTOMERS} canCreate onCreate={async () => created} spy={spy} />,
    );

    await user.type(input(), 'Zenith Metals');
    await user.click(createRow() as HTMLElement);

    expect(spy).toHaveBeenCalledWith('new-1', created);
    expect(input()).toHaveValue('Zenith Metals');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('appends the created option as a chip in multiple mode', async () => {
    const user = userEvent.setup();
    const created: SearchSelectOption = { id: 'new-1', label: 'Zenith Metals' };
    const spy = vi.fn();
    const { container } = render(
      <Multi
        options={CUSTOMERS}
        initial={['c1']}
        canCreate
        onCreate={async () => created}
        spy={spy}
      />,
    );

    await user.type(input(), 'Zenith Metals');
    await user.click(createRow() as HTMLElement);

    // The input clears so the next name can be typed straight away, while the list keeps the
    // results it was showing — those are two separate pieces of state precisely because
    // clearing both emptied a panel that was deliberately left open.
    expect(input()).toHaveValue('');
    expect(spy).toHaveBeenCalledWith(['c1', 'new-1'], [CUSTOMERS[0], created]);
    expect(
      Array.from(container.querySelectorAll('.pms-search-select__chip-label')).map(
        (node) => node.textContent,
      ),
    ).toEqual(['Sharma Traders', 'Zenith Metals']);
  });

  it('closes and selects nothing when onCreate resolves nothing', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Single options={CUSTOMERS} canCreate onCreate={async () => null} spy={spy} />);

    await user.type(input(), 'Zenith Metals');
    await user.click(createRow() as HTMLElement);

    // The app owns the flow from here — open a form, come back, set `value` (§5.5).
    expect(spy).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('accepts a void onCreate that opens the caller’s own flow', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn<(q: string) => void>();
    render(<Single options={CUSTOMERS} canCreate onCreate={onCreate} />);

    await user.type(input(), 'Zenith Metals');
    await user.click(createRow() as HTMLElement);

    expect(onCreate).toHaveBeenCalledWith('Zenith Metals');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ live region */

describe('SearchSelect — live region', () => {
  it('is silent while the list is closed', () => {
    render(<Single options={CUSTOMERS} />);
    // A region that keeps announcing a list nobody can see is noise, and noise gets muted.
    expect(live()).toHaveTextContent('');
  });

  it('announces the result count, singular and plural', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    expect(live()).toHaveTextContent('7 results');

    await user.type(input(), 'sharma');
    expect(live()).toHaveTextContent('1 result');
  });

  it('announces the empty state', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} emptyLabel="No customers found" />);

    await user.type(input(), 'zzzz');
    expect(live()).toHaveTextContent('No customers found');
  });

  it('goes quiet again when the list closes', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    expect(live()).toHaveTextContent('7 results');
    await user.keyboard('{Escape}');
    expect(live()).toHaveTextContent('');
  });

  it('announces searching, more-available, failure and the minimum length', async () => {
    installFakeClock();
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const pending = deferred();
      const load = vi
        .fn<SearchSelectLoader>()
        .mockReturnValueOnce(pending.promise)
        .mockRejectedValueOnce(new Error('network'));
      render(<Single loadOptions={load} />);

      await user.click(input());
      expect(live()).toHaveTextContent('Type at least 2 characters to search');

      await user.type(input(), 'sh');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      // A list that changes silently does not exist to a screen reader, and "nothing yet" and
      // "still loading" are different facts.
      expect(live()).toHaveTextContent('Searching');

      await act(async () => {
        pending.resolve({ items: remoteRows('a', 2), nextCursor: 'cursor-page-2' });
      });
      expect(live()).toHaveTextContent('2 results, more available');

      await user.type(input(), 'a');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      expect(live()).toHaveTextContent('Search failed');
    } finally {
      restoreClock();
    }
  });
});

/* ------------------------------------------------------------------ positioning */

describe('SearchSelect — positioning contract', () => {
  it('renders the list outside the field, in the body', async () => {
    const user = userEvent.setup();
    const { container } = render(<Single options={CUSTOMERS} />);

    await user.click(input());
    const field = container.querySelector('.pms-search-select') as HTMLElement;
    const list = screen.getByRole('listbox');

    // Absolute positioning inside the field is what made `UserMenu` a clipped sliver in the top
    // bar: any ancestor with `overflow` clips a descendant popover (decision log 20).
    expect(field.contains(list)).toBe(false);
    expect(document.body.contains(list)).toBe(true);
    expect(panel().parentElement).toBe(document.body);
  });

  it('takes its rectangle from an inline style, since no token can express one', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    // Measured at runtime from the field's own rect — the one thing here that is not a token.
    expect(panel().style.position).toBe('fixed');

    const rule = CSS.slice(CSS.indexOf('.pms-search-select__panel {'));
    expect(rule.slice(0, rule.indexOf('}'))).not.toMatch(/position:/);
  });

  it('dresses the panel as a popover, with an edge that survives a dark surface', () => {
    expect(CSS).toMatch(
      /\.pms-search-select__panel \{[^}]*z-index: var\(--pms-z-popover\)/,
    );
    expect(CSS).toMatch(/\.pms-search-select__panel \{[^}]*background: var\(--pms-overlay\)/);
    // In dark the shadow is black on near-black, so the border is what separates list from page
    //.
    expect(CSS).toMatch(
      /\.pms-search-select__panel \{[^}]*border: 1px solid var\(--pms-line-strong\)/,
    );
    expect(CSS).toMatch(
      /\.pms-search-select__panel \{[^}]*box-shadow: var\(--pms-shadow-popover\)/,
    );
  });

  /*
   * The flip, and the capture-phase re-placement that keeps it honest. jsdom computes no layout, so
   * the field's rectangle is supplied — it is the one input the placement has, and the only way to
   * put the field near the bottom of the window without a browser.
   */
  it('flips above the field when there is no room below, and re-places on an ancestor scroll', async () => {
    const user = userEvent.setup();
    const { container } = render(<Single options={CUSTOMERS} />);

    const rect = (top: number, bottom: number): DOMRect =>
      ({
        x: 10,
        y: top,
        top,
        bottom,
        left: 10,
        right: 210,
        width: 200,
        height: bottom - top,
        toJSON: () => ({}),
      }) as DOMRect;

    const control = container.querySelector('.pms-search-select__control') as HTMLElement;
    let current = rect(700, 740);
    control.getBoundingClientRect = () => current;
    const innerHeight = window.innerHeight;
    Object.defineProperty(window, 'innerHeight', { value: 760, configurable: true, writable: true });

    try {
      await user.click(input());
      // 14px below the field, 694 above it: rendering below would put the list off the window.
      expect(panel()).toHaveAttribute('data-flipped', 'true');
      expect(panel().style.bottom).toBe('66px');
      expect(panel().style.top).toBe('');

      // The field moved because something *containing* it scrolled — a card, a toolbar, the main
      // column. A bubbling listener never sees that, which is why the listener is capture-phase.
      current = rect(40, 80);
      fireEvent.scroll(document);

      expect(panel()).not.toHaveAttribute('data-flipped');
      expect(panel().style.top).toBe('86px');
      expect(panel().style.bottom).toBe('');
    } finally {
      Object.defineProperty(window, 'innerHeight', {
        value: innerHeight,
        configurable: true,
        writable: true,
      });
    }
  });

  /*
   * Fixed; this is the guard. `place()` runs on every capture-phase scroll event and built a
   * fresh placement object each time, so a page scrolling under an open list re-rendered the
   * component — and every row in it — per scroll event, for a rectangle that had not moved.
   *
   * `createLabel` is called during render, which makes it the one honest render counter available
   * from outside the component.
   */
  it('does not re-render on a scroll that leaves the field where it was', async () => {
    const user = userEvent.setup();
    const createLabel = vi.fn((q: string) => `Add “${q}”`);
    render(<Single options={CUSTOMERS} canCreate onCreate={vi.fn()} createLabel={createLabel} />);

    await user.type(input(), 'Zenith');
    expect(createLabel).toHaveBeenCalled();

    /*
     * jsdom's rect is all zeroes and never changes, which is exactly the unmoved-field case.
     *
     * Measured as growth *after* the first scroll, not from zero: an updater that returns the
     * identical value is documented to let React render the component once more before bailing
     * out, and that once is not the defect. The defect was renders scaling with scroll events —
     * so twenty more of them have to cost nothing.
     */
    fireEvent.scroll(document);
    const settled = createLabel.mock.calls.length;
    for (let i = 0; i < 20; i += 1) fireEvent.scroll(document);

    expect(createLabel.mock.calls.length).toBe(settled);
    // And the panel is still placed — bailing out must not mean forgetting where it goes.
    expect(panel().style.position).toBe('fixed');
  });

  it('unmounts the portal when the list closes', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    expect(panel()).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(panel()).toBeNull();
  });

  it('closes on a click outside the field', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    await user.click(document.body);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('stays open on a click inside the portalled list', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} emptyLabel="No customers found" />);

    await user.type(input(), 'zzzz');
    // The portal means "inside" is two subtrees: a `contains` check on the field alone would
    // dismiss the list the moment someone clicked it.
    await user.click(panel().querySelector('.pms-search-select__status') as HTMLElement);
    expect(panel()).toBeInTheDocument();
  });

  it('keeps the chevron state on the field, not on the portal', async () => {
    const user = userEvent.setup();
    const { container } = render(<Single options={CUSTOMERS} />);

    const field = container.querySelector('.pms-search-select') as HTMLElement;
    expect(field).not.toHaveAttribute('data-open');
    await user.click(input());
    expect(field).toHaveAttribute('data-open', 'true');
    expect(container.querySelector('.pms-search-select__chevron')).toHaveAttribute(
      'aria-hidden',
      'true',
    );
  });
});

/* ------------------------------------------------------------------ static mode */

describe('SearchSelect — static mode', () => {
  it('shows the whole list on open, because a static list that hides itself reads as broken', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} />);

    await user.click(input());
    // `minQueryLength` defaults to 0 here: there is no query cost to hold back from (§5.5).
    expect(screen.getAllByRole('option')).toHaveLength(7);
    expect(statusText()).toBe('');
  });

  it('still honours an explicit minimum when the caller sets one', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} minQueryLength={3} />);

    await user.click(input());
    expect(screen.queryByRole('option')).not.toBeInTheDocument();
    expect(statusText()).toContain('Type at least 3 characters to search');

    await user.type(input(), 'rao');
    expect(screen.getAllByRole('option')).toHaveLength(1);
  });

  it('caps a long static list and says so', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS} maxOptions={2} />);

    await user.click(input());
    expect(screen.getAllByRole('option')).toHaveLength(2);
    expect(statusText()).toContain('Showing the first 2.');
  });

  it('does not claim truncation when the whole list is exactly maxOptions long', async () => {
    const user = userEvent.setup();
    render(<Single options={CUSTOMERS.slice(0, 3)} maxOptions={3} />);

    await user.click(input());
    // Three of three is not "the first three" — there is nothing to refine towards.
    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(statusText()).not.toContain('Showing the first');
  });

  it('renders the placeholder while nothing is chosen', () => {
    render(<Single options={CUSTOMERS} placeholder="Search customers" />);
    expect(input()).toHaveAttribute('placeholder', 'Search customers');
  });
});

/* --------------------------------------------- regressions these tests were written for */

/**
 * Each of these was a real defect found by writing the test first, and each is now the guard
 * against it coming back. They are gathered together because they share a shape: none of them
 * is visible in a happy-path click-through, and three of the four only misbehave under timing
 * the eye cannot see.
 *
 * The first-paint labelling cases live with their own areas above (`selected` in single and
 * multiple mode, and a value carried by static `options`). All three had one cause: the option
 * cache was a `useRef` filled from a `useEffect`, and mutating a ref renders nothing — so the
 * paint that should have shown the label had already happened and the field came up blank.
 */
describe('SearchSelect — regressions', () => {
  beforeEach(installFakeClock);
  afterEach(restoreClock);

  const setup = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const settle = async (ms = 300) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  };

  /*
   * §5.5: "250ms debounce while typing; none on open." Opening is a deliberate act with a query
   * already in hand — there is no burst to collapse — yet the request waits out the full window,
   * so the first list a user sees is a quarter-second late for no reason.
   */
  it('requests on open without waiting out the typing debounce', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: remoteRows('a', 2), nextCursor: null }));
    render(<Single loadOptions={load} minQueryLength={0} />);

    await user.click(input());
    expect(load).toHaveBeenCalledTimes(1);
  });

  /*
   * The most valuable case in this file. The highlight used to be an **ordinal**, and the auto-page
   * trigger fires precisely when the highlight sits on the last row — so the page that arrived slid
   * a different entity under the highlight and Enter committed it. What the user saw and what the
   * control committed were two different customers; on an invoice that is the wrong customer on a
   * posted document. Tracked by row identity now, with the ordinal derived per render.
   */
  it('commits the row the highlight was on, not the row a fresh page slid underneath it', async () => {
    const user = setup();
    const onCreate = vi.fn(async () => null);
    const spy = vi.fn();
    const load = vi.fn<SearchSelectLoader>(async ({ cursor }) =>
      cursor
        ? { items: remoteRows('a', 3, 4), nextCursor: null }
        : { items: remoteRows('a', 3), nextCursor: 'cursor-page-2' },
    );
    render(<Single loadOptions={load} canCreate onCreate={onCreate} spy={spy} />);

    await user.type(input(), 'sh');
    await settle();
    // Three results and the create row.
    expect(screen.getAllByRole('option')).toHaveLength(4);

    // End lands on the create row — which is also the last row, so it arms the auto-page.
    await user.keyboard('{End}');
    expect(activeRowText()).toContain('Add “sh”');

    await settle();
    expect(load).toHaveBeenCalledTimes(2);
    expect(screen.getAllByRole('option')).toHaveLength(7);
    // Three rows appended beneath it and the highlight did not budge.
    expect(activeRowText()).toContain('Add “sh”');

    await user.keyboard('{Enter}');
    expect(onCreate).toHaveBeenCalledWith('sh');
    // The ordinal the highlight used to hold now belongs to "A row 4" — an entity nobody looked at.
    expect(spy).not.toHaveBeenCalled();
    expect(input()).toHaveValue('sh');
  });

  /*
   * §5.5: "250ms debounce while typing; none on open." `justOpened` was armed on every focus *and*
   * click rather than on the closed → open transition, so clicking to place the caret mid-edit
   * re-armed it — `setOpen(true)` on an already-open list is a no-op, so no render, so nothing
   * consumed the flag — and the next keystroke skipped the debounce and put a request on the wire
   * per character.
   */
  it('does not re-arm the immediate search by clicking a list that is already open', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({
      items: remoteRows('a', 2),
      nextCursor: null,
    }));
    render(<Single loadOptions={load} minQueryLength={2} />);

    await user.click(input());
    await user.type(input(), 'sh');
    await settle();
    expect(load).toHaveBeenCalledTimes(1);

    // The most ordinary thing a person does mid-edit: click into the text to move the caret.
    await user.click(input());
    await user.type(input(), 'a');
    /*
     * Asserted *before* the clock moves, which is the whole point: `settle()` advances
     * unconditionally, so after it a debounce that was skipped and one that was honoured look
     * exactly alike. The existing minimum-length tests could not have caught this.
     */
    expect(load).toHaveBeenCalledTimes(1);

    await settle();
    expect(load).toHaveBeenCalledTimes(2);
    expect(load.mock.calls[1]?.[0]).toMatchObject({ q: 'sha', cursor: null });
  });

  /*
   * `onQueryChange` exists so a caller can mirror what was typed into a heading or lift it into the
   * URL. Every keystroke reports, so the two clears the control performs *itself* have to report
   * too — otherwise the URL keeps a filter the field no longer holds, and a reload restores it.
   */
  it('reports an empty query when the control clears itself', async () => {
    const user = setup();
    const onQueryChange = vi.fn();
    render(<Single options={CUSTOMERS} initial="c1" onQueryChange={onQueryChange} />);

    await user.type(input(), 'rao');
    expect(onQueryChange).toHaveBeenLastCalledWith('rao');

    // First Escape closes the list; the second is the one that clears the query.
    await user.keyboard('{Escape}');
    await user.keyboard('{Escape}');
    expect(input()).toHaveValue('Sharma Traders');
    expect(onQueryChange).toHaveBeenLastCalledWith('');

    onQueryChange.mockClear();
    await user.type(input(), 'rao');
    await user.click(screen.getByRole('button', { name: 'Clear Customer' }));
    expect(onQueryChange).toHaveBeenLastCalledWith('');
  });

  /*
   * Fixed; this is the guard, and the one with money at the end of it. The create row must never
   * offer a name the server already holds. The guard was `query.trim() === filterQuery.trim()` —
   * but both are set in the same keystroke handler, so it was never false; and `loading` is still
   * false inside the debounce window, because no request has started yet. So on the async path a
   * name that exists looked new for 250ms, and one Enter created a duplicate customer master.
   *
   * The comparison has to be against the query the rows on screen actually *answer*, which only
   * a settled response can tell you.
   */
  it('offers no create row for a name the server holds but the settled list has not seen', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async ({ q }) => ({
      items: q.trim().toLowerCase().startsWith('zen') ? [{ id: 'c9', label: 'Zenith Metals' }] : [],
      nextCursor: null,
    }));
    const onCreate = vi.fn(async () => null);
    render(<Single loadOptions={load} canCreate onCreate={onCreate} />);

    // Settle on a query that matches nothing, where the create row is legitimately offered.
    await user.type(input(), 'zz');
    await settle();
    expect(screen.getByRole('option', { name: 'Add “zz”' })).toBeInTheDocument();

    // Now type the full name of a customer that does exist, and stop inside the debounce window.
    await user.clear(input());
    await user.type(input(), 'Zenith Metals');
    expect(load).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('option', { name: /^Add/ })).not.toBeInTheDocument();

    // The fastest possible Enter cannot reach it either.
    await user.keyboard('{End}{Enter}');
    expect(onCreate).not.toHaveBeenCalled();

    // And once the list has caught up, the existing row is the answer.
    await settle();
    expect(screen.getByRole('option', { name: /Zenith Metals/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /^Add/ })).not.toBeInTheDocument();
  });

  /* Same guard from the other side: below the minimum nothing has been searched at all, so
   * there is no basis on which to claim the name is new. */
  it('offers no create row below the minimum query length', async () => {
    const user = setup();
    const load = vi.fn<SearchSelectLoader>(async () => ({ items: [], nextCursor: null }));
    const onCreate = vi.fn(async () => null);
    render(<Single loadOptions={load} canCreate onCreate={onCreate} minQueryLength={3} />);

    await user.type(input(), 'ze');
    await settle();

    expect(load).not.toHaveBeenCalled();
    expect(screen.queryByRole('option', { name: /^Add/ })).not.toBeInTheDocument();
  });

  /*
   * Fixed; this is the guard. The two clears the control performs itself on Escape and on the
   * clear button reported an empty query; the third — the one a *commit* performs — did not. A
   * caller mirroring the query into the URL kept a filter the field no longer held, and a reload
   * restored it.
   */
  it('reports an empty query when a commit clears the input', async () => {
    const user = setup();
    const onQueryChange = vi.fn();
    const { unmount } = render(<Multi options={CUSTOMERS} onQueryChange={onQueryChange} />);

    await user.type(input(), 'rao');
    expect(onQueryChange).toHaveBeenLastCalledWith('rao');
    await user.click(screen.getByRole('option', { name: /Rao Industries/ }));
    expect(input()).toHaveValue('');
    expect(onQueryChange).toHaveBeenLastCalledWith('');
    unmount();

    // Single mode clears both the input and the filter, so it has even more to report.
    const single = vi.fn();
    render(<Single options={CUSTOMERS} onQueryChange={single} />);
    await user.type(input(), 'rao');
    await user.click(screen.getByRole('option', { name: /Rao Industries/ }));
    expect(single).toHaveBeenLastCalledWith('');
  });

  /*
   * §5.5: results "cap at `maxOptions` and say so, rather than paging forever". The paging effect
   * was not guarded by the cap, and `loadMore`'s identity changed twice per request
   * (`loadingMore` true then false), so it re-fired with the highlight still on the last row: a
   * capped list sitting on its last row requested page after page and sliced every one away.
   * The loader stops offering a cursor after eight pages only so a regression can terminate.
   */
  it('stops requesting once the accumulated list is capped', async () => {
    const user = setup();
    let page = 0;
    const load = vi.fn<SearchSelectLoader>(async () => {
      page += 1;
      return { items: remoteRows(`p${page}`, 5), nextCursor: page < 8 ? `cursor-${page}` : null };
    });
    render(<Single loadOptions={load} maxOptions={3} />);

    await user.type(input(), 'sh');
    await settle();
    await user.keyboard('{End}');
    await settle();

    expect(load).toHaveBeenCalledTimes(1);
  });

  /*
   * Same effect, reached the honest way: a page that comes back empty with a cursor still set
   * (a filtered keyset page, which api-conventions §2.1 explicitly allows) leaves `rowCount`
   * unchanged, so the highlight is still on the last row and the next page is requested at once —
   * on repeat, as fast as the network answers.
   */
  it('asks for one more page, not every page, when a page comes back empty', async () => {
    const user = setup();
    let page = 0;
    const load = vi.fn<SearchSelectLoader>(async ({ cursor }) => {
      page += 1;
      if (!cursor) return { items: remoteRows('a', 2), nextCursor: 'cursor-1' };
      return { items: [], nextCursor: page < 8 ? `cursor-${page}` : null };
    });
    render(<Single loadOptions={load} />);

    await user.type(input(), 'sh');
    await settle();
    await user.keyboard('{End}');
    await settle();

    expect(load).toHaveBeenCalledTimes(2);
  });

  /*
   * `aria-describedby` used to list both ids while only one of the two paragraphs is ever
   * rendered, so with a hint *and* an error the field pointed at an element that did not exist.
   * Harmless to a browser, silently dropped by AT — and only ever found by asserting that every
   * idref resolves.
   */
  it('never describes the field by an element that is not in the document', () => {
    render(<Single options={CUSTOMERS} hint="Search by name or code." error="Pick a customer." />);

    const ids = (input().getAttribute('aria-describedby') ?? '').split(' ').filter(Boolean);
    expect(ids.filter((id) => !document.getElementById(id))).toEqual([]);
  });
});
