/**
 * BarChart — a hand-rolled SVG, so its correctness is structural: geometry, attributes and
 * the accessible table twin. jsdom does no layout, so nothing here asserts on pixels.
 *
 * The load-bearing test is `keeps displayed values as the caller's strings`: the chart is
 * allowed to parse a value for pixel math, and that is exactly the boundary a later change
 * silently crosses (design-system decision 10).
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BarChart } from '../src/components/BarChart';

const MONTHS = [
  { label: 'Jan', value: '1200.0000' },
  { label: 'Feb', value: '2400.0000' },
  { label: 'Mar', value: '600.0000' },
];

function bars(container: HTMLElement): SVGPathElement[] {
  return [...container.querySelectorAll<SVGPathElement>('.pms-chart__bar')];
}

/** The bar's data-end y, read out of the path's first quadratic (the rounded cap). */
function endY(bar: Element): number {
  const match = /Q (-?[\d.]+) (-?[\d.]+) /.exec(bar.getAttribute('d') ?? '');
  return Number(match?.[2]);
}

/** The bar's baseline y, read out of the opening move. */
function baseY(bar: Element): number {
  const match = /^M (-?[\d.]+) (-?[\d.]+)/.exec(bar.getAttribute('d') ?? '');
  return Number(match?.[2]);
}

/** Signed height: positive grows up out of the zero line. */
function reach(bar: Element): number {
  return baseY(bar) - endY(bar);
}

/** The bar's left edge, read out of the opening move. */
function leftX(bar: Element): number {
  return Number(/^M (-?[\d.]+)/.exec(bar.getAttribute('d') ?? '')?.[1]);
}

/** Width, from the left edge to the x of the closing quadratic (the far cap). */
function barWidth(bar: Element): number {
  const quadratics = [...(bar.getAttribute('d') ?? '').matchAll(/Q (-?[\d.]+) /g)];
  return Number(quadratics[1]?.[1]) - leftX(bar);
}

function gridYs(container: HTMLElement): number[] {
  return [...container.querySelectorAll('.pms-chart__gridline')].map((line) =>
    Number(line.getAttribute('y1')),
  );
}

function axisY(container: HTMLElement): number {
  return Number(container.querySelector('.pms-chart__axis')?.getAttribute('y1'));
}

function everyAttributeValue(container: HTMLElement): string[] {
  return [...container.querySelectorAll('*')].flatMap((el) => [...el.attributes].map((a) => a.value));
}

