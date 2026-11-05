import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DepartmentEditor } from '../src/components/DepartmentEditor';
import { DEMO_DEPARTMENTS } from '../src/data/departments';
import { saveDepartmentDraft, departmentDraft, validateDepartmentDraft } from '../src/lib/department-editor';

const department = DEMO_DEPARTMENTS[0]!;
const valid = () => ({
  ...departmentDraft(null),
  name: 'Emergency Ward',
  description: 'Urgent treatment unit.'
});

describe('department editor data', () => {
  it('requires a nonblank name on creation', () => {
    expect(validateDepartmentDraft({ ...valid(), name: '   ' }))
      .toEqual({ name: 'Enter a department name.' });
  });

  it.each([['name', 80], ['description', 4000], ['status_reason', 4000]] as const)(
    'honors the API length boundary for %s', (field, max) => {
      expect(validateDepartmentDraft({ ...valid(), [field]: 'x'.repeat(max) })[field]).toBeUndefined();
      expect(validateDepartmentDraft({ ...valid(), [field]: 'x'.repeat(max + 1) })[field]).toBeDefined();
    },
  );

  it('creates records, trims fields and keeps management values consistent', () => {
    const saved = saveDepartmentDraft({
      ...valid(),
      name: '  Emergency Ward  ',
      description: '  Urgent treatment.  ',
      is_active: true,
    }, null, 'new-id', 'timestamp');
    
    expect(saved).toMatchObject({
      id: 'new-id',
      name: 'Emergency Ward',
      description: 'Urgent treatment.',
      is_active: true,
      created_at: 'timestamp',
      updated_at: 'timestamp',
      management_version: 1,
    });
  });

  it('preserves IDs and original creation date when editing', () => {
    const draft = { ...departmentDraft(department), name: 'Renamed Dept' };
    expect(validateDepartmentDraft(draft)).toEqual({});
    expect(saveDepartmentDraft(draft, department, 'ignored', 'later')).toMatchObject({
      id: department.id,
      name: 'Renamed Dept',
      created_at: department.created_at,
      updated_at: 'later',
      management_version: department.management_version + 1,
    });
  });
});

describe('department editor controls', () => {
  it('does not show errors while an untouched form mounts', async () => {
    const user = userEvent.setup();
    render(<StrictMode><DepartmentEditor department={null} onSave={vi.fn()} onClose={() => {}} /></StrictMode>);
    expect(screen.getByRole('textbox', { name: 'Department name' })).toHaveFocus();
    await user.tab();
    expect(screen.queryByText('Enter a department name.')).not.toBeInTheDocument();
  });

  it('shows required errors, and clears errors as corrected', async () => {
    const user = userEvent.setup();
    const save = vi.fn();
    render(<DepartmentEditor department={null} onSave={save} onClose={() => {}} />);
    
    await user.click(screen.getByRole('button', { name: 'Create department' }));
    expect(screen.getByText('Enter a department name.')).toBeInTheDocument();
    
    await user.type(screen.getByRole('textbox', { name: 'Department name' }), 'Nephrology Ward');
    expect(screen.queryByText('Enter a department name.')).not.toBeInTheDocument();
  });

  it('protects a dirty draft on Escape, keeps editing, and discards only after confirmation', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(<DepartmentEditor department={null} onSave={vi.fn()} onClose={close} />);
    
    await user.type(screen.getByRole('textbox', { name: 'Department name' }), 'Draft Dept');
    await user.keyboard('{Escape}');
    
    const confirmation = screen.getByRole('dialog', { name: 'Discard unsaved changes?' });
    expect(within(confirmation).getByRole('button', { name: 'Keep editing' })).toHaveFocus();
    
    await user.click(within(confirmation).getByRole('button', { name: 'Keep editing' }));
    expect(screen.getByRole('textbox', { name: 'Department name' })).toHaveValue('Draft Dept');
    
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(close).toHaveBeenCalledTimes(1);
  });

  it('does not warn or save an unchanged edit, and allows Cancel immediately', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    const save = vi.fn();
    render(<DepartmentEditor department={department} onSave={save} onClose={close} />);
    
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    fireEvent.submit(screen.getByRole('textbox', { name: 'Department name' }).closest('form')!);
    expect(save).not.toHaveBeenCalled();
    
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(close).toHaveBeenCalledOnce();
  });
});
