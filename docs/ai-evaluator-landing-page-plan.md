# AI Evaluator public landing page plan

Recorded: 2026-10-08.
Status: the user authorized the layout stage and subsequently all remaining local
implementation phases, followed by review and fixes. Assets, content, contact,
policy pages and metadata are complete. Publication and hosted deployment are separate.

## Agreed scope

- Product: AI Evaluator. Character: Alex, explicitly a fictional simulated patient.
- Public homepage with its own CSS, styles, layout, header, navigation and footer.
- Seven content sections, two main images, ten content icons, one existing logo
  design displayed in the header and footer. Small UI control symbols are additional.
- Static informational content with minimal navigation and FAQ interaction.
- Login opens the existing authentication page; My Account opens the console for
  signed-in users. The public homepage remains accessible to both.
- Aim for clear messaging, restrained imagery, professional typography and strong
  desktop/mobile presentation. PCS.ai is a reference, not a source of copied assets.
- Preserve existing authentication, console behavior, permissions and unrelated work.

## Complete page plan

Header: existing AI Evaluator identity; Platform, Meet Alex, How It Works, FAQ,
Contact anchor links; Login/My Account action. Accessible mobile navigation.

| Section | Proposed heading | Contents |
| --- | --- | --- |
| Hero | Bring clinical learning to life. | Brief product introduction, Explore the Platform and Contact Us actions, Alex/interface composition. |
| Capabilities | Your simulation workflow, in one place. | Patient Scenarios, Training Sessions, Session Records, Teams & Devices; four icons. |
| Meet Alex | Meet Alex, your simulated patient. | Fictional patient character, authored symptoms/history/background/starting vitals; second image. |
| Workflow | Prepare. Simulate. Review. | Three numbered steps and icons; explain web management and companion roles accurately. |
| Audience | Designed for the people behind clinical training. | Clinical Educators, Simulation Teams, Institution Administrators; three icons. |
| FAQ | Before you get started. | Five short answers about purpose, Alex, scenario authoring, web/desktop use and accounts. |
| Contact | Explore AI Evaluator for your institution. | Approved contact destination and secondary account access. |

Proposed hero copy: "Prepare patient scenarios, coordinate simulation sessions,
and keep training records organized with AI Evaluator."

Footer: existing logo and product sentence; exploration links; approved contact
details; Privacy Policy, Terms of Use and copyright. Include only working links.

## Assets and content direction

- Main image 1: Alex with an actual platform preview using fictional sample data.
- Main image 2: the same Alex in a restrained clinical simulation setting.
- Define consistent character appearance before generating variants; compose real
  UI separately so generated artwork does not invent product controls/features.
- Optimize desktop/mobile variants; these remain versions of two main images.
- Icons: four capabilities, three workflow steps, three audiences; one SVG family.
- Reuse existing mark, wordmark and favicon; no logo redesign planned.
- Review copy against actual implemented behavior. Do not claim automated assessment,
  clinical outcomes or hardware acceptance without supporting evidence.
- Use the approved contact@aieval.com, AI Evaluator Company and
  https://eval.centralindia.cloudapp.azure.com/ identity. Local privacy and terms
  pages provide product-specific information. Do not expose private tenant data in assets.

## CSS, style and layout plan

This is the current focus. Values below are initial design targets, to be tuned
through visual review rather than treated as immutable requirements.

### Isolation and structure

- Dedicated landing component, scoped CSS module and small landing components.
- Local `--landing-*` variables for colors, typography, spacing, radii and elevation.
- No unscoped element resets or changes to shared PMS theme tokens.
- Audit inherited root, body and shared UI styles; locally establish a predictable
  light landing appearance without changing the stored console theme preference.
- Reuse branding geometry; locally supply any theme values required by its existing
  CSS so the wordmark remains readable under all stored application themes.
- Plan seven semantic sections inside main, plus header/nav and footer, one h1 and
  six h2 headings. Card titles use h3; number steps with an ordered list.
- Public route change is a later implementation step: `/` renders the landing page
  instead of automatically redirecting; `/login` and `/home` keep their existing roles.

### Palette and typography

- Warm white main surface, pale lavender secondary surface, deep navy headings,
  muted slate body text, and the existing brand indigo/purple direction.
- Initial palette: canvas #FCFCFE, surface #FFFFFF, pale surface #F4F2FA,
  ink #17213B, body #4B556B, border #E3E5EE, action #5B3FD6.
- Verify actual contrast; tune colors rather than assuming these values pass.
- Reserve gradient for subtle hero decoration and contact panel; solid surfaces
  and readable text elsewhere.
- Start with the existing system/Segoe UI stack; no font download required.
- Fluid hero heading approximately 38-64px; section headings 28-40px; card titles
  20-22px; body 16-18px; supporting text 14-16px. Use rem/clamp for sizing.
