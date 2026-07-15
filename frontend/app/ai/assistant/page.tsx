import type { Metadata } from "next";
import { ResearchAssistant } from "@/components/research-assistant";

export const metadata: Metadata = {
  title: "AI Research Assistant | ResearchHub Ethiopia",
  description: "Ask grounded questions about Ethiopian university research.",
};

export default async function ResearchAssistantPage({
  searchParams,
}: {
  searchParams: Promise<{
    documentId?: string;
    publicationId?: string;
    publication?: string;
    repository?: string;
    university?: string;
  }>;
}) {
  const params = await searchParams;
  return (
    <ResearchAssistant
      initialScope={{
        documentId: params.documentId,
        publicationId: params.publicationId || params.publication,
        repository: params.repository,
        university: params.university,
      }}
    />
  );
}
