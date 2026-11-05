/*
 * BarChart — the "over time" panel of the console: one series, horizontal gridlines,
 * a right-aligned annotation for the top of the scale, nothing else.
 *
 * Hand-rolled SVG on purpose (design-system decision 8): no chart dependency until one
 * is justified. Colour is never chosen here — the caller picks a *slot* (`series`) and
 * chart.css maps that slot to `--pms-chart-N`, so the bars repaint per theme with no JS.
 */
import type { ReactElement } from 'react';

export type BarChartDatum = {
  label: string;
  /** Money and quantities are strings end to end (design-system decision 10). */
  value: string;
};

/** A slot in the ordered categorical palette, never a hue picked at the call site. */
export type BarChartSeries = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export type BarChartProps = {
  data: BarChartDatum[];
  /** The chart's accessible name — also the caption of the data table twin. */
  ariaLabel: string;
  /** Top of the scale, as a string. Omitted, the largest datum sets it. */
  max?: string;
  series?: BarChartSeries;
  /** Applied to every value a reader sees. Defaults to the string as given. */
  formatValue?: (value: string) => string;
  height?: number;
};

/*
 * The drawing is authored in a fixed 720-unit-wide coordinate space and scaled by the
 * browser (`preserveAspectRatio`), so there is no measuring, no resize observer and no
 * layout read — which is also why it renders identically under test.
 */
const VIEW_W = 720;
const PAD_TOP = 22; // the top gridline; the annotation sits above it
const PAD_BOTTOM = 20; // the x-label band — never let the axis fall outside the box
const PAD_X = 8;
const MIN_HEIGHT = 120;
const BAR_MAX_W = 24; // cap the mark; the band's leftover is air, not more bar
const BAR_GAP = 2; // surface gap between neighbours — separation without a stroke
const CAP_RADIUS = 4; // rounded data-end, square at the baseline
const GRID_LINES = 4; // bands, so 5 candidate rules including the two edges
const TICK_DROP = 6; // x-label baseline above the bottom edge

const asGiven = (value: string): string => value;

/** Round to 2dp so coordinate strings stay short and free of float dust. */
const u = (value: number): string => String(Math.round(value * 100) / 100);

/*
 * The one place a value becomes a number, and it is geometry only: bar heights are pixel
 * math. Nothing derived from here is ever rendered — every value a reader sees comes from
 * the caller's original string. Crossing that line reintroduces exactly the float coercion
 * the string-money rule exists to prevent.
 */
