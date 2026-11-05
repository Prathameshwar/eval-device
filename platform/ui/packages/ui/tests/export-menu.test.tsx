/**
 * `ExportMenu` — asking the server for the list as it is currently queried.
 *
 * Two properties matter more than the markup. It is gated on **its own** permission key: reading a
 * list on screen and taking the whole list away are different capabilities, so `invoice.read` must
 * not draw it. And it never produces a file — a browser-built export would cover one page of a
 * keyset walk and would be assembled from data that passed field policy for *display*, while a
 * read-denied field has to stay denied in exports and reports too.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { EXPORT_FORMATS, ExportMenu } from '../src/components/ExportMenu';
import { PermissionProvider } from '../src/lib/permissions';

function mount(permissions: readonly string[], props: Partial<Parameters<typeof ExportMenu>[0]> = {}) {
  const onExport = vi.fn();
  render(
    <PermissionProvider permissions={permissions}>
      <ExportMenu permission="invoice.export" onExport={onExport} {...props} />
    </PermissionProvider>,
  );
  return { onExport, trigger: screen.queryByRole('button', { name: /Export/ }) };
}

describe('ExportMenu permission gating', () => {
  it('is absent without the key — not a greyed control advertising a capability', () => {
    const { trigger } = mount([]);

    expect(trigger).toBeNull();
  });

  it('is absent for a reader who may only read the list', () => {
    // The load-bearing case: `invoice.read` does not carry `invoice.export`.
    const { trigger } = mount(['invoice.read']);

    expect(trigger).toBeNull();
  });

  it('is drawn for the export key', () => {
    const { trigger } = mount(['invoice.export']);

    expect(trigger).toBeInTheDocument();
  });

  it('is drawn for a wildcard grant over the resource', () => {
    const { trigger } = mount(['invoice.*']);

    expect(trigger).toBeInTheDocument();
  });

  it('takes the key the screen names, not a key of its own', () => {
    render(
      <PermissionProvider permissions={['audit_event.export']}>
        <ExportMenu permission="audit_event.export" onExport={vi.fn()} />
      </PermissionProvider>,
    );

    expect(screen.getByRole('button', { name: /Export/ })).toBeInTheDocument();
  });
});

describe('ExportMenu formats', () => {
  it('offers the standard two, named as a reader would recognise them', async () => {
    const user = userEvent.setup();
    const { trigger } = mount(['invoice.export']);

    await user.click(trigger as HTMLElement);

    expect(screen.getAllByRole('menuitem').map((item) => item.textContent)).toEqual(['CSV', 'Excel']);
    expect(EXPORT_FORMATS.map((format) => format.id)).toEqual(['csv', 'xlsx']);
  });

  it('reports the format id, and nothing else happens here', async () => {
    const user = userEvent.setup();
    const { trigger, onExport } = mount(['invoice.export']);
    await user.click(trigger as HTMLElement);

    await user.click(screen.getByRole('menuitem', { name: 'Excel' }));

    // The id is what the screen puts in the request. No file, no blob, no object URL: the server
    // runs the job, applies field policy, audits it and returns a signed expiring URL.
    expect(onExport).toHaveBeenCalledWith('xlsx');
    expect(document.querySelector('a[download]')).toBeNull();
  });

  it('closes after the request is made — it is a verb, not a set of toggles', async () => {
    const user = userEvent.setup();
    const { trigger } = mount(['invoice.export']);
    await user.click(trigger as HTMLElement);

    await user.click(screen.getByRole('menuitem', { name: 'CSV' }));

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('takes a narrower format list when a resource supports one', async () => {
    const user = userEvent.setup();
    const { trigger, onExport } = mount(['invoice.export'], {
      formats: [{ id: 'pdf', label: 'PDF' }],
    });
    await user.click(trigger as HTMLElement);

    expect(screen.getAllByRole('menuitem')).toHaveLength(1);
    await user.click(screen.getByRole('menuitem', { name: 'PDF' }));
    expect(onExport).toHaveBeenCalledWith('pdf');
  });
});

describe('ExportMenu when an export cannot be started', () => {
  it('says why, on every format, and refuses the request', async () => {
    const user = userEvent.setup();
    const { trigger, onExport } = mount(['invoice.export'], {
      disabledReason: 'An export is already running',
    });
    await user.click(trigger as HTMLElement);

    const csv = screen.getByRole('menuitem', { name: /CSV/ });
    expect(csv).toHaveTextContent('An export is already running');
    expect(csv).toHaveAttribute('aria-disabled', 'true');

    await user.click(csv);
    expect(onExport).not.toHaveBeenCalled();
    // Still open, so the reason stays readable rather than vanishing with the panel.
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  it('takes its own wording when a screen names it differently', () => {
    render(
      <PermissionProvider permissions={['invoice.export']}>
        <ExportMenu permission="invoice.export" onExport={vi.fn()} label="Download" />
      </PermissionProvider>,
    );

    expect(screen.getByRole('button', { name: /Download/ })).toBeInTheDocument();
  });
});
