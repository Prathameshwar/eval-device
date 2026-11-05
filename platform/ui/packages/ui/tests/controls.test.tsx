/**
 * Badge and Disclosure. `Select` grew its own file, `select.test.tsx` —
 * it now carries hint, error, disabled and loading states, and each one is a branch.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { Badge } from '../src/components/Badge';
import { Disclosure } from '../src/components/Disclosure';

describe('Badge', () => {
  it('defaults to a neutral tint', () => {
    render(<Badge>4 overdue</Badge>);
    const badge = screen.getByText('4 overdue');
    expect(badge).toHaveClass('pms-badge');
    expect(badge).toHaveClass('pms-badge--tint');
    expect(badge).toHaveAttribute('data-tone', 'neutral');
  });

  it.each(['tint', 'outline', 'mono'] as const)('renders the %s variant', (variant) => {
    render(<Badge variant={variant}>INR</Badge>);
    expect(screen.getByText('INR')).toHaveClass(`pms-badge--${variant}`);
  });

  it.each(['neutral', 'brand', 'success', 'warn', 'danger', 'info'] as const)(
    'carries data-tone="%s" so the triplet resolves in CSS',
    (tone) => {
      render(<Badge tone={tone}>Status</Badge>);
      expect(screen.getByText('Status')).toHaveAttribute('data-tone', tone);
    },
  );
});

describe('Disclosure', () => {
  it('is closed by default', () => {
    const { container } = render(
      <Disclosure summary="Assumptions">Excludes cancelled invoices.</Disclosure>,
    );
    expect(container.querySelector<HTMLDetailsElement>('details')?.open).toBe(false);
  });

  it('honours defaultOpen', () => {
    const { container } = render(
      <Disclosure summary="Assumptions" defaultOpen>
        Excludes cancelled invoices.
      </Disclosure>,
    );
    expect(container.querySelector<HTMLDetailsElement>('details')?.open).toBe(true);
    expect(screen.getByText('Excludes cancelled invoices.')).toBeInTheDocument();
  });

  it('toggles open and closed from the summary', async () => {
    const { container } = render(
      <Disclosure summary="Assumptions">Excludes cancelled invoices.</Disclosure>,
    );
    const details = container.querySelector<HTMLDetailsElement>('details');

    await userEvent.click(screen.getByText('Assumptions'));
    expect(details?.open).toBe(true);

    await userEvent.click(screen.getByText('Assumptions'));
    expect(details?.open).toBe(false);
  });

  it('renders a caret that the CSS rotates, hidden from assistive tech', () => {
    const { container } = render(<Disclosure summary="Assumptions">Body</Disclosure>);
    const caret = container.querySelector('.pms-disclosure__caret');
    expect(caret).toHaveAttribute('aria-hidden', 'true');
    expect(caret?.querySelector('svg')).not.toBeNull();
  });
});