describe('BarChart', () => {
  it('renders one bar per data point', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue by month" />);
    expect(bars(container)).toHaveLength(3);
  });

  it('names itself for assistive technology, by role and by <title>', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue by month" />);

    expect(screen.getByRole('img', { name: 'Revenue by month' })).toBeInTheDocument();
    expect(container.querySelector('svg > title')?.textContent).toBe('Revenue by month');
  });

  it('scales fluidly: a viewBox, preserveAspectRatio, and height driving the box', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue" height={320} />);
    const svg = container.querySelector('svg');

    expect(svg).toHaveAttribute('viewBox', '0 0 720 320');
    expect(svg).toHaveAttribute('preserveAspectRatio', 'xMidYMid meet');
    expect(svg).toHaveAttribute('height', '320');
  });

  it('renders a visually-hidden table twin — a captioned row per data point', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue by month" />);
    const table = container.querySelector('table');

    expect(table).toHaveClass('pms-visually-hidden');
    expect(table?.querySelector('caption')?.textContent).toBe('Revenue by month');
    expect(table?.querySelectorAll('tbody tr')).toHaveLength(3);
    expect(screen.getByRole('rowheader', { name: 'Feb' })).toBeInTheDocument();
  });

  it('passes every value a reader sees through formatValue', () => {
    const { container } = render(
      <BarChart data={MONTHS} ariaLabel="Revenue" formatValue={(v) => `₹${v}`} />,
    );
    const cells = [...container.querySelectorAll('tbody td')].map((td) => td.textContent);

    expect(cells).toEqual(['₹1200.0000', '₹2400.0000', '₹600.0000']);
    // the per-bar hover readout is formatted too
    expect(bars(container)[1]?.querySelector('title')?.textContent).toBe('Feb: ₹2400.0000');
  });

  it('keeps displayed values as the caller’s strings, never a parsed float', () => {
    const precise = [{ label: 'Q1', value: '1234567.8912' }];
    const { container } = render(
      <BarChart data={precise} ariaLabel="Spend" formatValue={(v) => `${v} INR`} />,
    );

    // the table cell, the hover readout and the scale annotation all read the string
    expect(container.querySelector('tbody td')?.textContent).toBe('1234567.8912 INR');
    expect(bars(container)[0]?.querySelector('title')?.textContent).toBe('Q1: 1234567.8912 INR');
    expect(container.querySelector('.pms-chart__annotation')?.textContent).toBe('1234567.8912 INR');

    // nothing rendered may look like the value round-tripped through a JS number
    expect(container.textContent).not.toContain('1234567.89 ');
    expect(container.textContent).not.toContain('1234568');
  });

  it('annotates the scale top from the max prop, right-aligned', () => {
    const { container } = render(
      <BarChart data={MONTHS} ariaLabel="Revenue" max="5000.0000" formatValue={(v) => `${v}`} />,
    );
    const annotation = container.querySelector('.pms-chart__annotation');

    expect(annotation?.textContent).toBe('5000.0000');
    expect(annotation).toHaveAttribute('text-anchor', 'end');
    expect(annotation).toHaveClass('pms-figure');
  });

  it('sizes bars in proportion to their value against an explicit max', () => {
    const data = [
      { label: 'a', value: '25' },
      { label: 'b', value: '50' },
      { label: 'c', value: '100' },
    ];
    const { container } = render(<BarChart data={data} ariaLabel="Share" max="100" />);
    const [a, b, c] = bars(container);

    expect(reach(b!) / reach(a!)).toBeCloseTo(2, 5);
    expect(reach(c!) / reach(a!)).toBeCloseTo(4, 5);
    // the full-value bar reaches the top gridline; no bar overflows the plot
    expect(endY(c!)).toBeCloseTo(Math.min(...gridYs(container)), 5);
  });

  it('halves the tallest bar when max is twice the largest value', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue" max="4800" />);
    const plotHeight = baseY(bars(container)[0]!) - Math.min(...gridYs(container));

    expect(reach(bars(container)[1]!)).toBeCloseTo(plotHeight / 2, 5);
  });

  it('infers the max from the data when none is given', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue" />);
    const [jan, feb, mar] = bars(container);

    // Feb is the peak, so it reaches the top gridline and the others scale off it
    expect(endY(feb!)).toBeCloseTo(Math.min(...gridYs(container)), 5);
    expect(reach(jan!) / reach(feb!)).toBeCloseTo(0.5, 5);
    expect(reach(mar!) / reach(feb!)).toBeCloseTo(0.25, 5);
    // and the annotation is the peak datum's own string, not a recomputed number
    expect(container.querySelector('.pms-chart__annotation')?.textContent).toBe('2400.0000');
  });

  it('renders an empty state rather than a broken axis, with no NaN anywhere', () => {
    const { container } = render(<BarChart data={[]} ariaLabel="Revenue by month" />);

    expect(screen.getByText('No data to display')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeNull();
    expect(screen.getByText('Revenue by month')).toHaveClass('pms-visually-hidden');
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  });

  it('survives a zero max without dividing by zero', () => {
    const { container } = render(
      <BarChart data={[{ label: 'Jan', value: '1200' }]} ariaLabel="Revenue" max="0" />,
    );

    expect(everyAttributeValue(container).some((v) => /NaN|Infinity/.test(v))).toBe(false);
    // nothing to scale against, so the bar rests flat on the baseline
    expect(reach(bars(container)[0]!)).toBe(0);
  });

  it('survives an all-zero dataset', () => {
    const zeros = [
      { label: 'Jan', value: '0.0000' },
      { label: 'Feb', value: '0.0000' },
    ];
    const { container } = render(<BarChart data={zeros} ariaLabel="Revenue" />);

    expect(everyAttributeValue(container).some((v) => /NaN|Infinity/.test(v))).toBe(false);
    expect(bars(container).every((bar) => reach(bar) === 0)).toBe(true);
  });

  it('treats an unparseable value as no bar, but still shows the caller’s string', () => {
    const { container } = render(
      <BarChart data={[{ label: 'Jan', value: 'n/a' }]} ariaLabel="Revenue" max="100" />,
    );

    expect(everyAttributeValue(container).some((v) => /NaN|Infinity/.test(v))).toBe(false);
    expect(reach(bars(container)[0]!)).toBe(0);
    expect(container.querySelector('tbody td')?.textContent).toBe('n/a');
  });

  it('draws negatives downward from a zero baseline that sits inside the plot', () => {
    const data = [
      { label: 'Jan', value: '100' },
      { label: 'Feb', value: '-50' },
    ];
    const { container } = render(<BarChart data={data} ariaLabel="Net revenue" />);
    const [jan, feb] = bars(container);
    const zero = axisY(container);

    expect(baseY(jan!)).toBeCloseTo(zero, 5);
    expect(reach(jan!)).toBeGreaterThan(0); // grows up
    expect(reach(feb!)).toBeLessThan(0); // grows down
    expect(reach(feb!) / reach(jan!)).toBeCloseTo(-0.5, 5);
    // the zero line is no longer the bottom of the plot — the scale extends below it
    expect(zero).toBeLessThan(Math.max(...gridYs(container)));
  });

  it.each([1, 2, 3, 4, 5, 6, 7, 8] as const)('selects palette slot %i by index', (series) => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue" series={series} />);

    expect(container.querySelector('.pms-chart')).toHaveAttribute('data-series', String(series));
  });

  it('defaults to slot 1 — series 1 is the primary', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue" />);
    expect(container.querySelector('.pms-chart')).toHaveAttribute('data-series', '1');
  });

  it('maps every slot to its --pms-chart-N token in chart.css, not in TSX', () => {
    const css = readFileSync(join(__dirname, '..', 'src', 'styles', 'chart.css'), 'utf8');

    for (const n of [1, 2, 3, 4, 5, 6, 7, 8]) {
      expect(css).toMatch(
        new RegExp(`\\[data-series='${n}'\\][^{]*\\{[^}]*var\\(--pms-chart-${n}\\)`),
      );
    }
    expect(css).toContain('var(--pms-chart-grid)');
    expect(css).toContain('var(--pms-chart-axis)');
  });

  it('thins crowded x labels rather than rotating them, always keeping the last', () => {
    const dense = Array.from({ length: 31 }, (_, i) => ({
      label: `2026-01-${String(i + 1).padStart(2, '0')}`,
      value: String(i + 1),
    }));
    const { container } = render(<BarChart data={dense} ariaLabel="Daily spend" />);
    const ticks = [...container.querySelectorAll('.pms-chart__tick')].map((t) => t.textContent);

    expect(ticks.length).toBeLessThan(dense.length);
    expect(ticks.at(-1)).toBe('2026-01-31');
    // thinned labels are decoration only — every one is still in the table
    expect(container.querySelectorAll('tbody tr')).toHaveLength(31);
  });

  it('labels every point when there is room', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue" />);
    const ticks = [...container.querySelectorAll('.pms-chart__tick')].map((t) => t.textContent);

    expect(ticks).toEqual(['Jan', 'Feb', 'Mar']);
  });

  it('caps bar thickness at 24 units — the band’s leftover is air, not more bar', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue" />);
    const [first, second] = bars(container);

    expect(barWidth(first!)).toBeCloseTo(24, 5);
    // one band apart — coordinates are rounded to 2dp, hence the loose tolerance
    expect(leftX(second!) - leftX(first!)).toBeCloseTo(704 / 3, 1);
  });

  it('keeps the x-label band inside the box even at an absurd height', () => {
    const { container } = render(<BarChart data={MONTHS} ariaLabel="Revenue" height={40} />);
    const boxHeight = Number(container.querySelector('svg')?.getAttribute('height'));
    const tickY = Number(container.querySelector('.pms-chart__tick')?.getAttribute('y'));

    expect(boxHeight).toBe(120); // clamped, so the plot can never invert
    expect(tickY).toBeLessThan(boxHeight);
    expect(axisY(container)).toBeLessThan(tickY); // axis above its labels, not off-canvas
  });

  it('never draws a bar narrower than a unit, however many points arrive', () => {
    const flood = Array.from({ length: 400 }, (_, i) => ({ label: `p${i}`, value: String(i + 1) }));
    const { container } = render(<BarChart data={flood} ariaLabel="Events" />);

    // a floor of one unit, less the 2dp rounding of the coordinates themselves
    expect(Math.min(...bars(container).map(barWidth))).toBeGreaterThan(0.98);
    expect(everyAttributeValue(container).some((v) => /NaN|Infinity/.test(v))).toBe(false);
  });

  it('keeps a 2-unit surface gap between neighbours when the band is narrow', () => {
    const dense = Array.from({ length: 31 }, (_, i) => ({ label: `d${i}`, value: String(i + 1) }));
    const { container } = render(<BarChart data={dense} ariaLabel="Daily spend" />);
    const [first, second] = bars(container);
    const band = leftX(second!) - leftX(first!);

    expect(barWidth(first!)).toBeLessThan(24);
    expect(band - barWidth(first!)).toBeCloseTo(2, 5);
  });
});
