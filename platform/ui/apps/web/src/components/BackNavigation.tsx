import Link from 'next/link';
import { ChevronLeftIcon } from '@pms/ui';

type BackNavigationProps = { label: string } & (
  | { href: string; onBack?: never; disabled?: never }
  | { href?: never; onBack: () => void; disabled?: boolean }
);

/** Explicit parent links and guarded in-page returns share one presentation. */
export function BackNavigation(props: BackNavigationProps) {
  const content = <><ChevronLeftIcon size={16} /><span>{props.label}</span></>;
  return <nav aria-label="Back navigation" className="pms-console__back-navigation">
    {props.href !== undefined
      ? <Link className="pms-console__back-control" href={props.href}>{content}</Link>
      : <button className="pms-console__back-control" type="button" disabled={props.disabled} onClick={props.onBack}>{content}</button>}
  </nav>;
}
