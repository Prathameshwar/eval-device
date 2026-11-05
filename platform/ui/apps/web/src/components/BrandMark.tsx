/**
 * The AI Evaluator identity: a mark, a wordmark, and the lockup of the two.
 *
 * Product branding lives in the application, not in `@pms/ui` — the package supplies branding
 * *slots* and nothing else, so a second consumer of the design system does not inherit this
 * product's logo.
 *
 * The tile is a `<span>` painted by CSS rather than an SVG `<linearGradient>`, deliberately:
 * the gradient is `--pms-grad-action`, which is redefined per palette, and an SVG gradient
 * would have to hard-code two hexes that then stay indigo-on-white in the dark theme. The
 * glyph inside is drawn in `currentColor` like every icon in the package.
 *
 * The glyph is a tick with a spark on its rising stroke: an evaluation that was made, and the
 * model that made it. `app/icon.svg` repeats the same geometry for the favicon.
 */

type MarkProps = {
  size?: number;
};

/**
 * Decorative, always: every place this app shows the mark, the wordmark is beside it, so the
 * product name is already text. Naming the tile as well would have a screen reader read
 * "AI Evaluator AI Evaluator". A future screen that shows the mark alone needs a name — and
 * should add that prop then, with a caller that proves it is needed.
 */
export function BrandMark({ size = 32 }: MarkProps) {
  return (
    <span className="pms-brand__tile" style={{ width: size, height: size }} aria-hidden="true">
      <svg
        className="pms-brand__glyph"
        width={Math.round(size * 0.62)}
        height={Math.round(size * 0.62)}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        {/* The tick rises *towards* the spark and stops short of it. An earlier version ran the
            stroke under the star, and at 20px the two merged into one blob with a spur. */}
        <path
          d="M3.4 14 8 18.6 13.8 9.8"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M17.8 2.6 19.05 4.75 21.2 6 19.05 7.25 17.8 9.4 16.55 7.25 14.4 6 16.55 4.75Z"
          fill="currentColor"
        />
      </svg>
    </span>
  );
}

/**
 * The product name as real text — selectable, translatable, and its own accessible name.
 * "AI" carries the brand gradient through `background-clip`, with a solid-colour fallback in
 * the stylesheet for engines that do not support it.
 */
export function Wordmark() {
  return (
    <span className="pms-brand__wordmark">
      <span className="pms-brand__ai">AI</span> Evaluator
    </span>
  );
}

/**
 * Mark and wordmark together.
 *
 * `lg` stacks them as a masthead — the auth panel, where the identity is the first thing on the
 * screen. `compact` lays them on one line at the size a 288px rail can hold, and collapses to the
 * mark alone at 72px (`console.css`). The variant exists because there are now two callers whose
 * proportions genuinely differ; it did not exist while there was one.
 */
export function BrandLockup({ size = 'lg' }: { size?: 'compact' | 'lg' }) {
  return (
    <span className={`pms-brand${size === 'compact' ? ' pms-brand--compact' : ''}`}>
      <BrandMark size={size === 'compact' ? 30 : 44} />
      <Wordmark />
    </span>
  );
}
