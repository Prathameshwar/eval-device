/**
 * `Select`.
 *
 * Checked through `getByLabelText` almost everywhere on purpose: that query only passes if the
 * label really is associated with the control, which is the whole reason this is a native
 * `<select>` and not a styled div. The rest of the file is the states a form actually goes
 * through — empty, chosen, invalid, disabled, still loading its choices — because each one is a
 * separate branch and a control that renders three of the five is a control that ships blank
 * screens.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Select, type SelectItem } from '../src/components/Select';

const RANGES: SelectItem[] = [
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'fy', label: 'This fiscal year' },
];

/** Two groups and a disabled row — the shape a currency or tax-rate list really has. */
const CURRENCIES: SelectItem[] = [
  { label: 'Reporting', options: [{ value: 'INR', label: 'Indian rupee' }] },
  {
    label: 'Foreign',
    options: [
      { value: 'USD', label: 'US dollar' },
      { value: 'AED', label: 'UAE dirham', disabled: true },
    ],
  },
];

function control(name = 'Range'): HTMLSelectElement {
  return screen.getByLabelText(name) as HTMLSelectElement;
}

describe('Select — structure', () => {
  it('associates its visible label with the native control', () => {
    render(<Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} />);
    expect(control().tagName).toBe('SELECT');
    expect(control()).toHaveValue('7d');
  });

  it('renders every option', () => {
    render(<Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} />);
    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(screen.getByRole('option', { name: 'This fiscal year' })).toBeInTheDocument();
  });

  it('wears the shared field and input classes, so it lines up with a text field', () => {
    const { container } = render(
      <Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} />,
    );
    expect(container.querySelector('.pms-select')).toHaveClass('pms-field');
    expect(control()).toHaveClass('pms-input');
    expect(control()).toHaveClass('pms-select__control');
  });

  it('is stacked by default and inline when asked', () => {
    const { container: stacked } = render(
      <Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} />,
    );
    expect(stacked.querySelector('.pms-select')).not.toHaveClass('pms-select--inline');

    const { container: inline } = render(
      <Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} inline />,
    );
    expect(inline.querySelector('.pms-select')).toHaveClass('pms-select--inline');
  });

  it('gives each instance its own id, so two selects on a page stay labelled', () => {
    render(
      <>
        <Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} />
        <Select label="Company" value="7d" options={RANGES} onChange={vi.fn()} />
      </>,
    );
    expect(control('Range').id).not.toBe(control('Company').id);
  });

  it('lets the caller own the id and still points the label at it', () => {
    render(<Select id="range-picker" label="Range" value="7d" options={RANGES} onChange={vi.fn()} />);
    expect(control().id).toBe('range-picker');
  });

  it('hides the caret from assistive technology — it repeats the control’s own shape', () => {
    const { container } = render(
      <Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} />,
    );
    const caret = container.querySelector('.pms-select__caret');
    expect(caret).toHaveAttribute('aria-hidden', 'true');
    expect(caret?.querySelector('svg')).not.toBeNull();
  });

  it('keeps the label as the accessible name when it is hidden from the layout', () => {
    const { container } = render(
      <Select hideLabel label="Range" value="7d" options={RANGES} onChange={vi.fn()} />,
    );
    // Still found by its label — hidden from sight is not hidden from the accessibility tree.
    expect(control()).toBeInTheDocument();
    // The label itself is clipped; with nothing else in it there is no row left to clip.
    expect(screen.getByText('Range')).toHaveClass('pms-visually-hidden');
    expect(container.querySelector('.pms-field__row')).toBeNull();
  });

  it('leaves the action visible when the label is hidden', () => {
    render(
      <Select
        hideLabel
        label="Range"
        value="7d"
        options={RANGES}
        onChange={vi.fn()}
        action={<button type="button">Edit ranges</button>}
      />,
    );

    // `pms-visually-hidden` clips rather than removes, so hiding the whole row left this button
    // focusable and invisible — a tab stop a sighted keyboard user cannot see (WCAG 2.4.7).
    const action = screen.getByRole('button', { name: 'Edit ranges' });
    expect(action.closest('.pms-visually-hidden')).toBeNull();
    expect(screen.getByText('Range')).toHaveClass('pms-visually-hidden');
  });
});

