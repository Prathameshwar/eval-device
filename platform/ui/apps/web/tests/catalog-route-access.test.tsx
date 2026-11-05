import { beforeEach, describe, expect, it, vi } from 'vitest';
import { notFound } from 'next/navigation';
import { requireCatalog } from '../src/lib/catalog-access';
import Categories from '../src/app/(console)/catalog/categories/[id]/page';
import Patients from '../src/app/(console)/catalog/patients/[id]/page';
import Cases from '../src/app/(console)/catalog/cases/[id]/page';

vi.mock('next/navigation', () => ({ notFound: vi.fn(() => { throw new Error('404'); }) }));
vi.mock('../src/lib/catalog-access', () => ({ requireCatalog: vi.fn() }));
vi.mock('../src/components/CatalogEditor', () => ({ CatalogEditor: () => null }));

describe('tenant clinical editor routes', () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([Categories, Patients, Cases])('denies direct new route to clinical readers', async (Page) => {
    vi.mocked(requireCatalog).mockResolvedValue({ contextId: 'tenant-a', permissions: ['org.clinical.read'] } as never);
    await expect(Page({ params: Promise.resolve({ id: 'new' }) })).rejects.toThrow('404');
    expect(notFound).toHaveBeenCalledOnce();
  });

  it.each([Categories, Patients, Cases])('allows clinical authors to open the new route', async (Page) => {
    vi.mocked(requireCatalog).mockResolvedValue({ contextId: 'tenant-a', permissions: ['org.clinical.author'] } as never);
    await expect(Page({ params: Promise.resolve({ id: 'new' }) })).resolves.toBeTruthy();
    expect(notFound).not.toHaveBeenCalled();
  });
});
