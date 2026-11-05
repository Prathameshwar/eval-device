import type { ReactNode } from 'react';

type PageHeaderProps = {
  /** Letterspaced uppercase label above the title — where you are, not what this is. */
  overline?: ReactNode;
  title: ReactNode;
  lede?: ReactNode;
  /** Primary/secondary actions for the whole page, right-aligned on the title's band. */
  actions?: ReactNode;
};

/**
 * The top of every page. It owns the page's single `<h1>`, which is why
 * no other primitive here renders one — a screen with two `h1`s has no outline.
 */
export function PageHeader({ overline, title, lede, actions }: PageHeaderProps) {
  return (
    <header className="pms-page-header">
      <div className="pms-page-header__text">
        {overline ? <p className="pms-overline">{overline}</p> : null}
        <h1 className="pms-h1">{title}</h1>
        {lede ? <p className="pms-lede">{lede}</p> : null}
      </div>
      {actions ? <div className="pms-page-header__actions">{actions}</div> : null}
    </header>
  );
}
