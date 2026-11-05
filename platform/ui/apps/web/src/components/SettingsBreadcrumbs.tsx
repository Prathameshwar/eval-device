import { BackNavigation } from './BackNavigation';

export function SettingsBreadcrumbs(_props: { title: string }) {
  return <BackNavigation href="/settings" label="Back to settings" />;
}
