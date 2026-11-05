/**
 * Permission gating tests. This layer is presentation only — these
 * tests assert what is *drawn*, and prove the default is deny, never "show it and hope".
 */
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';
import {
  Can,
  PermissionProvider,
  useCan,
  useGranted,
  usePermissions,
} from '../src/lib/permissions';

function Probe({ permission }: { permission: string }) {
  return <span data-testid="probe">{useCan(permission) ? 'allowed' : 'denied'}</span>;
}

function Count() {
  return <span data-testid="count">{String(usePermissions().length)}</span>;
}

const withPermissions = (permissions: readonly string[], children: ReactNode) =>
  render(<PermissionProvider permissions={permissions}>{children}</PermissionProvider>);

const verdict = (): string | null => screen.getByTestId('probe').textContent;

describe('useCan', () => {
  it('allows an exactly held key', () => {
    withPermissions(['invoice.read', 'payment.read'], <Probe permission="invoice.read" />);
    expect(verdict()).toBe('allowed');
  });

  it('denies a key that is not held', () => {
    withPermissions(['invoice.read'], <Probe permission="invoice.write" />);
    expect(verdict()).toBe('denied');
  });

  it('denies with no provider — an unknown set is not a permitted one', () => {
    render(<Probe permission="invoice.read" />);
    expect(verdict()).toBe('denied');
  });

  it('denies against an empty set', () => {
    withPermissions([], <Probe permission="invoice.read" />);
    expect(verdict()).toBe('denied');
  });

  it('honours a trailing :* wildcard on the granted key', () => {
    withPermissions(['invoice.*'], <Probe permission="invoice.read" />);
    expect(verdict()).toBe('allowed');
  });

  it('lets a wildcard span deeper keys', () => {
    withPermissions(['invoice.*'], <Probe permission="invoice.line:write" />);
    expect(verdict()).toBe('allowed');
  });

  it('does not let a wildcard leak past its prefix', () => {
    withPermissions(['invoice.*'], <Probe permission="payment.read" />);
    expect(verdict()).toBe('denied');
  });

  it('does not treat a partial prefix as a wildcard match', () => {
    withPermissions(['invoice.*'], <Probe permission="invoicesummary:read" />);
    expect(verdict()).toBe('denied');
  });

  it('treats a bare * as everything', () => {
    withPermissions(['*'], <Probe permission="company.delete" />);
    expect(verdict()).toBe('allowed');
  });

  it('exposes the raw resolved set', () => {
    withPermissions(['invoice.read', 'invoice.write'], <Count />);
    expect(screen.getByTestId('count').textContent).toBe('2');
  });
});

describe('useGranted', () => {
  type Item = { id: string; permission?: string };

  /** A menu's items, filtered in one pass — the case `useCan` cannot serve. */
  function Items({ items }: { items: readonly Item[] }) {
    const granted = useGranted();
    const kept = items.filter((item) => granted(item.permission)).map((item) => item.id);
    return <span data-testid="probe">{kept.length === 0 ? 'none' : kept.join(',')}</span>;
  }

  const MENU: readonly Item[] = [
    { id: 'view', permission: 'invoice.read' },
    { id: 'void', permission: 'invoice.void' },
    { id: 'note' },
  ];

  it('filters a list against the resolved set', () => {
    withPermissions(['invoice.read'], <Items items={MENU} />);
    expect(verdict()).toBe('view,note');
  });

  it('applies the same wildcard rule as useCan', () => {
    withPermissions(['invoice.*'], <Items items={MENU} />);
    expect(verdict()).toBe('view,void,note');
  });

  it('passes an ungated item — the caller never claimed to restrict it', () => {
    withPermissions([], <Items items={MENU} />);
    expect(verdict()).toBe('note');
  });

  it('grants only the ungated with no provider mounted', () => {
    render(<Items items={MENU.slice(0, 2)} />);
    expect(verdict()).toBe('none');
  });
});

describe('<Can>', () => {
  it('renders its children when permitted', () => {
    withPermissions(
      ['invoice.write'],
      <Can permission="invoice.write">
        <button type="button">Post invoice</button>
      </Can>,
    );
    expect(screen.getByRole('button', { name: 'Post invoice' })).toBeInTheDocument();
  });

  it('renders nothing when denied — no placeholder, no disabled ghost', () => {
    const { container } = withPermissions(
      ['invoice.read'],
      <Can permission="invoice.write">
        <button type="button">Post invoice</button>
      </Can>,
    );
    expect(screen.queryByRole('button', { name: 'Post invoice' })).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the fallback when one is given', () => {
    withPermissions(
      ['invoice.read'],
      <Can permission="invoice.write" fallback={<p>Ask an approver</p>}>
        <button type="button">Post invoice</button>
      </Can>,
    );
    expect(screen.getByText('Ask an approver')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Post invoice' })).not.toBeInTheDocument();
  });

  it('accepts a wildcard grant for a gated control', () => {
    withPermissions(
      ['invoice.*'],
      <Can permission="invoice.post" fallback={<p>hidden</p>}>
        <button type="button">Post invoice</button>
      </Can>,
    );
    expect(screen.getByRole('button', { name: 'Post invoice' })).toBeInTheDocument();
    expect(screen.queryByText('hidden')).not.toBeInTheDocument();
  });

  it('renders nothing with no provider at all', () => {
    const { container } = render(
      <Can permission="invoice.write">
        <button type="button">Post invoice</button>
      </Can>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
