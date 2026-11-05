import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import DownloadsPage from '../src/app/(console)/downloads/page';
import { downloadSession } from '../src/lib/downloads';
import { apiRequest, ApiError } from '../src/lib/api';

vi.mock('../src/lib/downloads', () => ({ downloadSession: vi.fn() }));
vi.mock('../src/lib/api', () => ({ apiRequest: vi.fn(),
  ApiError: class extends Error { constructor(public status: number, message: string) { super(message); } } }));
vi.mock('next/navigation', () => ({ redirect: (path: string) => { throw new Error('redirect:' + path); } }));
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(downloadSession).mockResolvedValue({ token: 'fixture' } as never);
  vi.mocked(apiRequest).mockResolvedValue({ items: ['cuda', 'runtime'].map((edition) => ({ id: 'desktop-' + edition,
    filename: 'Human-test-windows-x64-' + edition + '-protected-fixture.zip', size_bytes: 1048576,
    sha256: 'a'.repeat(64) })) });
});

it('offers both editions with checksums and correct portable onboarding instructions', async () => {
  render(await DownloadsPage());
  expect(screen.getByRole('heading', { name: 'Downloads', level: 1 })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'GPU portable with models' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'App & runtime without models' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'CPU edition' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Download Desktop App' })).toHaveAttribute('href', '/api/downloads?artifact=desktop-cuda&sha256=' + 'a'.repeat(64));
  expect(screen.getByRole('link', { name: 'Download without models' })).toHaveAttribute('href', '/api/downloads?artifact=desktop-runtime&sha256=' + 'a'.repeat(64));
  expect(screen.getByText('Human-test.exe')).toBeInTheDocument();
  expect(screen.getByText('Desktop-App-GPU.zip')).toBeInTheDocument();
  expect(screen.getByText('Desktop-App.zip')).toBeInTheDocument();
  expect(screen.getByText(/with Qwen 3.5 4B, Whisper large-v3 and Piper English\/Hindi voices/)).toBeInTheDocument();
  expect(screen.getByText(/without model weights or voices/)).toBeInTheDocument();
  expect(screen.getByText(/Keep your models, saved connection and history folders/)).toBeInTheDocument();
  expect(screen.getByText(/Match the device's assigned models/)).toBeInTheDocument();
  expect(apiRequest).toHaveBeenCalledWith('/downloads', { token: 'fixture' });
});

it('redirects non-admins before fetching release metadata', async () => {
  vi.mocked(downloadSession).mockRejectedValue(new ApiError(403, 'denied'));
  await expect(DownloadsPage()).rejects.toThrow('redirect:/home');
  expect(apiRequest).not.toHaveBeenCalled();
});

it('requires login before fetching release metadata', async () => {
  vi.mocked(downloadSession).mockRejectedValue(new ApiError(401, 'missing'));
  await expect(DownloadsPage()).rejects.toThrow('redirect:/login');
  expect(apiRequest).not.toHaveBeenCalled();
});

it('handles an empty catalog and an unavailable server without a broken link', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ items: [] });
  const first = render(await DownloadsPage());
  expect(screen.getByRole('status')).toHaveTextContent('being prepared');
  expect(screen.queryByRole('link', { name: 'Download Desktop App' })).not.toBeInTheDocument();
  first.unmount();
  vi.mocked(apiRequest).mockRejectedValue(new ApiError(503, 'unavailable'));
  render(await DownloadsPage());
  expect(screen.getByRole('status')).toHaveTextContent('temporarily unavailable');
});
