/**
 * StatTile / StatRow.
 *
 * The load-bearing case is the missing value: "no data" and "zero" are different facts in
 * accounting, and a tile that renders `0` for an absent figure is a reporting bug that reads
 * as a correct answer. That branch is asserted from both directions.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatRow, StatTile } from '../src/components/StatTile';
import { WalletIcon } from '../src/components/icons-console';

describe('StatTile', () => {
  it('renders the label and the pre-formatted string figure', () => {
    const { container } = render(<StatTile label="Invoiced" value="₹ 12,45,000.0000" />);
    expect(screen.getByText('Invoiced')).toBeInTheDocument();
    const figure = container.querySelector('.pms-stat__value');
    expect(figure).toHaveTextContent('₹ 12,45,000.0000');
    // Figures are tabular everywhere — a column of numbers that shifts is unreadable.
    expect(figure).toHaveClass('pms-figure');
  });

  it('defaults to the default tone, top-level size and no emphasis', () => {
    const { container } = render(<StatTile label="Invoiced" value="10" />);
    const tile = container.querySelector('.pms-stat');
    expect(tile).toHaveAttribute('data-tone', 'default');
    expect(tile).not.toHaveClass('pms-stat--nested');
    expect(tile).not.toHaveClass('pms-stat--emphasis');
  });

  it.each(['default', 'brand', 'success', 'warn', 'danger'] as const)(
    'colours the figure via data-tone="%s"',
    (tone) => {
      const { container } = render(<StatTile label="Margin" value="18.4%" tone={tone} />);
      expect(container.querySelector('.pms-stat')).toHaveAttribute('data-tone', tone);
    },
  );

  it.each(['default', 'brand', 'success', 'warn', 'danger'] as const)(
    'tints the whole tile for tone="%s" when emphasized',
    (tone) => {
      const { container } = render(
        <StatTile label="Margin" value="18.4%" tone={tone} emphasis />,
      );
      const tile = container.querySelector('.pms-stat');
      expect(tile).toHaveClass('pms-stat--emphasis');
      expect(tile).toHaveAttribute('data-tone', tone);
    },
  );

  it('renders the nested variant for a tile inside a card', () => {
    const { container } = render(<StatTile label="Paid" value="4" nested />);
    expect(container.querySelector('.pms-stat')).toHaveClass('pms-stat--nested');
  });

  it('renders the icon and footnote when given', () => {
    const { container } = render(
      <StatTile label="Collected" value="₹ 8,000" icon={<WalletIcon />} footnote="vs ₹ 6,100" />,
    );
    expect(container.querySelector('.pms-stat__icon svg')).not.toBeNull();
    expect(screen.getByText('vs ₹ 6,100')).toHaveClass('pms-stat__footnote');
  });

  it('omits the icon and footnote when not given', () => {
    const { container } = render(<StatTile label="Collected" value="₹ 8,000" />);
    expect(container.querySelector('.pms-stat__icon')).toBeNull();
    expect(container.querySelector('.pms-stat__footnote')).toBeNull();
  });

  it('renders an em-dash — never 0 — for a null value', () => {
    const { container } = render(<StatTile label="Write-offs" value={null} />);
    const figure = container.querySelector('.pms-stat__value');
    expect(figure).toHaveTextContent('—');
    expect(figure?.textContent).not.toContain('0');
    expect(screen.queryByText('0')).toBeNull();
  });

  it('renders the em-dash for an undefined value', () => {
    const { container } = render(<StatTile label="Write-offs" value={undefined} />);
    expect(container.querySelector('.pms-stat__value')).toHaveTextContent('—');
  });

  it('treats a blank string as no data, not as an empty figure', () => {
    const { container } = render(<StatTile label="Write-offs" value="   " />);
    expect(container.querySelector('.pms-stat__value')).toHaveTextContent('—');
  });

  it('gives the em-dash a text equivalent so it is not announced as punctuation', () => {
    render(<StatTile label="Write-offs" value={null} />);
    const equivalent = screen.getByText('No value');
    expect(equivalent).toHaveClass('pms-visually-hidden');
    expect(equivalent.previousElementSibling).toHaveAttribute('aria-hidden', 'true');
  });

  it('renders a real zero as a figure, not as the em-dash', () => {
    const { container } = render(<StatTile label="Write-offs" value="0.0000" />);
    const figure = container.querySelector('.pms-stat__value');
    expect(figure).toHaveTextContent('0.0000');
    expect(figure?.textContent).not.toContain('—');
    expect(screen.queryByText('No value')).toBeNull();
  });
});

describe('StatRow', () => {
  it('is 4-up by default', () => {
    const { container } = render(
      <StatRow>
        <StatTile label="A" value="1" />
      </StatRow>,
    );
    expect(container.querySelector('.pms-stat-row')).toHaveAttribute('data-columns', '4');
  });

  it('takes 3 columns when asked', () => {
    const { container } = render(
      <StatRow columns={3}>
        <StatTile label="A" value="1" />
      </StatRow>,
    );
    expect(container.querySelector('.pms-stat-row')).toHaveAttribute('data-columns', '3');
  });

  it('renders each child tile', () => {
    render(
      <StatRow>
        <StatTile label="Invoiced" value="1" />
        <StatTile label="Collected" value="2" />
        <StatTile label="Overdue" value="3" />
        <StatTile label="Written off" value={null} />
      </StatRow>,
    );
    expect(screen.getAllByText(/Invoiced|Collected|Overdue|Written off/)).toHaveLength(4);
  });
});
