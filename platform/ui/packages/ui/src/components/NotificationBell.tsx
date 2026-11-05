'use client';

import { IconButton } from './IconButton';
import { BellIcon } from './icons-console';

/**
 * The top bar's bell. The count lives in the accessible name because the dot is a colour
 * on a shape — "status is never colour alone" — and a screen reader
 * user would otherwise never learn there is anything to read.
 */
export function NotificationBell({
  count,
  onOpen,
}: {
  count: number;
  onOpen?: () => void;
}) {
  const unread = count > 0;

  return (
    <IconButton
      label={unread ? `Notifications, ${count} unread` : 'Notifications'}
      icon={<BellIcon />}
      badged={unread}
      onClick={onOpen}
      className="pms-bell"
    />
  );
}