describe('Select — choosing', () => {
  it('reports the chosen value, not the event', async () => {
    const onChange = vi.fn();
    render(<Select label="Range" value="7d" options={RANGES} onChange={onChange} />);
    await userEvent.selectOptions(control(), '30d');
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('30d');
  });

  it('reports the empty string when the placeholder is chosen back', async () => {
    const onChange = vi.fn();
    render(
      <Select
        label="Company"
        placeholder="All companies"
        value="7d"
        options={RANGES}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(control('Company'), '');
    // A filter has to be clearable, so the empty choice is a real value the caller receives.
    expect(onChange).toHaveBeenCalledWith('');
  });

  it('passes native handlers straight through', async () => {
    const onBlur = vi.fn();
    render(<Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} onBlur={onBlur} />);
    await userEvent.click(control());
    await userEvent.tab();
    expect(onBlur).toHaveBeenCalled();
  });

  it('renders a group as an optgroup and keeps a disabled row unchoosable', () => {
    const { container } = render(
      <Select label="Currency" value="INR" options={CURRENCIES} onChange={vi.fn()} />,
    );
    const groups = container.querySelectorAll('optgroup');
    expect([...groups].map((group) => group.label)).toEqual(['Reporting', 'Foreign']);
    expect(screen.getByRole('option', { name: 'US dollar' })).not.toBeDisabled();
    expect(screen.getByRole('option', { name: 'UAE dirham' })).toBeDisabled();
  });

  it('finds a value inside a group, so no placeholder is invented for it', () => {
    render(<Select label="Currency" value="USD" options={CURRENCIES} onChange={vi.fn()} />);
    expect(control('Currency')).toHaveValue('USD');
    expect(screen.queryByRole('option', { name: 'Select…' })).toBeNull();
  });
});

describe('Select — the empty choice', () => {
  it('renders the placeholder first, with an empty value', () => {
    render(
      <Select
        label="Company"
        placeholder="All companies"
        value=""
        options={RANGES}
        onChange={vi.fn()}
      />,
    );
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(4);
    expect(options[0]).toHaveTextContent('All companies');
    expect(options[0]).toHaveValue('');
    expect(control('Company')).toHaveValue('');
  });

  it('leaves the placeholder choosable on an optional field', () => {
    render(
      <Select
        label="Company"
        placeholder="All companies"
        value=""
        options={RANGES}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('option', { name: 'All companies' })).not.toBeDisabled();
  });

  it('makes the placeholder unchoosable when the field is required', () => {
    render(
      <Select
        required
        label="Company"
        placeholder="Choose a company"
        value=""
        options={RANGES}
        onChange={vi.fn()}
      />,
    );
    /* This is what makes native constraint validation reject "nothing picked": the empty option
     * is selected but cannot be chosen, so the control is invalid until something else is. */
    expect(screen.getByRole('option', { name: 'Choose a company' })).toBeDisabled();
    expect(control('Company')).toBeRequired();
  });

  /*
   * The trap this closes: React sets `value` on the element, and a value matching no option
   * leaves `selectedIndex` at -1 — a control rendering blank, with nothing to tell the reader
   * that apart from "nothing chosen yet".
   */
  it('says nothing is selected rather than rendering blank for an unmatched value', () => {
    render(<Select label="Range" value="ytd" options={RANGES} onChange={vi.fn()} />);
    expect(screen.getByRole('option', { name: 'Select…' })).toBeInTheDocument();
    expect(control()).toHaveValue('');
  });

  it('adds no empty row when the value matches and no placeholder was asked for', () => {
    render(<Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} />);
    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(screen.queryByRole('option', { name: 'Select…' })).toBeNull();
  });

  it('renders a placeholder-only list when there are no options at all', () => {
    render(<Select label="Company" placeholder="No companies yet" value="" options={[]} onChange={vi.fn()} />);
    expect(screen.getAllByRole('option')).toHaveLength(1);
  });
});

describe('Select — hint, error and validity', () => {
  it('renders a hint and points the control at it', () => {
    render(
      <Select
        label="Range"
        hint="Buckets follow the posting date."
        value="7d"
        options={RANGES}
        onChange={vi.fn()}
      />,
    );
    const hint = screen.getByText('Buckets follow the posting date.');
    expect(control()).toHaveAttribute('aria-describedby', hint.id);
    expect(control()).not.toHaveAttribute('aria-invalid');
  });

  it('announces an error, marks the control invalid and flags the field for CSS', () => {
    const { container } = render(
      <Select label="Range" error="Pick a range." value="" options={RANGES} onChange={vi.fn()} />,
    );
    const error = screen.getByRole('alert');
    expect(error).toHaveTextContent('Pick a range.');
    // Paired with a glyph: a colour-only error is invisible to a colour-blind reader (§7).
    expect(error.querySelector('svg')).not.toBeNull();
    expect(control()).toHaveAttribute('aria-invalid', 'true');
    expect(control()).toHaveAttribute('aria-describedby', error.id);
    expect(container.querySelector('.pms-select')).toHaveAttribute('data-invalid', 'true');
  });

  it('shows the error instead of the hint, and never references the paragraph it dropped', () => {
    render(
      <Select
        label="Range"
        hint="Buckets follow the posting date."
        error="Pick a range."
        value=""
        options={RANGES}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByText('Buckets follow the posting date.')).toBeNull();
    /* A dangling idref is dropped silently by assistive technology, so referencing an id that
     * did not render would quietly lose the description that did. */
    const described = control().getAttribute('aria-describedby');
    expect(described).toBe(screen.getByRole('alert').id);
  });

  it('describes nothing when there is nothing to describe', () => {
    render(<Select label="Range" value="7d" options={RANGES} onChange={vi.fn()} />);
    expect(control()).not.toHaveAttribute('aria-describedby');
  });
});

