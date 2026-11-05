# Platform UI

An npm workspace with two members:

- **`packages/ui`** — the reusable `@pms/ui` React package: `AppShell`, navigation, controls, tables, filters, overlays, charts, theme support, formatters, and presentation utilities. It still has no application routes, authentication flows, API proxies, dashboard data, or catalog screens, and it stays that way — those belong to a consumer.
- **`apps/web`** — `@pms/web`, the AI Evaluator Next.js application. It provides API-backed local account authentication and a permission-aware console with preview business data. See [its README](apps/web/README.md) for what it does and does not do.

The split is the point: product branding, routes and the auth split-screen live in the app, so a second consumer of the design system inherits neither this product's logo nor its sign-in layout.

## Install and verify

From `platform/ui`:

```sh
#cd C:\Pratham\poc-device\platform\ui
npm ci
npm run typecheck   # both workspaces
npm test            # both workspaces
npm run build       # production build of apps/web
npm run dev         # apps/web on http://localhost:3000
```

The workspace lockfile fixes development dependency versions. Generated dependencies, coverage, framework builds, `next-env.d.ts`, and TypeScript caches are ignored.

## Use in a consuming application

The package exports TypeScript source, so the consuming application's bundler must compile TS/TSX and CSS from `@pms/ui`. It supports React 18 and 19. Import the styles once at the application entry point:

```tsx
import { Button, ThemeProvider } from '@pms/ui';
import '@pms/ui/styles.css';

export function Screen() {
  return (
    <ThemeProvider>
      <div className="pms-root">
        <Button>Continue</Button>
      </div>
    </ThemeProvider>
  );
}
```

The stylesheet entry includes tokens, all three palettes, and component styles in order. Individual stylesheets are also exported under `@pms/ui/styles/*`. CSS classes and variables, theme preferences, and column-preference storage now use the `pms-` / `pms.` namespace. Fonts default to system fonts; a consuming app may override the font tokens and load its own fonts.

Supply application branding through component slots. Supply display preferences with `DisplayConfigProvider`; the inherited defaults use INR, Indian digit grouping, and Asia/Kolkata. Permission helpers only control presentation. Authentication, authorization, record scope, and API-specific query limits belong to the consuming application and its server. Search/selection controls accept caller-supplied loaders; the library has no built-in PMS or external-service client.

## Shared control contracts

List pages use `FilterBar` with stacked `Select` labels (omit `inline`). The filter
container owns 44px controls at the default font size, 12px gaps, bounded field
widths and full-width stacking in narrow containers, including dialogs. Use
`TableSearch` for existing debounced searches; an immediate `TextField` search can
use a `pms-table-search` wrapper to share the sizing without changing its query
behavior. Keep explicit Apply/Clear actions inside the filter bar and preserve
their form semantics. These dimensions are scoped to filter controls; ordinary
forms, pagination and applied-filter chips keep their own styling.

- `Button` defaults to `type="button"`. Use `type="submit"` for form submission and `type="reset"` for a native form reset.
- `TextField` and `Select` merge caller-provided `aria-describedby` with the messages they actually render. An error keeps `aria-invalid` true, and a loading select keeps `aria-busy` true.
- A named loading `Select` preserves an existing selected value during submission, including when attached to an external form with `form="form-id"`. An explicitly disabled control submits nothing.
- Dialogs keep focus inside the available controls, fall back to a focusable panel, and share scroll locking across overlapping dialogs. Menus and search lists consume Escape for their own open state before the containing dialog handles it.
- Footer and rail links use the same URL allowlist as rows and table cells. Unsafe destinations render as text. This is URL-scheme validation; it does not authorize access to a destination.
- Every tab panel needs a unique `panelId`. Use that same value when labelling its content:

```tsx
<Tabs tabs={tabs} active={active} onChange={setActive} label="Sections" panelId="sections-panel" />
<section
  id="sections-panel"
  role="tabpanel"
  aria-labelledby={tabButtonId(active, 'sections-panel')}
  tabIndex={0}
>
  {content}
</section>
```

Repeated tab ids in separate groups are supported. Tabs without a panel receive generated instance ids. Consumers of the imported copy must update panel labels from `tabButtonId(active)` to `tabButtonId(active, panelId)`.

## Removed from the imported copy

- The authentication and business-console apps, including the duplicate `apps/apps/console` tree. `apps/web` is a new AI Evaluator application written against the package's public exports, not a restoration of either.
- Customer, product/catalog, audit, and dashboard screens, their API/session adapters, previews, app tests, and app dependencies.
- JANSO logo/wordmark components and assets.
- Catalog-specific `AttributeValueInput`, `CustomFields`, `CustomFieldEditor`, custom-field rules, and field-set-to-column adapters.
- Generated coverage, Next.js output, copied dependencies, and TypeScript build caches.
- Automatic Google Fonts loading and obsolete source-project documentation references.

Reusable components keep their existing behavioral tests. The import was renamed from `@janso/ui` to `@pms/ui`; consumers copied from the original project must update their imports and CSS/storage prefixes. `apps/web` is the first application in this repository to consume the package.

### Bulk member imports

Tenant administrators can open **Members > Import members** for the Access > Workbook > Review > Results wizard. It supports one role and optional department per Excel batch, validates before creating invitations, shows partial outcomes, and downloads reusable failed rows or full results. Saved batches survive refresh and are listed for 30 days. See [API and deployment contract](../api/deploy/member-imports.md).

## Content, configuration and history screens

The web console includes tenant **Scenarios** for patient stories, Case QnA, instructor guidance and independent publication review, plus **Practice** for private selection of a published scenario. Historical clinical catalogs remain available at their existing URLs. It also includes platform model configuration, processing profile revisions, API-backed departments, session/feedback/reporting and scoped recordings. Tenant personal settings use `/me`. The guided scenario editor reuses `@pms/ui` workflow steps and responsive CSS modules. See [management routes and deployment requirements](../../docs/web-content-management.md).
