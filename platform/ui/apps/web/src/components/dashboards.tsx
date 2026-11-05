import { ActivityIcon, BarChart, Card, CardBody, CardHeader, ClockIcon, CustomersIcon, ListRow, PageHeader, TrendUpIcon } from '@pms/ui';
import { StatCards } from './StatCards';
import { DeviceIcon, LicenseIcon, PulseIcon, SessionIcon, TenantIcon } from './icons-product';
import type { SessionUser } from '@/lib/session-user';
import type { HomeData } from '@/lib/home';
import { settingsFor } from '@/lib/settings';
import { DestinationCards } from './DestinationCards';

export function TenantClinicalHome({ user }: { user: SessionUser }) {
  const sections = settingsFor('org_admin', permission => user.permissions.includes(permission))
    .filter(section => section.id === 'scenarios');
  return <div className="pms-page">
    <PageHeader overline={user.tenant?.name ?? 'Tenant'} title={`Good to see you, ${user.name}`}
      lede="Create and review clinical scenarios for desktop practice and device training." />
    <DestinationCards sections={sections} label="Clinical content" />
  </div>;
}

export function Dashboard({ user, data }: { user: SessionUser; data: HomeData }) {
  if (user.role === 'org_admin') return <TenantClinicalHome user={user} />;
  const platform = user.contextId === 'platform';
  return (
    <div className="pms-page">
      <PageHeader overline={platform ? 'Platform' : user.tenant?.name ?? 'Training'} title={`Good to see you, ${user.name}`}
        lede={platform ? 'Current fleet and tenant activity across this deployment.' : 'Your practice sessions and recorded feedback.'} />
      <StatCards cards={data.cards} icons={{ devices: DeviceIcon, live: PulseIcon, tenants: TenantIcon, licences: TenantIcon, members: CustomersIcon, licence: LicenseIcon, sessions: SessionIcon, hours: ActivityIcon, score: TrendUpIcon, reviews: ClockIcon }} />
      <div className="pms-grid pms-grid--split">
        {platform && <Card>
          <CardHeader icon={<TenantIcon size={18} />} title="Devices by tenant" subtitle="Top ten tenants by current device count" />
          <CardBody>{data.tenants?.length ? <BarChart data={data.tenants} ariaLabel="Current devices by tenant" series={1} height={220} /> : <p>No tenants yet.</p>}</CardBody>
        </Card>}
        <Card>
          <CardHeader icon={<ActivityIcon size={18} />} title={platform ? 'Recent activity' : 'My recent sessions'} subtitle={platform ? 'Administrative audit, newest first' : 'Retained sessions, newest first'} />
          <CardBody><div className="pms-console__rows">
            {data.activity.length ? data.activity.map(row => <ListRow key={row.id} icon={<ActivityIcon size={16} />} primary={row.primary} meta={row.meta} figure={row.figure} tone={row.tone} />) : <p>{platform ? 'No recent activity.' : 'No sessions in this scope yet.'}</p>}
          </div></CardBody>
        </Card>
        {data.health && <Card><CardHeader icon={<DeviceIcon size={18} />} title="Device health" /><CardBody>
          {data.health.map(row => <ListRow key={row.id} primary={row.label} meta={row.meta} share={row.share} tone={row.tone} />)}
        </CardBody></Card>}
      </div>
    </div>
  );
}
