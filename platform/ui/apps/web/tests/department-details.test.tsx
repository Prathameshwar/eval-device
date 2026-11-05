import { PermissionProvider, ToastProvider } from '@pms/ui';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DepartmentDirectoryProvider } from '../src/components/DepartmentDirectoryProvider';
import { DepartmentDetails } from '../src/components/DepartmentDetails';
import { DEMO_DEPARTMENTS } from '../src/data/departments';
import type { Department } from '../src/lib/department-directory';

const sample = DEMO_DEPARTMENTS[0]!;
const manage = 'org.departments.manage';

function details(
  department: Department = sample,
  permissions = [manage],
  id = department.id
) {
  return render(
    <PermissionProvider permissions={permissions}>
      <ToastProvider>
        <DepartmentDirectoryProvider initialRows={[department]}>
          <DepartmentDetails departmentId={id} />
        </DepartmentDirectoryProvider>
      </ToastProvider>
    </PermissionProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe('department details', () => {
  it('shows the named department, cards, summary and full record ID', () => {
    details();
    expect(screen.getByRole('heading', { level: 1, name: sample.name })).toHaveFocus();
    for (const name of ['About this department', 'Record information']) {
      expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument();
    }
    expect(screen.getByText(sample.id)).toBeInTheDocument();
    expect(screen.getByText(sample.description!)).toBeInTheDocument();
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0);
    
    for (const link of screen.getAllByRole('link', { name: 'Back to departments' })) {
      expect(link).toHaveAttribute('href', '/departments');
    }
  });

  it('saves edits in place and retains the department identity', async () => {
    const user = userEvent.setup();
    details();
    await user.click(screen.getByRole('button', { name: 'Edit department' }));
    await user.clear(screen.getByRole('textbox', { name: 'Department name' }));
    await user.type(screen.getByRole('textbox', { name: 'Department name' }), 'Updated Cardiology');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Updated Cardiology');
    expect(screen.getByText('Department updated')).toBeInTheDocument();
  });

  it('requires confirmation for Archive and retains an archived view', async () => {
    const user = userEvent.setup();
    details();
    await user.click(screen.getByRole('button', { name: 'Department actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Archive' }));
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
    
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Edit department' })).toBeInTheDocument();
    
    await user.click(screen.getByRole('button', { name: 'Department actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Archive' }));
    await user.click(screen.getByRole('button', { name: 'Archive department' }));
    
    expect(screen.getByText('Archived department')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit department' })).not.toBeInTheDocument();
  });

  it('copies the full ID on Copy ID button click', async () => {
    const user = userEvent.setup();
    details();
    const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
    await user.click(screen.getByRole('button', { name: 'Copy ID' }));
    expect(copy).toHaveBeenCalledWith(sample.id);
    expect(screen.getByText('Department ID copied')).toBeInTheDocument();
  });

  it('explains a missing demo record with a way back to the list', () => {
    details(sample, [manage], 'not-found');
    expect(screen.getByRole('heading', { name: 'Department not available' })).toBeInTheDocument();
  });
});
