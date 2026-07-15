import type { Metadata } from "next";
import { DocumentDetail } from "@/components/documents/DocumentDetail";

export const metadata: Metadata = { title: "Research document" };

export default async function DocumentPage({
  params,
  searchParams,
}: {
  params: Promise<{ documentId: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { documentId } = await params;
  const query = await searchParams;
  const page =
    query.page && Number.isFinite(Number(query.page))
      ? Number(query.page)
      : undefined;
  return <DocumentDetail id={documentId} initialPage={page} />;
}
