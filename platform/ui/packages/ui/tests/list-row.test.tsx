/**
 * ListRow and Meter. The meter's aria bounds and clamping are the
 * substance here: a progressbar whose `aria-valuenow` leaves its declared range, or a fill
 * that runs past its track, is a wrong number rendered confidently.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ListRow } from '../src/components/ListRow';
import { Meter } from '../src/components/Meter';
import { CheckCircleIcon, WarnTriangleIcon } from '../src/components/icons-console';

describe('Meter', () => {
  it('declares the 0–1 scale it is given, with the percentage as its value text', () => {
    render(<Meter value={0.42} label="Share of revenue" />);
    const bar = screen.getByRole('progressbar', { name: 'Share of revenue' });
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '1');
    expect(bar).toHaveAttribute('aria-valuenow', '0.42');
    expect(bar).toHaveAttribute('aria-valuetext', '42%');
  });

  it('shows the percentage as a trailing tabular label', () => {
    const { container } = render(<Meter value={0.42} />);
    const percent = container.querySelector('.pms-meter__percent');
    expect(percent).toHaveTextContent('42%');
    expect(percent).toHaveClass('pms-figure');
  });

  it('falls back to a generic accessible name rather than none', () => {
    render(<Meter value={0.1} />);
    expect(screen.getByRole('progressbar', { name: 'Share' })).toBeInTheDocument();
  });

  it('clamps above 1 instead of overflowing the track', () => {
    const { container } = render(<Meter value={1.6} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1');
    expect(container.querySelector<HTMLElement>('.pms-meter__fill')?.style.width).toBe('100%');
  });

  it('clamps below 0 instead of inverting the fill', () => {
    const { container } = render(<Meter value={-0.5} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
    expect(container.querySelector<HTMLElement>('.pms-meter__fill')?.style.width).toBe('0%');
  });

  it('treats NaN as empty rather than rendering an invalid width', () => {
    const { container } = render(<Meter value={Number.NaN} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
    expect(container.querySelector<HTMLElement>('.pms-meter__fill')?.style.width).toBe('0%');
  });

  it.each(['neutral', 'brand', 'success', 'warn', 'danger', 'info'] as const)(
    'carries data-tone="%s" for the fill colour',
    (tone) => {
      const { container } = render(<Meter value={0.5} tone={tone} />);
      expect(container.querySelector('.pms-meter')).toHaveAttribute('data-tone', tone);
    },
  );
});

describe('ListRow', () => {
  it('renders a ranked row with a tabular rank and a figure', () => {
    const { container } = render(<ListRow rank={1} primary="Acme Traders" figure="₹ 4,20,000" />);
    const rank = container.querySelector('.pms-list-row__rank');
    expect(rank).toHaveTextContent('1');
    expect(rank).toHaveClass('pms-figure');
    const figure = container.querySelector('.pms-list-row__figure');
    expect(figure).toHaveTextContent('₹ 4,20,000');
    expect(figure).toHaveClass('pms-figure');
  });

  it('renders rank 0 rather than treating it as absent', () => {
    const { container } = render(<ListRow rank={0} primary="Baseline" />);
    expect(container.querySelector('.pms-list-row__rank')).toHaveTextContent('0');
  });

  it('renders a status icon when there is no rank', () => {
    const { container } = render(
      <ListRow icon={<CheckCircleIcon />} tone="success" primary="Paid in full" />,
    );
    expect(container.querySelector('.pms-list-row__icon svg')).not.toBeNull();
    expect(container.querySelector('.pms-list-row__rank')).toBeNull();
    expect(container.querySelector('.pms-list-row')).toHaveAttribute('data-tone', 'success');
  });

  it('prefers the rank over an icon when both are given', () => {
    const { container } = render(<ListRow rank={3} icon={<CheckCircleIcon />} primary="Both" />);
    expect(container.querySelector('.pms-list-row__rank')).toHaveTextContent('3');
    expect(container.querySelector('.pms-list-row__icon')).toBeNull();
  });

  it('renders no lead slot with neither rank nor icon', () => {
    const { container } = render(<ListRow primary="Plain" />);
    expect(container.querySelector('.pms-list-row__rank')).toBeNull();
    expect(container.querySelector('.pms-list-row__icon')).toBeNull();
  });

  it('renders plain text when there is no href', () => {
    render(<ListRow primary="Acme Traders" />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Acme Traders')).toBeInTheDocument();
  });

  it('renders an in-app link without new-tab attributes', () => {
    render(<ListRow primary="Acme Traders" href="/customers/1" />);
    const link = screen.getByRole('link', { name: 'Acme Traders' });
    expect(link).toHaveAttribute('href', '/customers/1');
    expect(link).not.toHaveAttribute('target');
    expect(link).not.toHaveAttribute('rel');
  });

  it('marks an external link with an icon, a text equivalent and a safe rel', () => {
    render(<ListRow primary="Acme Traders" href="https://example.test" external />);
    const link = screen.getByRole('link', { name: /Acme Traders/ });
    expect(link).toHaveAttribute('target', '_blank');
    // `noopener` is not decoration: a new tab otherwise gets a handle on this window.
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link.querySelector('svg')).not.toBeNull();
    expect(link).toHaveTextContent('(opens in a new tab)');
  });

  it('ignores `external` when there is no href, since nothing opens', () => {
    render(<ListRow primary="Acme Traders" external />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.queryByText(/opens in a new tab/)).toBeNull();
  });

  it('renders the meta line when given and omits it otherwise', () => {
    const { container: withMeta } = render(<ListRow primary="Acme" meta="12 invoices · Mumbai" />);
    expect(withMeta.querySelector('.pms-meta')).toHaveTextContent('12 invoices · Mumbai');

    const { container: without } = render(<ListRow primary="Acme" />);
    expect(without.querySelector('.pms-meta')).toBeNull();
  });

  it('renders a share meter named after the row', () => {
    render(<ListRow primary="Acme Traders" share={0.31} />);
    expect(screen.getByRole('progressbar', { name: 'Share — Acme Traders' })).toHaveAttribute(
      'aria-valuenow',
      '0.31',
    );
  });

  it('falls back to a generic meter name when the primary is not text', () => {
    render(<ListRow primary={<strong>Acme</strong>} share={0.5} />);
    expect(screen.getByRole('progressbar', { name: 'Share' })).toBeInTheDocument();
  });

  it('renders a zero share rather than dropping the meter', () => {
    render(<ListRow primary="Acme" share={0} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  });

  it('renders no meter when no share is given', () => {
    render(<ListRow primary="Acme" />);
    expect(screen.queryByRole('progressbar')).toBeNull();
  });

  it('passes the row tone through to the meter', () => {
    const { container } = render(<ListRow primary="Acme" share={0.5} tone="warn" />);
    expect(container.querySelector('.pms-meter')).toHaveAttribute('data-tone', 'warn');
  });

  it('defaults to the neutral tone so a colour never contradicts the glyph', () => {
    // A caller passing a warning triangle with no tone got an indigo warning triangle.
    const { container } = render(<ListRow icon={<WarnTriangleIcon />} primary="Overdue" />);
    expect(container.querySelector('.pms-list-row')).toHaveAttribute('data-tone', 'neutral');
  });

  it.each([
    ['/customers/1'],
    ['https://example.test/x'],
    ['http://example.test/x'],
    ['#totals'],
    ['mailto:ap@example.test'],
  ])('links an allowed scheme: %s', (href) => {
    render(<ListRow primary="Acme Traders" href={href} />);
    expect(screen.getByRole('link', { name: 'Acme Traders' })).toHaveAttribute('href', href);
  });

  it.each([
    ['javascript:alert(1)'],
    ['JavaScript:alert(1)'],
    ['  javascript:alert(1)'],
    ['java\nscript:alert(1)'],
    ['data:text/html;base64,PHNjcmlwdD4='],
    ['vbscript:msgbox(1)'],
    ['file:///etc/passwd'],
  ])('renders plain text instead of an anchor for a hostile href: %s', (href) => {
    // `href` reaches this component from an API row, and `external` makes that an intended
    // use — so an unvetted scheme is a live script-execution path on click.
    render(<ListRow primary="Acme Traders" href={href} external />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Acme Traders')).toHaveClass('pms-list-row__primary');
    expect(screen.queryByText(/opens in a new tab/)).toBeNull();
  });
});
