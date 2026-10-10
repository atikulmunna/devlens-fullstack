import { LegacyRepoRedirect } from "@/components/legacy-repo-redirect";

export default function LegacyDiffPage({ params }: { params: { repoId: string } }) {
  return <LegacyRepoRedirect repoId={params.repoId} tab="changes" />;
}
