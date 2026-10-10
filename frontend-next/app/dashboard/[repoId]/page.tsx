import { LegacyRepoRedirect } from "@/components/legacy-repo-redirect";

export default function LegacyDashboardPage({ params }: { params: { repoId: string } }) {
  return <LegacyRepoRedirect repoId={params.repoId} tab="overview" />;
}
