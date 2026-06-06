import { NewEpisodeFeaturePage } from "@/features/episodes/NewEpisodePage";

export default function Page({ params }: { params: { id: string } }) {
  return <NewEpisodeFeaturePage params={params} />;
}
