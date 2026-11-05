/**
 * Display config provider tests. The behaviours that matter: a missing provider must not blank a
 * page, a partial payload must not erase defaults, and the bound formatters must follow the
 * config rather than the environment.
 */
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';
import {
  DisplayConfigProvider,
  useDisplayConfig,
  useFormatters,
} from '../src/lib/display-config';
import { DEFAULT_DISPLAY_CONFIG, type DisplayConfig } from '../src/lib/format';

function ShowConfig() {
  const config = useDisplayConfig();
  return (
    <dl>
      <dt>currency</dt>
      <dd>{config.currency}</dd>
      <dt>grouping</dt>
      <dd>{config.digitGrouping}</dd>
      <dt>amountPrecision</dt>
      <dd>{String(config.amountPrecision)}</dd>
      <dt>timezone</dt>
      <dd>{config.timezone}</dd>
    </dl>
  );
}

function ShowFormatted({ iso = '2026-03-05T18:30:00Z' }: { iso?: string }) {
  const format = useFormatters();
  return (
    <ul>
      <li>{format.money('1234567.895')}</li>
      <li>{format.money(null)}</li>
      <li>{format.money('1234.5', { display: 'code' })}</li>
      <li>{format.quantity('2.5')}</li>
      <li>{format.compact('41600000')}</li>
      <li>{format.percent('18.55')}</li>
      <li>{format.date(iso)}</li>
      <li>{format.dateTime(iso)}</li>
      <li>{format.range(iso, '2026-04-02T06:00:00Z')}</li>
      {/* A fixed `now`, so this line does not change meaning tomorrow. */}
      <li>{format.relative(iso, Date.parse('2026-03-05T21:30:00Z'))}</li>
    </ul>
  );
}

const wrap = (config: Partial<DisplayConfig> | undefined, children: ReactNode) =>
  render(<DisplayConfigProvider config={config}>{children}</DisplayConfigProvider>);

describe('useDisplayConfig', () => {
  it('falls back to the default with no provider mounted', () => {
    render(<ShowConfig />);
    expect(screen.getByText(DEFAULT_DISPLAY_CONFIG.currency)).toBeInTheDocument();
    expect(screen.getByText('indian')).toBeInTheDocument();
    expect(screen.getByText('Asia/Kolkata')).toBeInTheDocument();
  });

  it('resolves to the default when the provider is given no config yet', () => {
    render(
      <DisplayConfigProvider>
        <ShowConfig />
      </DisplayConfigProvider>,
    );
    expect(screen.getByText('INR')).toBeInTheDocument();
    expect(screen.getByText('indian')).toBeInTheDocument();
  });

  it('merges a partial config over the defaults', () => {
    wrap({ currency: 'USD', digitGrouping: 'western' }, <ShowConfig />);
    expect(screen.getByText('USD')).toBeInTheDocument();
    expect(screen.getByText('western')).toBeInTheDocument();
    // Untouched keys keep their default.
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('Asia/Kolkata')).toBeInTheDocument();
  });

  it('does not let an explicit undefined erase a default', () => {
    wrap({ currency: undefined, timezone: undefined }, <ShowConfig />);
    expect(screen.getByText('INR')).toBeInTheDocument();
    expect(screen.getByText('Asia/Kolkata')).toBeInTheDocument();
  });

  it('layers a nested provider over the enclosing config', () => {
    render(
      <DisplayConfigProvider config={{ currency: 'USD', digitGrouping: 'western' }}>
        <DisplayConfigProvider config={{ currency: 'EUR' }}>
          <ShowConfig />
        </DisplayConfigProvider>
      </DisplayConfigProvider>,
    );
    expect(screen.getByText('EUR')).toBeInTheDocument();
    expect(screen.getByText('western')).toBeInTheDocument();
  });
});

describe('useFormatters', () => {
  it('produces default-config output with no provider', () => {
    render(<ShowFormatted />);
    expect(screen.getByText('₹12,34,567.90')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('1,234.50 INR')).toBeInTheDocument();
    expect(screen.getByText('2.5000')).toBeInTheDocument();
    expect(screen.getByText('4.2Cr')).toBeInTheDocument();
    expect(screen.getByText('18.6%')).toBeInTheDocument();
    // 18:30Z is already the next day in Asia/Kolkata.
    expect(screen.getByText('06 Mar 2026')).toBeInTheDocument();
    expect(screen.getByText('06 Mar 2026, 00:00')).toBeInTheDocument();
    expect(screen.getByText('06 Mar 2026 – 02 Apr 2026')).toBeInTheDocument();
    expect(screen.getByText('3 hours ago')).toBeInTheDocument();
  });

  it('follows the provided config for grouping, currency, precision, zone and rounding', () => {
    wrap(
      {
        currency: 'USD',
        currencySymbol: '$',
        digitGrouping: 'western',
        amountPrecision: 0,
        quantityPrecision: 2,
        roundingMode: 'floor',
        timezone: 'UTC',
        dateFormat: 'yyyy-MM-dd',
        datetimeFormat: 'yyyy-MM-dd HH:mm',
        locale: 'de-DE',
      },
      <ShowFormatted />,
    );
    expect(screen.getByText('$1,234,567')).toBeInTheDocument();
    expect(screen.getByText('1,234 USD')).toBeInTheDocument();
    expect(screen.getByText('2.50')).toBeInTheDocument();
    expect(screen.getByText('41.6M')).toBeInTheDocument();
    expect(screen.getByText('2026-03-05')).toBeInTheDocument();
    expect(screen.getByText('2026-03-05 18:30')).toBeInTheDocument();
    expect(screen.getByText('2026-03-05 – 2026-04-02')).toBeInTheDocument();
    // Relative wording is zone-independent below a day, so this line reads the same either way.
    expect(screen.getByText('3 hours ago')).toBeInTheDocument();
  });
});
