import { HarvestJobDetails } from "@/components/harvest-job-details";
export default async function HarvestJobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <HarvestJobDetails id={(await params).id} />;
}
