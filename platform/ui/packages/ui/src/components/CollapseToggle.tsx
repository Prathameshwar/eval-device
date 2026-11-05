'use client';

import { IconButton } from './IconButton';
import { PanelCollapseIcon } from './icons-console';

/**
 * The rail's collapse control. The accessible name states the *action*, not the state, and
 * flips with it — "Collapse sidebar" on an expanded rail — while `aria-expanded` carries
 * the state itself, so a screen reader gets both without the name lying.
 */
export function CollapseToggle({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const label = collapsed ? 'Expand sidebar' : 'Collapse sidebar';

  return (
    <IconButton
      label={label}
      icon={<PanelCollapseIcon />}
      aria-expanded={!collapsed}
      onClick={onToggle}
      className={`pms-collapse${collapsed ? ' pms-collapse--collapsed' : ''}`}
    />
  );
}
