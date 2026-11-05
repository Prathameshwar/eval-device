'use client';

import { useCan } from '../lib/permissions';
import { Menu, type MenuItem } from './Menu';
import { DownloadIcon } from './icons-console';

export type ExportFormat = {
  /** Passed back to `onExport` — the format the request asks the server for. */
  id: string;
  label: string;
};

export const EXPORT_FORMATS: readonly ExportFormat[] = [
  { id: 'csv', label: 'CSV' },
  { id: 'xlsx', label: 'Excel' },
];

export type ExportMenuProps = {
  /**
   * The permission this export requires, and it is **its own key** — `invoice.export`, never
   * `invoice.read`. Reading a list on screen and taking the whole list away are different
   * capabilities: one is bounded by a page and an audit trail, the other leaves the building. The
   * server enforces the same key; this only decides whether the control is drawn.
   */
  permission: string;
  /**
   * Asks the screen to *request* an export of the query in force. It must call the API — see this
   * component's docblock for why nothing here builds a file.
   */
  onExport: (format: string) => void;
  formats?: readonly ExportFormat[];
  /** Why an export cannot be started right now — "the list is empty", "an export is running". */
  disabledReason?: string;
  label?: string;
};

/**
 * Requests an export of the list as it is currently queried.
 *
 * **It never produces a file.** Not a convenience decision — an export built in the browser from
 * the rows in hand would be wrong twice over. It would cover one page of a keyset walk, which has no
 * total and no way to name the rest. And it would be assembled from
 * data that passed field policy for *display*, while a read-denied field must stay denied in exports
 * and reports too — only the server can hold that
 * line. So the component reports the request and the format; the screen calls the endpoint, which
 * runs the job, applies field policy, audits it and hands back a signed, expiring URL (§5.14).
 *
 * Absent, not disabled, without the permission: a greyed "Export" tells someone a capability exists
 * that they are not going to get.
 */
export function ExportMenu({
  permission,
  onExport,
  formats = EXPORT_FORMATS,
  disabledReason,
  label = 'Export',
}: ExportMenuProps) {
  const allowed = useCan(permission);
  if (!allowed) return null;

  const items: MenuItem[] = formats.map((format) => ({
    id: format.id,
    label: format.label,
    disabledReason,
  }));

  return (
    <Menu
      label={label}
      triggerLabel={label}
      icon={<DownloadIcon size={14} />}
      items={items}
      onSelect={onExport}
    />
  );
}
