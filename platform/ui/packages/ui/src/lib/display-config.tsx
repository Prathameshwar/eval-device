'use client';

import { createContext, useContext, useMemo, type ReactNode } from 'react';
import {
  DEFAULT_DISPLAY_CONFIG,
  formatCompact,
  formatDate,
  formatDateTime,
  formatMoney,
  formatPercent,
  formatQuantity,
  formatRange,
  formatRelative,
  type DisplayConfig,
  type MoneyOptions,
} from './format';

/**
 * Consumers supply display preferences. This provider merges explicit values with defaults;
 * it has no dependency on a company, tenant, session, or backend preference endpoint.
 */
const DisplayConfigContext = createContext<DisplayConfig | null>(null);

type DisplayConfigProviderProps = {
  /** Partial: anything absent keeps the default, so a half-populated payload still renders. */
  config?: Partial<DisplayConfig>;
  children: ReactNode;
};

/** An explicit `undefined` in the payload must not erase a default by spreading over it. */
function mergeConfig(base: DisplayConfig, partial: Partial<DisplayConfig> | undefined): DisplayConfig {
  if (!partial) return base;
  const merged: DisplayConfig = { ...base };
  for (const [key, value] of Object.entries(partial) as [keyof DisplayConfig, unknown][]) {
    if (value !== undefined) {
      Object.assign(merged, { [key]: value });
    }
  }
  return merged;
}

export function DisplayConfigProvider({ config, children }: DisplayConfigProviderProps) {
  // Nested providers layer over the enclosing config, not over the bare default, so a screen
  // can override one field (a foreign-currency panel's symbol, say) without restating the rest.
  const parent = useContext(DisplayConfigContext);
  const resolved = useMemo(
    () => mergeConfig(parent ?? DEFAULT_DISPLAY_CONFIG, config),
    [parent, config],
  );

  return <DisplayConfigContext.Provider value={resolved}>{children}</DisplayConfigContext.Provider>;
}

/**
 * Falls back to `DEFAULT_DISPLAY_CONFIG` when no provider is mounted. A formatter hook that
 * threw would blank a whole page over a display preference — the wrong failure mode for
 * something that is only presentation.
 */
export function useDisplayConfig(): DisplayConfig {
  return useContext(DisplayConfigContext) ?? DEFAULT_DISPLAY_CONFIG;
}

export type Formatters = {
  money: (value: string | null | undefined, opts?: MoneyOptions) => string;
  quantity: (value: string | null | undefined, opts?: { precision?: number }) => string;
  compact: (value: string | null | undefined) => string;
  percent: (value: string | null | undefined, places?: number) => string;
  date: (iso: string | null | undefined) => string;
  dateTime: (iso: string | null | undefined) => string;
  range: (startIso: string | null | undefined, endIso: string | null | undefined) => string;
  /** `now` is injectable for tests; production callers omit it. */
  relative: (iso: string | null | undefined, now?: number) => string;
};

/**
 * Config-bound formatters. Components take a config or a formatted string and never a raw
 * figure plus an inline format call, which is how a stray `toLocaleString` gets in.
 */
export function useFormatters(): Formatters {
  const config = useDisplayConfig();
  return useMemo<Formatters>(
    () => ({
      money: (value, opts) => formatMoney(value, config, opts),
      quantity: (value, opts) => formatQuantity(value, config, opts),
      compact: (value) => formatCompact(value, config),
      percent: (value, places) => formatPercent(value, config, places),
      date: (iso) => formatDate(iso, config),
      dateTime: (iso) => formatDateTime(iso, config),
      range: (startIso, endIso) => formatRange(startIso, endIso, config),
      relative: (iso, now) => formatRelative(iso, config, now),
    }),
    [config],
  );
}
