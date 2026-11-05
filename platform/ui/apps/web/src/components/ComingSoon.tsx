import type { ReactNode } from 'react';
import {
  AuditIcon,
  Badge,
  CustomersIcon,
  EmptyState,
  PageHeader,
  ReportsIcon,
  RolesIcon,
  SettingsIcon,
} from '@pms/ui';
import { ActivityIcon } from '@pms/ui';
import {
  DeviceIcon,
  LicenseIcon,
  ModelIcon,
  SessionIcon,
  TenantIcon,
} from '@/components/icons-product';

/**
 * The destinations the rail offers that are not built yet.
 *
 * They exist so no menu item 404s while the screens behind them are pending — a dead link in a
 * navigation is indistinguishable from a broken build. Each one states plainly what it will be
 * and that it holds nothing, rather than showing an empty table that looks like a query that
 * returned nothing.
 *
 * One catalogue rather than twelve hand-written pages: the route files are four lines each and
 * the copy lives together, where it can be read as a set.
 */

type Pending = {
  title: string;
  overline: string;
  body: string;
  icon: ReactNode;
};

export const PENDING_PAGES = {
  tenants: {
    title: 'Tenants',
    overline: 'Platform',
    body: 'Organisations on this deployment, their administrators, subscriptions and enrolment limits.',
    icon: <TenantIcon size={28} />,
  },
  devices: {
    title: 'Devices',
    overline: 'Manage',
    body: 'Enrolled devices, their credentials, heartbeat, configuration profile and telemetry.',
    icon: <DeviceIcon size={28} />,
  },
  models: {
    title: 'Models',
    overline: 'Manage',
    body: 'Create and manage local and cloud models for devices.',
    icon: <ModelIcon size={28} />,
  },
  users: {
    title: 'Administrators',
    overline: 'Platform',
    body: 'Platform identities and the administrators who hold them, with their audit trail.',
    icon: <RolesIcon size={28} />,
  },
  licenses: {
    title: 'Licenses',
    overline: 'Platform',
    body: 'Subscription periods, device allowances and renewals for every tenant.',
    icon: <LicenseIcon size={28} />,
  },
  logs: {
    title: 'Logs',
    overline: 'Activity',
    body: 'The audit record: who changed what, when, and from which device or address.',
    icon: <AuditIcon size={28} />,
  },
  settings: {
    title: 'Settings',
    overline: 'Configuration',
    body: 'Your profile, notification preferences, and — where your role allows it — the settings for your scope.',
    icon: <SettingsIcon size={28} />,
  },
  members: {
    title: 'Members',
    overline: 'Manage',
    body: 'People in your tenant, their roles, department scope and pending invitations.',
    icon: <CustomersIcon size={28} />,
  },
  departments: {
    title: 'Departments',
    overline: 'Manage',
    body: 'Departments within your tenant and the members and devices scoped to each.',
    icon: <TenantIcon size={28} />,
  },
  sessions: {
    title: 'Sessions',
    overline: 'Activity',
    body: 'Practice interviews, their transcripts turn by turn, and how each was scored.',
    icon: <SessionIcon size={28} />,
  },
  reports: {
    title: 'Reports',
    overline: 'Activity',
    body: 'Scores over time by cohort, scenario and department, with exports.',
    icon: <ReportsIcon size={28} />,
  },
  recordings: {
    title: 'Recordings',
    overline: 'Training',
    body: 'Audio and video from your sessions, kept private to you and your reviewers.',
    icon: <ActivityIcon size={28} />,
  },
} as const satisfies Record<string, Pending>;

export type PendingPageId = keyof typeof PENDING_PAGES;

export function ComingSoon({ id, breadcrumbs }: { id: PendingPageId; breadcrumbs?: ReactNode }) {
  const page = PENDING_PAGES[id];

  return (
    <div className="pms-page">
      {breadcrumbs}
      <PageHeader
        overline={page.overline}
        title={page.title}
        lede={page.body}
        actions={
          <Badge tone="neutral" variant="outline">
            Not built yet
          </Badge>
        }
      />
      <EmptyState
        icon={page.icon}
        title="This screen is next, not missing"
        body="The navigation, roles and dashboards were built first so the shape of the console could be agreed. This page will list real records once the API is connected."
      />
    </div>
  );
}
