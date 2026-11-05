import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BrandLockup, BrandMark, Wordmark } from '../src/components/BrandMark';

describe('brand identity', () => {
  it('states the product name once, as text', () => {
    const { container } = render(<BrandLockup />);

    /* The tile is decoration beside real text: one accessible name for the lockup, not two. */
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(container.querySelector('.pms-brand__tile')).toHaveAttribute('aria-hidden', 'true');
    expect(container).toHaveTextContent('AI Evaluator');
  });

  it('keeps the product name selectable and translatable rather than drawing it', () => {
    const { container } = render(<Wordmark />);

    expect(container.querySelector('svg')).toBeNull();
    expect(container.querySelector('.pms-brand__ai')).toHaveTextContent('AI');
    expect(container).toHaveTextContent('AI Evaluator');
  });

  it('scales the glyph with the tile', () => {
    const { container } = render(<BrandMark size={64} />);

    const tile = container.querySelector('.pms-brand__tile') as HTMLElement;
    expect(tile.style.width).toBe('64px');
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '40');
    expect(svg).toHaveAttribute('height', '40');
  });

  /* The favicon cannot read a custom property, so it repeats the glyph as literals. If the two
   * ever diverge, the tab shows a different logo from the page — which nobody notices for weeks. */
  it('draws the same geometry as the favicon', async () => {
    const { readFileSync } = await import('node:fs');
    const { join } = await import('node:path');
    const icon = readFileSync(join(__dirname, '..', 'src', 'app', 'icon.svg'), 'utf8');
    const { container } = render(<BrandMark />);

    for (const path of container.querySelectorAll('path')) {
      expect(icon).toContain(path.getAttribute('d'));
    }
  });
});
