import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PublicationDetail } from "./publication-detail";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      publication: vi.fn(),
      similarPublications: vi.fn(),
      summarizePublication: vi.fn(),
      extractPublicationKeywords: vi.fn(),
      publicationCitation: vi.fn(),
    },
  };
});

const publication = {
  id: "publication-1",
  external_id: null,
  title: "Gender inequality and economic empowerment",
  abstract: "An abstract.",
  authors: [],
  keywords: [],
  subjects: [],
  affiliations: [],
  publication_year: 2024,
  publication_date: null,
  language: "en",
  doi: null,
  article_url: null,
  pdf_url: null,
  source: "wolkite-etd",
  source_type: "oai_pmh",
  quality_score: null,
  publisher: null,
  is_deleted: false,
  updated_at: "2026-07-16T00:00:00Z",
};

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PublicationDetail id="publication-1" />
    </QueryClientProvider>,
  );
}

describe("Publication research intelligence", () => {
  beforeEach(() => {
    vi.mocked(api.publication).mockResolvedValue(publication);
    vi.mocked(api.similarPublications).mockResolvedValue({
      publication_id: "publication-1",
      model: "all-MiniLM-L6-v2",
      count: 0,
      results: [],
      status: "ready",
      message: null,
      minimum_similarity: 0.35,
    });
  });

  it("labels an indexed chunk summary as full text", async () => {
    vi.mocked(api.summarizePublication).mockResolvedValue({
      id: "summary-1",
      publication_id: "publication-1",
      summary_type: "structured",
      summary_text: "Study overview\nGrounded evidence [p. 4]",
      summary: "Study overview\nGrounded evidence [p. 4]",
      model_name: "page-aware-extractive-v2",
      source_fields: ["document_chunks"],
      confidence_score: "0.9",
      is_verified: false,
      generated_at: "2026-07-16T00:00:00Z",
      status: "ready",
      summary_source: "full_text",
      summary_style: "structured",
      research_document_id: "document-1",
      document_status: "indexed",
      pages_used: [4],
      chunk_count: 8,
      provider: "local",
      cached: false,
      warnings: [],
      processing_job_id: null,
      message: null,
    });
    renderDetail();
    fireEvent.click(
      await screen.findByRole("button", { name: "Generate summary" }),
    );
    expect(await screen.findByText("Full-text summary")).toBeInTheDocument();
    expect(screen.getByText(/Evidence pages: 4/)).toBeInTheDocument();
  });

  it("shows a recoverable missing-embedding state", async () => {
    vi.mocked(api.similarPublications).mockResolvedValue({
      publication_id: "publication-1",
      model: "all-MiniLM-L6-v2",
      count: 0,
      results: [],
      status: "embedding_required",
      message:
        "A semantic representation is being generated for this publication.",
      minimum_similarity: 0.35,
    });
    renderDetail();
    await waitFor(() =>
      expect(
        screen.getByText(/semantic representation is being generated/i),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Check again" }),
    ).toBeInTheDocument();
  });
});
