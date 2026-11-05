# AI Evaluator landing page completion and release

Owner-supplied public details, 2026-10-08:

- Product: AI Evaluator; fictional patient: Alex, 35-year-old male schoolteacher.
- Operator: AI Evaluator Company.
- Contact: contact@aieval.com.
- Public origin: https://eval.centralindia.cloudapp.azure.com/.

## Public configuration

The owner-supplied identity is the default in `public-site.ts`. A deployment may
override the documented `PMS_PUBLIC_*` values in the web environment. These values
are intentionally public; they must never contain credentials, private media URLs,
tokens, or signed links. Contact uses mailto and creates no server-side form/outbox.
Public website and external policy URLs require HTTPS without credentials or query
strings. Empty identity overrides hide the corresponding optional public details.

`/privacy` explains actual product data handling and deployment responsibilities.
`/terms` provides educational-use guidelines. These do not invent a jurisdiction,
universal retention period, processing legal basis, pricing, or service contract.
An operator can supply approved external policy destinations using the environment.
Deployment-specific privacy information should identify actual hosting/provider
arrangements and applicable rights. The ICO privacy-information checklist was used
as a completeness reference, not as a claim that a particular jurisdiction applies:
https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/the-right-to-be-informed/what-privacy-information-should-we-provide/

The homepage and legal pages retain noindex unless public indexing is explicitly
enabled with a public origin. Private application routes retain the existing root
noindex defaults. The canonical URL uses the public origin, and the social image is
generated locally from existing brand geometry through Next ImageResponse.

## Images

Two main Alex assets are complete. Hero character photography is composed with a
real UI capture containing only fictional sample data. Meet Alex uses the first
portrait as its identity reference. Responsive exports are variants, not additional
main images. Prompts are recorded beside this document in `landing-page-assets/`.

The user approved imagegen CLI/API fallback because built-in generation is unavailable.
Both images were created with the bundled skill CLI, gpt-image-2 at high quality.
The owner-provided local key was scoped to each process and never printed or copied
into source. A task-local certificate bundle uses the Windows trust store;
TLS verification remained enabled. The second scene references the first portrait.

Final public assets are in `platform/ui/apps/web/public/landing/`:

| Asset | Dimensions | Bytes |
| --- | --- | --- |
| alex-hero.webp | 1280 x 1200 | 77,528 |
| alex-hero-small.webp | 768 x 720 | 27,108 |
| alex-clinical.webp | 1200 x 800 | 52,804 |
| alex-clinical-small.webp | 768 x 512 | 23,316 |

Responsive srcSet/sizes select local WebP variants. Width/height reserve layout space;
the hero has high fetch priority and the clinical image loads lazily. UI capture
uses the actual scenario component with entirely fictional sample data and read-only
mocked endpoints. Generated originals and capture/export evidence remain in ignored
`output/imagegen/` and `.test_artifacts/landing-final-20261008/` respectively.

## Verification and release

- 91 distinct relevant frontend tests passed; all 23 new public-page tests passed
  again after the final review fixes. Workspace typecheck and production build passed.
- Browser checks verified contact/policy destinations, canonical/social metadata,
  image loading, 320-1440px layouts, saved themes, 200% text, keyboard navigation,
  reduced motion and account-service error handling. Initial measured CLS was 0.
- Reviewed every section, final imagery, both documents, social preview and forced
  colors. Removed obsolete illustration CSS and corrected inherited metadataBase.
- Actual results are in `pms-api-reviews.md`; phase status is in `pms-api-todo.md`.
- The subsequently authorized hosted deployment and actual HTTPS/browser results
  are recorded below. Live model integrations and hardware remain unverified.
- Use the repository publishing helper if GitHub publication is requested; preserve
  other work and remote contents. The owner subsequently authorized publication
  of the complete landing-page source, assets, tests and documentation.

## Render review follow-up

Self-inspection found overflow when narrow screens used 200% root text sizing.
Header navigation now adapts to enlarged text, grid children can shrink and wrap,
and buttons/contact links stay within their containers. The measured header height
bounds the menu and offsets anchor/focus scrolling. Mobile headline sizing was tuned
to avoid awkward word breaks. Platform and review copy now use clearer, shorter wording.

The read-only regression can be run against a local web build using
`node platform/ui/apps/web/tests/browser-landing-reflow.mjs`. Set
`PMS_TEST_WEB_ORIGIN` and `PMS_TEST_BROWSER` if the defaults need changing. It checks
the homepage and both public documents at six widths, normal/enlarged text,
expanded menus, landscape layout and FAQ keyboard/focus behavior. No login,
database fixture or provider call is required.

## Hosted deployment - 2026-10-08

The owner authorized updating the existing VM. The landing page is now live at
https://eval.centralindia.cloudapp.azure.com/. Managed release
20261008-081101-222638 retains 20261007-144101-199603 as the previous release.
The normal Ubuntu deployment workflow rebuilt the UI and completed successfully.
A private consistent PostgreSQL backup was retained with a validated restore
catalog; the schema revision did not change and no destructive upgrade flags were used.

The 17 reviewed public-web files match the deployed source/assets. Existing API,
shared code, configuration, six checked data tables and downloads catalog remained
unchanged. All five services are active; public pages and API/web readiness pass
over valid HTTPS. Login remains at /login and anonymous /home access redirects there.

Hosted browser checks passed for content, images, metadata, policy links, mobile
navigation and keyboard FAQ, without mocked endpoints. All 36 public-route reflow
combinations and short-landscape checks passed. Desktop/mobile screenshots were
inspected, with no failed assets or JavaScript page errors. Evidence and detailed
limits are recorded in pms-api-reviews.md. Authenticated learner sessions, live
model-provider integrations and device hardware were not exercised in this release.
