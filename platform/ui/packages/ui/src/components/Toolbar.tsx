import type { ReactNode } from 'react';

type ToolbarProps = {
  /** Labels, counts, the "what am I looking at" side. */
  left?: ReactNode;
  /** Controls: range select, refresh, overflow, filters. */
  right?: ReactNode;
};

/**
 * The row of controls above a data region. The trailing side is pushed by `margin-left:auto`
 * rather than `space-between`, so a toolbar with only a `right` slot still sits right.
 */
export function Toolbar({ left, right }: ToolbarProps) {
  return (
    <div className="pms-toolbar">
      {left ? <div className="pms-toolbar__side">{left}</div> : null}
      {right ? <div className="pms-toolbar__side pms-toolbar__side--end">{right}</div> : null}
    </div>
  );
}
