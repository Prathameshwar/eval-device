/**
 * Page-composition primitives. jsdom does no layout, so these
 * assert structure, heading level, slot branches, roles and the keyboard model — the things
 * that break silently and that a screenshot wouldn't catch anyway.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { PageHeader } from '../src/components/PageHeader';
import { SectionHeader } from '../src/components/SectionHeader';
import { Tabs, tabButtonId } from '../src/components/Tabs';
import { Toolbar } from '../src/components/Toolbar';
import { DashboardIcon } from '../src/components/icons-console';

const DATA_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'data.css'), 'utf8');

describe('PageHeader', () => {
  it('renders the title as the page h1', () => {
    render(<PageHeader title="Revenue" />);
    expect(screen.getByRole('heading', { level: 1, name: 'Revenue' })).toBeInTheDocument();
  });

  it('omits overline, lede and actions when not given', () => {
    const { container } = render(<PageHeader title="Revenue" />);
    expect(container.querySelector('.pms-overline')).toBeNull();
    expect(container.querySelector('.pms-lede')).toBeNull();
    expect(container.querySelector('.pms-page-header__actions')).toBeNull();
  });

  it('renders overline, lede and actions when given', () => {
    const { container } = render(
      <PageHeader
        overline="Console"
        title="Revenue"
        lede="Everything invoiced this period."
        actions={<button type="button">New invoice</button>}
      />,
    );
    expect(screen.getByText('Console')).toHaveClass('pms-overline');
    expect(screen.getByText('Everything invoiced this period.')).toHaveClass('pms-lede');
    expect(screen.getByRole('button', { name: 'New invoice' })).toBeInTheDocument();
    expect(container.querySelector('.pms-page-header__actions')).not.toBeNull();
  });
});

describe('SectionHeader', () => {
  it('renders the title as an h2 so the outline descends from the page h1', () => {
    render(<SectionHeader title="Top customers" />);
    expect(screen.getByRole('heading', { level: 2, name: 'Top customers' })).toBeInTheDocument();
  });

  it('brand-tints the overline and renders the icon and description', () => {
    const { container } = render(
      <SectionHeader
        overline="Receivables"
        icon={<DashboardIcon />}
        title="Top customers"
        description="Ranked by invoiced value."
      />,
    );
    const overline = screen.getByText('Receivables');
    expect(overline).toHaveClass('pms-overline');
    expect(overline).toHaveClass('pms-overline--brand');
    expect(container.querySelector('.pms-section-header__icon svg')).not.toBeNull();
    expect(screen.getByText('Ranked by invoiced value.')).toBeInTheDocument();
  });

  it('omits the icon, overline and description when not given', () => {
    const { container } = render(<SectionHeader title="Top customers" />);
    expect(container.querySelector('.pms-section-header__icon')).toBeNull();
    expect(container.querySelector('.pms-overline')).toBeNull();
    expect(container.querySelector('.pms-section-header__desc')).toBeNull();
  });
});

describe('Toolbar', () => {
  it('renders both slots', () => {
    const { container } = render(
      <Toolbar left={<span>4 series</span>} right={<button type="button">Filters</button>} />,
    );
    expect(screen.getByText('4 series')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Filters' })).toBeInTheDocument();
    expect(container.querySelectorAll('.pms-toolbar__side')).toHaveLength(2);
  });

  it('renders no empty flex children when a slot is absent', () => {
    const { container } = render(<Toolbar right={<span>Refresh</span>} />);
    const sides = container.querySelectorAll('.pms-toolbar__side');
    expect(sides).toHaveLength(1);
    expect(sides[0]).toHaveClass('pms-toolbar__side--end');
  });

  it('renders an empty toolbar with no slots at all', () => {
    const { container } = render(<Toolbar />);
    expect(container.querySelectorAll('.pms-toolbar__side')).toHaveLength(0);
  });
});

const TABS = [
  { id: 'day', label: 'Today' },
  { id: 'week', label: 'This week' },
  { id: 'month', label: 'This month' },
];

function renderTabs(active = 'day') {
  const onChange = vi.fn();
  const view = render(<Tabs tabs={TABS} active={active} onChange={onChange} label="Range" />);
  return { onChange, ...view };
}

describe('Tabs', () => {
  it('is a named tablist with one selected tab', () => {
    renderTabs('week');
    expect(screen.getByRole('tablist', { name: 'Range' })).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByRole('tab', { name: 'This week' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Today' })).toHaveAttribute('aria-selected', 'false');
  });

  it('makes only the active tab a tab stop', () => {
    renderTabs('week');
    expect(screen.getByRole('tab', { name: 'This week' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'Today' })).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('tab', { name: 'This month' })).toHaveAttribute('tabindex', '-1');
  });

  it('activates on click', async () => {
    const { onChange } = renderTabs();
    await userEvent.click(screen.getByRole('tab', { name: 'This month' }));
    expect(onChange).toHaveBeenCalledWith('month');
  });

  it('moves and activates with ArrowRight, wrapping at the end', async () => {
    const { onChange } = renderTabs();
    const first = screen.getByRole('tab', { name: 'Today' });
    first.focus();

    await userEvent.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenLastCalledWith('week');
    expect(screen.getByRole('tab', { name: 'This week' })).toHaveFocus();

    // Still on `active="day"` (uncontrolled here), so wrapping is driven from the last tab.
    screen.getByRole('tab', { name: 'This month' }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenLastCalledWith('day');
    expect(screen.getByRole('tab', { name: 'Today' })).toHaveFocus();
  });

  it('moves and activates with ArrowLeft, wrapping at the start', async () => {
    const { onChange } = renderTabs();
    screen.getByRole('tab', { name: 'Today' }).focus();

    await userEvent.keyboard('{ArrowLeft}');
    expect(onChange).toHaveBeenLastCalledWith('month');
    expect(screen.getByRole('tab', { name: 'This month' })).toHaveFocus();

    screen.getByRole('tab', { name: 'This month' }).focus();
    await userEvent.keyboard('{ArrowLeft}');
    expect(onChange).toHaveBeenLastCalledWith('week');
  });

  it('jumps to the ends with Home and End', async () => {
    const { onChange } = renderTabs('week');
    screen.getByRole('tab', { name: 'This week' }).focus();

    await userEvent.keyboard('{End}');
    expect(onChange).toHaveBeenLastCalledWith('month');
    expect(screen.getByRole('tab', { name: 'This month' })).toHaveFocus();

    await userEvent.keyboard('{Home}');
    expect(onChange).toHaveBeenLastCalledWith('day');
    expect(screen.getByRole('tab', { name: 'Today' })).toHaveFocus();
  });

  it('ignores keys outside the tab pattern', async () => {
    const { onChange } = renderTabs();
    screen.getByRole('tab', { name: 'Today' }).focus();
    await userEvent.keyboard('{ArrowUp}');
    await userEvent.keyboard('a');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('points every tab at the panel it controls, and carries an id the panel can name it by', () => {
    // `role="tab"` with no `aria-controls` and no `role="tabpanel"` anywhere promises a
    // screen-reader user a view that changed — an incomplete ARIA pattern.
    render(
      <Tabs tabs={TABS} active="day" onChange={vi.fn()} label="Range" panelId="range-panel" />,
    );

    for (const tab of screen.getAllByRole('tab')) {
      expect(tab).toHaveAttribute('aria-controls', 'range-panel');
    }
    expect(screen.getByRole('tab', { name: 'Today' })).toHaveAttribute('id', tabButtonId('day', 'range-panel'));
    expect(screen.getByRole('tab', { name: 'This week' })).toHaveAttribute(
      'id',
      tabButtonId('week', 'range-panel'),
    );
  });

  it('omits aria-controls when no panel is wired, rather than pointing at nothing', () => {
    renderTabs();
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab).not.toHaveAttribute('aria-controls');
      // The id is unconditional: a panel elsewhere can still be labelled by its tab.
      expect(tab.id).not.toBe('');
    }
  });

  it('derives a tab id from the tab id, stably', () => {
    expect(tabButtonId('day')).toBe(tabButtonId('day'));
    expect(tabButtonId('day')).not.toBe(tabButtonId('week'));
    expect(tabButtonId('day')).toContain('day');
  });

  it('does nothing when the tab list is empty', async () => {
    const onChange = vi.fn();
    render(<Tabs tabs={[]} active="" onChange={onChange} label="Range" />);
    expect(screen.getByRole('tablist', { name: 'Range' })).toBeEmptyDOMElement();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('vertical rhythm of a page column', () => {
  /*
   * jsdom computes no layout, so the stylesheet is the assertion. What is worth pinning is not
   * the pixel values but the *shape* of the rule set: spacing stated per relationship, from one
   * mechanism. A uniform `gap` on the column is what this replaced — it put a toolbar as far
   * from its own section heading as from an unrelated block, and it compounded with
   * `.pms-meta`'s own top margin.
   */
  it('spaces the column with margins, not a uniform gap', () => {
    const page = DATA_CSS.slice(DATA_CSS.indexOf('.pms-page {'), DATA_CSS.indexOf('.pms-grid {'));
    const pageRule = page.slice(0, page.indexOf('}'));

    expect(pageRule).not.toMatch(/\bgap:/);
    expect(DATA_CSS).toContain('.pms-page > * + *');
    expect(DATA_CSS).toContain('.pms-flow > * + *');
  });

  it('states each relationship rather than one distance for everything', () => {
    // A section heading introduces what follows it, so that pair is tight…
    expect(DATA_CSS).toContain('.pms-flow > .pms-section-header + *');
    // …a new section is a bigger break than a block inside one…
    expect(DATA_CSS).toContain('.pms-flow > * + .pms-section-header');
    // …the meta line is a caption on the toolbar above it, not a block of its own…
    expect(DATA_CSS).toContain('.pms-flow > .pms-toolbar + .pms-meta');
    // …and two bands of cards keep the grid's own gutter, so vertical matches horizontal.
    expect(DATA_CSS).toMatch(/\.pms-flow > :is\(\.pms-grid, \.pms-stat-row\) \+ :is\(/);
  });

  it('offers the rhythm as a utility, because a page is not the only such column', () => {
    // The console nests a `role="tabpanel"` inside `.pms-page`; it carries `.pms-flow`
    // rather than restating the column and its spacing, which is how the two drifted before.
    expect(DATA_CSS).toMatch(/\.pms-page,\n\.pms-flow \{\n  display: flex;/);
  });
});
