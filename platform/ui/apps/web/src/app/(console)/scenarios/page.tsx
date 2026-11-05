import { requireScenario } from '@/lib/catalog-access';
import { ScenarioLibrary } from '@/components/ScenarioLibrary';
export default async function Page({ searchParams }: { searchParams: Promise<{ source_case_id?: string }> }) {
  const user = await requireScenario();
  const query = await searchParams;
  return <ScenarioLibrary key={user.contextId} contextId={user.contextId!}
    canAuthor={user.permissions.includes('org.clinical.author')}
    canReview={user.permissions.includes('org.clinical.review')}
    sourceCaseId={query.source_case_id} />;
}
