'use client';

import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { THEME_PREFERENCES, type ThemePreference } from '../lib/theme';
import { ContrastIcon, MonitorIcon, MoonIcon, SunIcon } from './icons-console';
import { useTheme } from './ThemeProvider';

const PRESENTATION: Record<ThemePreference, { label: string; icon: ReactNode }> = {
  light: { label: 'Light', icon: <SunIcon size={16} /> },
  dark: { label: 'Dark', icon: <MoonIcon size={16} /> },
  ledger: { label: 'Ledger', icon: <ContrastIcon size={16} /> },
  system: { label: 'System', icon: <MonitorIcon size={16} /> },
};

/* Order comes from the shared catalogue, not a second hand-written list — adding a
 * preference then can't leave the switcher a value short. */
const OPTIONS = THEME_PREFERENCES.map((value) => ({ value, ...PRESENTATION[value] }));

type ThemeSwitcherProps = {
  /** The group's accessible name. A radiogroup with no name is an unlabelled control. */
  label?: string;
  className?: string;
};

/**
 * The segmented theme control: a real radiogroup, so arrow keys move *and* select and the
 * group is a single tab stop. The icon is the only visible content, so
 * each option's name lives in `aria-label` and in `title` for the hover tooltip.
 */
export function ThemeSwitcher({ label = 'Theme', className = '' }: ThemeSwitcherProps) {
  const { preference, setPreference } = useTheme();
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);

  const selectAt = (index: number): void => {
    const option = OPTIONS[index];
    if (!option) return;
    setPreference(option.value);
    // Selection follows focus in a radiogroup, so focus must follow the arrow key too.
    buttons.current[index]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number): void => {
    const last = OPTIONS.length - 1;
    let next: number | null = null;

    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        next = index === last ? 0 : index + 1;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        next = index === 0 ? last : index - 1;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = last;
        break;
      default:
        return;
    }

    event.preventDefault();
    selectAt(next);
  };

  const classes = ['pms-theme-switcher', className].filter(Boolean).join(' ');

  return (
    <div className={classes} role="radiogroup" aria-label={label}>
      {OPTIONS.map((option, index) => {
        const checked = option.value === preference;
        return (
          <button
            key={option.value}
            ref={(node) => {
              buttons.current[index] = node;
            }}
            type="button"
            className="pms-theme-switcher__option"
            role="radio"
            aria-checked={checked}
            aria-label={option.label}
            title={option.label}
            /* Roving tabindex: the group is one tab stop, and Tab lands on the selection. */
            tabIndex={checked ? 0 : -1}
            onClick={() => setPreference(option.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            <span className="pms-theme-switcher__icon" aria-hidden="true">
              {option.icon}
            </span>
          </button>
        );
      })}
    </div>
  );
}