describe('Select — disabled and loading', () => {
  it('disables the control and flags the field', () => {
    const { container } = render(
      <Select disabled label="Range" value="7d" options={RANGES} onChange={vi.fn()} />,
    );
    expect(control()).toBeDisabled();
    expect(container.querySelector('.pms-select')).toHaveAttribute('data-disabled', 'true');
  });

  it('submits nothing while disabled — that is what disabling a field means', () => {
    const { container } = render(
      <Select disabled name="range" label="Range" value="7d" options={RANGES} onChange={vi.fn()} />,
    );
    // Native `disabled` already excludes the select; no hidden input may put it back.
    expect(container.querySelector('input[type="hidden"]')).toBeNull();
  });

  it('carries the value in a name so a plain form submit works', () => {
    render(<Select name="range" label="Range" value="7d" options={RANGES} onChange={vi.fn()} />);
    expect(control()).toHaveAttribute('name', 'range');
  });

  it('names the busy state rather than only spinning at the reader', () => {
    const { container } = render(
      <Select loading label="Currency" value="" options={[]} onChange={vi.fn()} />,
    );
    const busy = screen.getByRole('status');
    expect(busy).toHaveTextContent('Loading…');
    expect(control('Currency')).toHaveAttribute('aria-busy', 'true');
    expect(control('Currency')).toHaveAttribute('aria-describedby', busy.id);
    // Inoperable: there is nothing to choose from yet.
    expect(control('Currency')).toBeDisabled();
    // The caret slot holds the spinner, not a chevron that promises an openable list.
    expect(container.querySelector('.pms-select__caret .pms-spinner')).not.toBeNull();
    expect(container.querySelector('.pms-select__caret svg')).toBeNull();
  });

  it('takes the caller’s word for what is loading', () => {
    render(
      <Select
        loading
        loadingLabel="Fetching tax rates…"
        label="Tax rate"
        value=""
        options={[]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Fetching tax rates…');
    expect(screen.getByRole('option', { name: 'Fetching tax rates…' })).toBeDisabled();
  });

  /*
   * Busy is not the same as withheld. `disabled` drops a control from form submission, which is
   * what a caller means by `disabled` and never what they mean by `loading` — so a value already
   * chosen must survive a reload of the choices behind it.
   */
  it('still submits an already-chosen value while the choices reload', () => {
    const { container } = render(
      <Select loading name="range" label="Range" value="7d" options={RANGES} onChange={vi.fn()} />,
    );
    const hidden = container.querySelector<HTMLInputElement>('input[type="hidden"]');
    expect(hidden).not.toBeNull();
    expect(hidden).toHaveAttribute('name', 'range');
    expect(hidden).toHaveValue('7d');
  });

  it('mirrors nothing when there is nothing chosen yet', () => {
    const { container } = render(
      <Select loading name="range" label="Range" value="" options={RANGES} onChange={vi.fn()} />,
    );
    expect(container.querySelector('input[type="hidden"]')).toBeNull();
  });

  it('keeps an error on screen while the choices reload', () => {
    render(
      <Select
        loading
        label="Range"
        error="Pick a range."
        value=""
        options={RANGES}
        onChange={vi.fn()}
      />,
    );
    /* Reloading the choices does not make a validation error untrue, so both lines render and
     * both are referenced. */
    const described = control().getAttribute('aria-describedby')?.split(' ') ?? [];
    expect(described).toContain(screen.getByRole('status').id);
    expect(described).toContain(screen.getByRole('alert').id);
  });

  it('cannot be changed while it is loading', async () => {
    const onChange = vi.fn();
    render(<Select loading label="Range" value="7d" options={RANGES} onChange={onChange} />);
    await userEvent.click(control());
    expect(onChange).not.toHaveBeenCalled();
  });
});
