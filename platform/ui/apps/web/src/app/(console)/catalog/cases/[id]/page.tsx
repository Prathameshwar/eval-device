import { CatalogEditor } from '@/components/CatalogEditor';
import { requireCatalog } from '@/lib/catalog-access';
import { notFound } from 'next/navigation';
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireCatalog();
  const { id } = await params;
  if (id === 'new' && !user.permissions.includes('org.clinical.author')) notFound();
  return (
    <CatalogEditor
      key={user.contextId + id}
      kind="cases"
      id={id}
      canManage={user.permissions.includes('org.clinical.author')}
    />
  );
}
