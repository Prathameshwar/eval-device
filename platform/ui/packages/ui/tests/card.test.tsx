/**
 * The card family. The tone branches matter one by one: a card that is
 * meant to read as a warning and silently renders untinted is a status that isn't there.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Badge } from '../src/components/Badge';
import { Card, CardBody, CardFooter, CardHeader } from '../src/components/Card';
import { DocumentIcon } from '../src/components/icons-console';

describe('Card', () => {
  it('renders children on the default surface with no tone', () => {
    const { container } = render(<Card>Ledger</Card>);
    const card = container.querySelector('.pms-card');
    expect(card).not.toBeNull();
    expect(card).not.toHaveAttribute('data-tone');
    expect(card).not.toHaveClass('pms-card--nested');
    expect(screen.getByText('Ledger')).toBeInTheDocument();
  });

  it('marks a nested card so it takes the quieter surface', () => {
    const { container } = render(<Card nested>Nested</Card>);
    expect(container.querySelector('.pms-card')).toHaveClass('pms-card--nested');
  });

  it('merges a caller class without dropping the base class', () => {
    const { container } = render(<Card className="dash-card">Body</Card>);
    const card = container.querySelector('.pms-card');
    expect(card).toHaveClass('pms-card');
    expect(card).toHaveClass('dash-card');
  });

  it.each(['neutral', 'brand', 'success', 'warn', 'danger', 'info'] as const)(
    'carries data-tone="%s" so the triplet resolves in CSS',
    (tone) => {
      const { container } = render(<Card tone={tone}>Toned</Card>);
      expect(container.querySelector('.pms-card')).toHaveAttribute('data-tone', tone);
    },
  );
});

describe('CardHeader', () => {
  it('renders the title as an h3, below a section h2', () => {
    render(<CardHeader title="Outstanding" />);
    expect(screen.getByRole('heading', { level: 3, name: 'Outstanding' })).toBeInTheDocument();
  });

  it('omits the icon, subtitle and aside when none are given', () => {
    const { container } = render(<CardHeader title="Outstanding" />);
    expect(container.querySelector('.pms-card__icon')).toBeNull();
    expect(container.querySelector('.pms-card__subtitle')).toBeNull();
    expect(container.querySelector('.pms-card__aside')).toBeNull();
  });

  it('renders icon, subtitle, badge and action together', () => {
    const { container } = render(
      <CardHeader
        icon={<DocumentIcon />}
        title="Outstanding"
        subtitle="Across 12 customers"
        badge={<Badge tone="warn">4 overdue</Badge>}
        action={<button type="button">View all</button>}
      />,
    );
    expect(container.querySelector('.pms-card__icon svg')).not.toBeNull();
    expect(screen.getByText('Across 12 customers')).toHaveClass('pms-card__subtitle');
    expect(screen.getByText('4 overdue')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View all' })).toBeInTheDocument();
  });

  it('renders the aside for a badge alone', () => {
    const { container } = render(<CardHeader title="Outstanding" badge={<Badge>3</Badge>} />);
    expect(container.querySelector('.pms-card__aside')).not.toBeNull();
  });

  it('renders the aside for an action alone', () => {
    const { container } = render(
      <CardHeader title="Outstanding" action={<button type="button">Refresh</button>} />,
    );
    expect(container.querySelector('.pms-card__aside')).not.toBeNull();
  });
});

describe('CardBody and CardFooter', () => {
  it('renders body and footer content in the composed card', () => {
    const { container } = render(
      <Card>
        <CardHeader title="Invoices" />
        <CardBody>
          <p>Twelve open invoices.</p>
        </CardBody>
        <CardFooter>Updated a moment ago</CardFooter>
      </Card>,
    );
    expect(screen.getByText('Twelve open invoices.')).toBeInTheDocument();
    expect(screen.getByText('Updated a moment ago')).toBeInTheDocument();
    expect(container.querySelector('.pms-card__body')).not.toBeNull();
    expect(container.querySelector('.pms-card__footer')).not.toBeNull();
  });
});
