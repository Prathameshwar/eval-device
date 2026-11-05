import { CatalogDirectory } from '@/components/CatalogDirectory';
import { requireCatalog } from '@/lib/catalog-access';
export default async function Page() {
  const user = await requireCatalog();
  return <CatalogDirectory key={user.contextId} kind="cases" canManage={user.permissions.includes('org.clinical.author')} />;
}
