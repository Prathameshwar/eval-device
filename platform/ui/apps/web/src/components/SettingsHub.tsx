import { BackNavigation } from './BackNavigation';
import Link from 'next/link';
import { EmptyState, PageHeader, SettingsIcon } from '@pms/ui';
import type { SettingsDestination } from '@/lib/settings';
import { DestinationCards } from './DestinationCards';

export function SettingsHub({
  sections,
  tenantScoped,
}: {
  sections: readonly SettingsDestination[];
  tenantScoped: boolean;
}) {
  const department = sections.find(section => section.id === 'departments');
  const cards = sections.filter(section => section.id !== 'departments');
  return (
    <div className="pms-page">
      <BackNavigation href="/home" label="Back to home" />
      <PageHeader
        overline={tenantScoped ? 'Tenant' : 'Platform'}
        title="Settings"
        lede={
          tenantScoped
            ? 'Manage departments and create and review clinical scenarios.'
            : 'Manage subscriptions, models, language options and platform access.'
        }
      />
      {sections.length ? (
        <>
          {cards.length > 0 && <DestinationCards sections={cards} label="Settings sections" />}
          {department && <nav className="pms-console__settings-secondary" aria-label="Tenant administration">
            <h2 className="pms-console__settings-title">Tenant administration</h2>
            <Link className="pms-link" href={department.href}>{department.title}</Link>
          </nav>}
        </>
      ) : (
        <EmptyState
          icon={<SettingsIcon size={28} />}
          title="No settings sections available"
          body="Your account doesn't have access to these settings sections."
        />
      )}
    </div>
  );
}
