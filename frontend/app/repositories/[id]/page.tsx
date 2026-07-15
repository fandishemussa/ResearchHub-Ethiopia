import { SourceDetails } from "@/components/source-details";
export default async function SourceDetailsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <SourceDetails id={(await params).id} />;
}
