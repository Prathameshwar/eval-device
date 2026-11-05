import Link from 'next/link';
import { ArrowRightIcon, Card } from '@pms/ui';
import type { SettingsDestination } from '@/lib/settings';

export function DestinationCards({ sections, label }: {
  sections: readonly SettingsDestination[];
  label: string;
}) {
  return <section className="pms-grid pms-console__settings-grid" aria-label={label}>
    {sections.map((section) => <Card key={section.id} className="pms-console__settings-card">
      <Link href={section.href} className="pms-console__settings-link"
        aria-labelledby={`destination-${section.id}-title`}
        aria-describedby={`destination-${section.id}-description`}>
        <span className="pms-console__settings-icon" aria-hidden="true"><section.icon size={24} /></span>
        <h2 className="pms-console__settings-title" id={`destination-${section.id}-title`}>{section.title}</h2>
        <p className="pms-console__settings-description" id={`destination-${section.id}-description`}>{section.description}</p>
        <span className="pms-console__settings-action">{section.action}<ArrowRightIcon size={18} /></span>
      </Link>
    </Card>)}
  </section>;
}
