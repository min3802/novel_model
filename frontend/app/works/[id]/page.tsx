import { WorkDetailFeaturePage } from "@/features/works/WorkDetailPage";

export default function Page({ params }: { params: { id: string } }) {
  return <WorkDetailFeaturePage params={params} />;
}
