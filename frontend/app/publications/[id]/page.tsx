import { PublicationDetail } from "@/components/publication-detail";

export default async function PublicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PublicationDetail id={id} />;
}