function toMagnitude(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

/**
 * A bar as a path rather than a rect: a rect's `rx` would round the baseline end too,
 * which reads as a floating mark. Grows either way from the zero line, so a negative
 * value is drawn rather than dropped.
 */
function barPath(x: number, width: number, base: number, end: number): string {
  const reach = Math.abs(end - base);
  const radius = Math.min(CAP_RADIUS, width / 2, reach);
  const towards = end <= base ? 1 : -1; // 1 = grows up out of the baseline
  const cap = end + towards * radius;
  const right = x + width;
  return [
    `M ${u(x)} ${u(base)}`,
    `L ${u(x)} ${u(cap)}`,
    `Q ${u(x)} ${u(end)} ${u(x + radius)} ${u(end)}`,
    `L ${u(right - radius)} ${u(end)}`,
    `Q ${u(right)} ${u(end)} ${u(right)} ${u(cap)}`,
    `L ${u(right)} ${u(base)}`,
    'Z',
  ].join(' ');
}

export function BarChart({
  data,
  ariaLabel,
  max,
  series = 1,
  formatValue,
  height = 240,
}: BarChartProps): ReactElement {
  const show = formatValue ?? asGiven;

  if (data.length === 0) {
    // An axis with no scale is worse than a sentence, so draw no SVG at all.
    return (
      <div className="pms-chart" data-series={series}>
        <p className="pms-visually-hidden">{ariaLabel}</p>
        <p className="pms-chart__empty">No data to display</p>
      </div>
    );
  }

  // Clamped so a too-short box can never invert the plot and push the axis off the canvas.
  const boxHeight = Math.max(MIN_HEIGHT, height);
  const plotTop = PAD_TOP;
  const plotBottom = boxHeight - PAD_BOTTOM;
  const plotHeight = plotBottom - plotTop;
  const plotLeft = PAD_X;
  const plotWidth = VIEW_W - PAD_X * 2;

  const magnitudes = data.map((datum) => toMagnitude(datum.value));
  let peak = 0;
  for (let i = 1; i < magnitudes.length; i += 1) {
    if ((magnitudes[i] ?? 0) > (magnitudes[peak] ?? 0)) peak = i;
  }

  const scaleTop = max === undefined ? (magnitudes[peak] ?? 0) : toMagnitude(max);
  const scaleBottom = Math.min(0, ...magnitudes); // negatives extend the scale below zero
  const span = scaleTop - scaleBottom;

  /* A zero or inverted span (every value 0, or `max="0"`) would divide by zero — the bars
   * simply rest on the baseline instead. */
  const yOf = (value: number): number =>
    span > 0
      ? plotBottom - ((clamp(value, scaleBottom, scaleTop) - scaleBottom) / span) * plotHeight
      : plotBottom;
  const zeroY = yOf(0);

  const band = plotWidth / data.length;
  const barWidth = Math.max(1, Math.min(BAR_MAX_W, band - BAR_GAP));

  /* Thin crowded labels instead of rotating them into illegibility, and thin from the end
   * so the most recent period always keeps its label. Every label stays in the table. */
  const longestLabel = data.reduce((longest, datum) => Math.max(longest, datum.label.length), 0);
  const labelSlot = Math.max(28, longestLabel * 6.2);
  const tickStep = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(plotWidth / labelSlot))));

  const gridYs = Array.from({ length: GRID_LINES + 1 }, (_, i) => plotTop + (plotHeight / GRID_LINES) * i)
    // the zero line is drawn once, as the axis
    .filter((y) => Math.abs(y - zeroY) > 1);

  /* The annotation is a value a reader READS, so it is the caller's string — the `max`
   * prop, or the peak datum's own value — never `scaleTop`, which is float pixel input. */
  const scaleTopLabel = show(max ?? data[peak]?.value ?? '');

  return (
    <div className="pms-chart" data-series={series}>
      <svg
        className="pms-chart__svg"
        role="img"
        aria-label={ariaLabel}
        width={VIEW_W}
        height={boxHeight}
        viewBox={`0 0 ${VIEW_W} ${boxHeight}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <title>{ariaLabel}</title>

        {gridYs.map((y) => (
          <line
            key={`grid-${u(y)}`}
            className="pms-chart__gridline"
            x1={u(plotLeft)}
            x2={u(plotLeft + plotWidth)}
            y1={u(y)}
            y2={u(y)}
          />
        ))}
        <line
          className="pms-chart__axis"
          x1={u(plotLeft)}
          x2={u(plotLeft + plotWidth)}
          y1={u(zeroY)}
          y2={u(zeroY)}
        />

        {data.map((datum, i) => (
          <path
            key={`bar-${i}-${datum.label}`}
            className="pms-chart__bar"
            d={barPath(plotLeft + band * i + (band - barWidth) / 2, barWidth, zeroY, yOf(magnitudes[i] ?? 0))}
          >
            {/* Hover readout only. The table twin is what makes the values reachable. */}
            <title>{`${datum.label}: ${show(datum.value)}`}</title>
          </path>
        ))}

        <text
          className="pms-chart__annotation pms-figure"
          x={u(plotLeft + plotWidth)}
          y={u(plotTop - 7)}
          textAnchor="end"
        >
          {scaleTopLabel}
        </text>

        {data.map((datum, i) =>
          (data.length - 1 - i) % tickStep === 0 ? (
            <text
              key={`tick-${i}-${datum.label}`}
              className="pms-chart__tick"
              x={u(plotLeft + band * i + band / 2)}
              y={u(boxHeight - TICK_DROP)}
              textAnchor="middle"
            >
              {datum.label}
            </text>
          ) : null,
        )}
      </svg>

      {/* The accessible equivalent of the picture — and the reason a hand-rolled chart is
          acceptable here. Tick text is decoration; this table is the data. */}
      <table className="pms-visually-hidden">
        <caption>{ariaLabel}</caption>
        <thead>
          <tr>
            <th scope="col">Label</th>
            <th scope="col">Value</th>
          </tr>
        </thead>
        <tbody>
          {data.map((datum, i) => (
            <tr key={`row-${i}-${datum.label}`}>
              <th scope="row">{datum.label}</th>
              <td className="pms-figure">{show(datum.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
