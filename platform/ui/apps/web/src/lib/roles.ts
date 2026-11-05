/**
 * Roles, and the one place "tenant" is translated to "organization".
 *
 * The schema calls it an organization (`organizations`, `organization_memberships`,
 * `org_admin`, every `org.*` permission). The product calls it a tenant. Renaming the schema to
 * match the label would be the wrong fix — so the mapping lives here, the UI reads the labels
 * from here, and nothing else in the app spells either word.
 *
 * The permission keys below mirror the current API role catalogue. The frozen database baseline
 * view is historical; current role-derived clinical author access is resolved by the API. This
 * lets the navigation be gated by the same
 * strings the server will enforce. Presentation only: `PermissionProvider` decides what is
 * *drawn*, and the server decides what is *allowed* — the package says so in its own comments.
 */

export const ROLE_CODES = ['platform_admin', 'org_admin', 'org_user'] as const;

export type RoleCode = (typeof ROLE_CODES)[number];

/** What each role is called on screen. `org_*` becomes "Tenant *" for the product's vocabulary. */
export const ROLE_LABELS: Record<RoleCode, string> = {
  platform_admin: 'Platform Admin',
  org_admin: 'Tenant Admin',
  org_user: 'Tenant User',
};

/** True for the roles scoped to one tenant — they get a tenant chip and a switcher; the platform admin does not. */
export function isTenantScoped(role: RoleCode): boolean {
  return role !== 'platform_admin';
}

/**
 * Exactly the current API role grants for these three roles. Three roles in the
 * catalogue are not modelled here yet — `org_read_only`, `org_trainee` and the `org_device`
 * machine principal — because no screen distinguishes them; adding one means adding its row.
 */
export const ROLE_PERMISSIONS: Record<RoleCode, readonly string[]> = {
  platform_admin: [
    'platform.settings.read',
    'platform.settings.manage',
    'platform.organizations.read',
    'platform.organizations.manage',
    'platform.organization_admins.manage',
    'platform.users.read',
    'platform.users.manage',
    'platform.administrators.manage',
    'platform.audit.read',
    'platform.health.read',
  ],
  org_admin: [
    'org.devices.summary.read',
    'org.devices.read',
    'org.status.read',
    'org.configuration.read',
    'org.results.read',
    'org.media.read',
    'org.telemetry.read',
    'org.activity.read',
    'org.settings.read',
    'org.settings.manage',
    'org.members.manage',
    'org.departments.manage',
    'org.devices.manage',
    'org.processing.execute',
    'org.playback.execute',
    'org.audit.read',
    'org.clinical.author',
  ],
  org_user: [
    'org.devices.summary.read',
    'org.devices.read',
    'org.status.read',
    'org.configuration.read',
    'org.results.read',
    'org.media.read',
    'org.telemetry.read',
    'org.activity.read',
    'org.processing.execute',
    'org.playback.execute',
  ],
};
