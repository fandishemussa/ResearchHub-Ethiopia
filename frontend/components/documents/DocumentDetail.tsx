"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Clipboard,
  ExternalLink,
  MessageSquareText,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { DocumentTypeBadge, SourceBadge } from "@/components/chat/Badges";
import { Card, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { safeHttpUrl } from "@/lib/urls";

export function DocumentDetail({
  id,
  initialPage,
}: {
  id: string;
  initialPage?: number;
}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState<number | undefined>(initialPage);
  const [section, setSection] = useState("");
  const [contentType, setContentType] = useState("");
  const deferredSearch = useDeferredValue(search);
  const document = useQuery({
    queryKey: ["document", id],
    queryFn: ({ signal }) => api.researchDocument(id, signal),
  });
  const params = new URLSearchParams({ limit: "50" });
  if (deferredSearch) params.set("search", deferredSearch);
  if (page) params.set("page", String(page));
  if (section) params.set("section", section);
  if (contentType) params.set("content_type", contentType);
  const chunks = useQuery({
    queryKey: [
      "document-chunks",
      id,
      deferredSearch,
      page,
      section,
      contentType,
    ],
    queryFn: ({ signal }) => api.documentChunks(id, params, signal),
  });
  if (document.isPending) return <Skeleton className="h-[70vh]" />;
  if (document.isError)
    return (
      <Card className="p-8 text-center">
        <h1 className="font-serif text-2xl font-bold">Document unavailable</h1>
        <p className="mt-2 text-stone-500">
          The indexed document could not be loaded.
        </p>
      </Card>
    );
  const item = document.data;
  const original =
    safeHttpUrl(item.document_url) || safeHttpUrl(item.landing_url);
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap gap-2">
            <SourceBadge code={item.source} />
            <DocumentTypeBadge
              type={String(item.metadata.document_type || "research document")}
            />
            <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs capitalize dark:bg-stone-800">
              {item.extraction_status}
            </span>
          </div>
          <h1 className="mt-3 max-w-4xl font-serif text-3xl font-bold">
            {item.title || "Indexed research document"}
          </h1>
          <p className="mt-2 text-sm text-stone-500">
            {item.page_count ?? "Unknown"} pages ·{" "}
            {item.chunk_count.toLocaleString()} chunks ·{" "}
            {item.character_count.toLocaleString()} characters ·{" "}
            {item.embedding_model || "Embedding model unavailable"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {item.publication_id && (
            <Link href={`/publications/${item.publication_id}`} className="btn">
              <BookOpen size={15} /> Publication
            </Link>
          )}
          <Link href={`/ai/assistant?documentId=${item.id}`} className="btn">
            <MessageSquareText size={15} /> Ask AI
          </Link>
          {original && (
            <a
              href={original}
              target="_blank"
              rel="noopener noreferrer"
              className="btn"
            >
              Original source <ExternalLink size={15} />
            </a>
          )}
        </div>
      </header>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(22rem,.7fr)]">
        <Card className="min-h-[70vh] overflow-hidden">
          <iframe
            title={`PDF: ${item.title || "Research document"}`}
            src={`/backend-api/documents/${encodeURIComponent(id)}/content${page ? `#page=${page}` : ""}`}
            loading="lazy"
            className="h-[75vh] w-full"
          />
        </Card>
        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="font-serif text-xl font-bold">Full-text chunks</h2>
            <label className="relative mt-3 block">
              <span className="sr-only">Search within document</span>
              <Search
                className="absolute left-3 top-3 text-stone-400"
                size={16}
              />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search within document"
                className="input pl-9"
              />
            </label>
            <label className="mt-2 block text-xs font-semibold">
              Page
              <input
                type="number"
                min={1}
                max={item.page_count || 100000}
                value={page ?? ""}
                onChange={(event) =>
                  setPage(
                    event.target.value ? Number(event.target.value) : undefined,
                  )
                }
                className="input mt-1"
              />
            </label>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <label className="block text-xs font-semibold">
                Section
                <input
                  value={section}
                  onChange={(event) => setSection(event.target.value)}
                  placeholder="e.g. Methodology"
                  className="input mt-1"
                />
              </label>
              <label className="block text-xs font-semibold">
                Content type
                <select
                  value={contentType}
                  onChange={(event) => setContentType(event.target.value)}
                  className="input mt-1"
                >
                  <option value="">All content</option>
                  <option value="text">Text</option>
                  <option value="abstract">Abstract</option>
                  <option value="methodology">Methodology</option>
                  <option value="conclusion">Conclusion</option>
                  <option value="table">Table</option>
                </select>
              </label>
            </div>
          </Card>
          <div className="max-h-[60vh] space-y-3 overflow-y-auto">
            {chunks.isPending && <Skeleton className="h-40" />}
            {chunks.data?.items.map((chunk) => (
              <Card key={chunk.id} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="text-xs font-bold text-emerald-700">
                      {chunk.page_start
                        ? `Page ${chunk.page_start}${chunk.page_end && chunk.page_end !== chunk.page_start ? `–${chunk.page_end}` : ""}`
                        : `Chunk ${chunk.chunk_index + 1}`}
                    </span>
                    <h3 className="text-sm font-semibold">
                      {chunk.section_title ||
                        chunk.content_type ||
                        "Document text"}
                    </h3>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      void navigator.clipboard.writeText(chunk.content)
                    }
                    aria-label="Copy chunk text"
                  >
                    <Clipboard size={15} />
                  </button>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-xs leading-5">
                  {chunk.content}
                </p>
                <Link
                  href={`/ai/assistant?documentId=${id}`}
                  className="mt-3 inline-flex text-xs font-semibold text-emerald-700"
                >
                  Ask AI about this chunk
                </Link>
              </Card>
            ))}
            {chunks.data && !chunks.data.items.length && (
              <Card className="p-6 text-center text-sm text-stone-500">
                No chunks match these filters.
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
