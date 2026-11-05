import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { HistoryWorkspace } from '../src/components/HistoryWorkspace';
import * as actions from '../src/lib/history-actions';

vi.mock('../src/lib/history-actions', () => ({ listHistory: vi.fn(), readHistory: vi.fn(), sessionRubric: vi.fn() }));
beforeEach(() => { vi.resetAllMocks(); });

it.each([
  ['authorized', 'other', true, false],
  ['authorized', 'viewer', false, false],
  ['authorized', 'viewer', true, true],
  ['completed', 'other', true, false],
  ['completed', 'viewer', true, true],
] as const)('gates controls for %s session owned by %s with instructor access %s', async (status, instructor_id, canManage, allowed) => {
  const row = { id: 'session', device_id: 'device', instructor_id, status, created_at: '2026-10-04T10:00:00Z' };
  vi.mocked(actions.listHistory).mockResolvedValue({ value: { items: [row], total: 1, has_more: false, next_cursor: null } });
  vi.mocked(actions.readHistory).mockResolvedValue({ value: row });
  vi.mocked(actions.sessionRubric).mockResolvedValue({ value: { items: [{ id: 'item', description: 'Assessment' }] } });
  render(<HistoryWorkspace contextId="tenant" viewerId="viewer" mode="sessions" canManage={canManage} canMedia={false} />);
  await userEvent.setup().click(await screen.findByRole('button', { name: 'View details' }));
  await waitFor(() => expect(actions.readHistory).toHaveBeenCalled());
  if (status === 'authorized') {
    expect(!!screen.queryByRole('button', { name: 'Stop session' })).toBe(allowed);
  } else if (allowed) {
    expect(await screen.findByRole('button', { name: 'Save feedback' })).toBeInTheDocument();
  } else {
    expect(actions.sessionRubric).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Save feedback' })).not.toBeInTheDocument();
  }
});