- Body line-height 1.55-1.7; headline line-height 1.08-1.2; body measure 55-65ch.

### Container and spacing

- Centered content container approximately 1200px maximum; page bands span full width.
- Horizontal gutters: 20px mobile, 32px tablet, 48px desktop.
- Section padding approximately 56px mobile, 72px tablet, 96px desktop.
- Internal scale: 4, 8, 12, 16, 24, 32, 48, 64 and 96px (implemented with rem).
- Grid gaps: 16px mobile and 24-32px desktop. No fixed text/card heights.
- Avoid forcing hero to fill the screen; size it to content, wrapping and its visual.

### Header and section composition

- Header approximately 72-80px desktop, 64-72px mobile, with room for text scaling.
- White/light sticky surface and subtle divider; blur is optional enhancement.
- Collapse navigation when available width requires it, initially near 1024px.
- Hero: desktop split approximately 48/52 with restrained gradient behind image.
  Mobile: headline, introduction, actions, visual; avoid tiny floating UI text.
- Capabilities: 4 columns desktop, 2 tablet, 1 narrow mobile; subtle bordered cards.
- Meet Alex: 2-column image/text layout; stack naturally on mobile. Reserve image
  aspect ratio and document safe crop areas for later assets.
- Workflow: 3 horizontal steps desktop, vertical ordered list mobile; connectors
  decorative and never necessary to understand the sequence.
- Audience: 3 equal columns desktop, 1 mobile; lightly tinted surface for rhythm.
- FAQ: approximately 800px readable content width, dividers and generous answer spacing.
- Contact: broad rounded navy/indigo panel with restrained glow, text plus actions;
  stack on mobile. Clear text and control contrast.
- Footer: 3 groups desktop, stacked mobile; light background and top divider.

### Components, responsive behavior and motion

- Buttons: solid primary, outlined secondary, quiet text link; minimum 44px
  control target, 48px default button height; clear hover, focus and active states.
- Initial radius targets: controls 10px, cards 16px, major visual/contact panel 24px.
- One subtle card shadow and one slightly stronger image shadow; avoid universal elevation.
- Icons: consistent approximately 24px glyphs in restrained 40-48px containers.
- Interactive elements get interaction styling; static cards should not imply clicks.
- Header/menu keyboard behavior, Escape dismissal and focus management are part of
  implementation; collapsed navigation should not remain keyboard-focusable.
- Native details/summary is the preferred minimal FAQ approach, subject to visual review.
- Default breakpoints approximately 640, 768 and 1024px, adjusted to content needs.
- Validate 360, 390, 768, 1024 and 1440px; also inspect 320px and text zoom/reflow.
- Motion limited to approximately 150-200ms control transitions; no required entrance
  animations or hidden-until-scroll content. Respect reduced-motion preferences.
- Visible focus, skip link, correct landmarks/headings and forced-colors fallbacks.
- Sticky header must not obscure focused controls or section anchors.

## Execution and verification stages

1. Create layout/style specification and reusable landing primitives.
2. Build section scaffolding with honest reserved visual regions; finalize responsive
   spacing and typography before adding final artwork/copy.
3. Integrate approved assets, copy and real link destinations in later requested stages.
4. Implement public routing and account navigation; review existing login redirects.
5. Optimize images, reserve dimensions and minimize client JavaScript.
6. Set accurate public metadata/social preview. Current app defaults to noindex;
   decide public indexing explicitly without exposing private routes to indexing.
7. Run frontend typecheck/build and relevant tests; meaningful regressions for routing
   and navigation; browser checks for mobile menu, FAQ, anchors and account links.
8. Review screenshots across widths, application theme preferences, keyboard use,
   reduced motion, contrast, overflow, loading/layout shift and browser console.
9. Fix confirmed issues, repeat affected checks, and inspect final result again.

Deliver locally reviewable page, assets, screenshot evidence and actual check results.
Maintain repository TODO/review records if implementation is substantial. Publishing,
hosted deployment, cloud/hardware validation and additional backend scope are separate.

## Current completed work

- Saved the agreed overall plan and the proposed CSS/style/layout specification.
- Inspected existing page routing, root style imports, brand components and tokens.
- Implemented the public root page, scoped landing CSS, responsive header, seven
  sections, existing brand/icons and footer. Existing login/console routes are preserved.
- Replaced the initial CSS illustrations with two consistent generated Alex visuals,
  including an actual fictional-data platform capture in the hero composition.
- Added responsive optimized WebP variants, approved contact/operator identity,
  working privacy and terms pages, canonical metadata and a local social preview.
- Retained noindex by default; documented an explicit public indexing setting.
- Completed review and narrow-screen overflow fixes. Verification and remaining stages
  are recorded in `pms-api-reviews.md` and `pms-api-todo.md`.
