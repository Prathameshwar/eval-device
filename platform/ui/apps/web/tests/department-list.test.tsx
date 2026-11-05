import { PermissionProvider, ToastProvider } from '@pms/ui';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DepartmentDirectoryProvider } from '../src/components/DepartmentDirectoryProvider';
import { DepartmentList } from '../src/components/DepartmentList';
import { DEMO_DEPARTMENTS } from '../src/data/departments';
import type { Department } from '../src/lib/department-directory';

const manage = 'org.departments.manage';

function renderList(rows: readonly Department[] = DEMO_DEPARTMENTS, permissions = [manage]) {
  return render(
    <PermissionProvider permissions={permissions}>
      <ToastProvider>
        <DepartmentDirectoryProvider initialRows={rows}>
          <DepartmentList />
        </DepartmentDirectoryProvider>
      </ToastProvider>
    </PermissionProvider>
  );
}

const table = () => screen.getByRole('table', { name: 'Departments' });
const dataRows = () => within(table()).getAllByRole('row').slice(1);

afterEach(() => vi.restoreAllMocks());

describe('department list', () => {
  it('distinguishes an empty directory from filtered results', () => {
    renderList([]);
    expect(screen.getByText('No departments yet')).toBeInTheDocument();
    expect(screen.queryByText('No matching departments')).not.toBeInTheDocument();
  });

  it('pages forward/back and changes page size', async () => {
    const user = userEvent.setup();
    renderList();
    expect(dataRows()).toHaveLength(4); // DEMO_DEPARTMENTS has 5 items but 1 is archived by default, so active/inactive = 4
    expect(screen.getByRole('button', { name: 'Previous page of departments' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page of departments' })).toBeDisabled();
  });

  it('searches by query and resets filters', async () => {
    const user = userEvent.setup();
    renderList();
    const input = screen.getByRole('searchbox', { name: 'Search departments' });
    await user.type(input, 'Cardiology');
    await waitFor(() => expect(dataRows()).toHaveLength(1));
    expect(dataRows().every((row) => row.textContent?.includes('Cardiology'))).toBe(true);

    await user.clear(input);
    await user.type(input, 'NonexistentDept');
    await waitFor(() => expect(screen.getByText('No matching departments')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(input).toHaveValue('');
    expect(dataRows()).toHaveLength(4);
  });

  it('links View to the department detail route', () => {
    renderList([DEMO_DEPARTMENTS[0]!]);
    expect(screen.getByRole('link', { name: `View ${DEMO_DEPARTMENTS[0]!.name}` }))
      .toHaveAttribute('href', `/departments/${DEMO_DEPARTMENTS[0]!.id}`);
  });

  it('confirms archive and moves department to archived', async () => {
    const user = userEvent.setup();
    renderList([DEMO_DEPARTMENTS[0]!]);
    await user.click(screen.getByRole('button', { name: `Actions for ${DEMO_DEPARTMENTS[0]!.name}` }));
    await user.click(screen.getByRole('menuitem', { name: 'Archive' }));
    
    expect(screen.getByText(`Archive ${DEMO_DEPARTMENTS[0]!.name}?`)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Archive department' }));

    expect(await screen.findByText('Department archived')).toBeInTheDocument();
  });

  it('copies the department ID', async () => {
    const user = userEvent.setup();
    renderList([DEMO_DEPARTMENTS[0]!]);
    const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
    await user.click(screen.getByRole('button', { name: `Actions for ${DEMO_DEPARTMENTS[0]!.name}` }));
    await user.click(screen.getByRole('menuitem', { name: 'Copy ID' }));
    expect(clipboard).toHaveBeenCalledWith(DEMO_DEPARTMENTS[0]?.id);
    expect(await screen.findByText('Department ID copied')).toBeInTheDocument();
  });

  it('creates a department locally', async () => {
    const user = userEvent.setup();
    renderList([DEMO_DEPARTMENTS[0]!]);
    await user.click(screen.getByRole('button', { name: 'Create new department' }));
    await user.type(screen.getByRole('textbox', { name: 'Department name' }), 'Emergency');
    await user.click(screen.getByRole('button', { name: 'Create department' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByText('Department created')).toBeInTheDocument();
  });
});
