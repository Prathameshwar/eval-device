import 'server-only';
import { apiRequest } from './api';

export type SetupStatus = { required: boolean; available: boolean };

export async function setupStatus(timeoutMs?: number): Promise<SetupStatus | null> {
  try { return await apiRequest<SetupStatus>('/auth/setup', { timeoutMs }); }
  catch { return null; }
}
