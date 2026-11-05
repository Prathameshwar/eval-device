import type { ComponentType } from 'react';
import { StatRow, StatTile } from '@pms/ui';
import type { StatCard } from '@/data/demo';

/**
 * The four-up band every dashboard leads with.
 *
 * One component rather than three copies: the roles differ in *which* four figures they lead
 * with, never in how a figure is presented. The icon for each card is passed in by id, because
 * an icon is a product decision and the data module should not import components.
 *
 * `StatRow` is already 4-up collapsing to 2-up at 1100px and 1-up at 680px, so there is no grid
 * to write here.
 */
export function StatCards({
  cards,
  icons,
}: {
  cards: readonly StatCard[];
  icons: Record<string, ComponentType<{ size?: number }>>;
}) {
  return (
    <StatRow columns={4}>
      {cards.map((card) => {
        const Icon = icons[card.id];
        return (
          <StatTile
            key={card.id}
            label={card.label}
            /* Already formatted, and a string: an em-dash and a "No value" text equivalent are
             * what the tile renders for missing data, which is not the same fact as zero. */
            value={card.value}
            footnote={card.footnote}
            icon={Icon ? <Icon size={16} /> : undefined}
            tone={card.tone}
            emphasis={card.emphasis}
          />
        );
      })}
    </StatRow>
  );
}
