"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpen,
  Calendar,
  ExternalLink,
  FileText,
  UserRound,
  Copy,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { safeHttpUrl } from "@/lib/urls";
import { Card, Skeleton } from "@/components/ui";

export function PublicationDetail({ id }: { id: string }) {
  const publication = useQuery({
    queryKey: ["publication", id],
    queryFn: ({ signal }) => api.publication(id, signal),
    retry: (count, error) =>
      error instanceof ApiError && error.kind === "network" && count < 1,
  });

  if (publication.isPending) return <DetailSkeleton />;
  if (publication.isError) {
    const missing =
      publication.error instanceof ApiError &&
      publication.error.kind === "not-found";
    return (
      <Card className="grid min-h-72 place-items-center p-8 text-center">
        <div>
          <BookOpen className="mx-auto mb-3 text-stone-400" />
          <h1 className="font-serif text-2xl font-bold">
            {missing ? "Publication not found" : "Publication unavailable"}
          </h1>
          <p className="mt-2 text-sm text-stone-500">
            {missing
              ? "This record may have been removed or is no longer public."
              : "The API could not load this publication. Try again shortly."}
          </p>
          <button
            onClick={() => publication.refetch()}
            className="mt-5 rounded-lg bg-emerald-800 px-4 py-2 text-sm font-semibold text-white"
          >
            Try again
          </button>
        </div>
      </Card>
    );
  }

  const item = publication.data;
  const articleUrl = safeHttpUrl(item.article_url);
  const pdfUrl = safeHttpUrl(item.pdf_url);
  return (
    <div className="space-y-6">
      <Link
        href="/publications"
        className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-800 hover:underline dark:text-emerald-400"
      >
        <ArrowLeft size={16} /> Back to publications
      </Link>
      <Card className="p-5 sm:p-8">
        <div className="flex flex-wrap gap-2 text-xs uppercase tracking-wider text-stone-500">
          <span className="rounded-full bg-emerald-50 px-3 py-1 font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
            {item.source_type?.replaceAll("-", " ") || "Research"}
          </span>
          <span className="px-2 py-1">{item.source || "Unknown source"}</span>
        </div>
        <h1 className="mt-5 break-words font-serif text-3xl font-bold leading-tight sm:text-4xl">
          {item.title || "Untitled publication"}
        </h1>
        <div className="mt-5 flex flex-wrap gap-x-6 gap-y-3 text-sm text-stone-500">
          <span className="flex items-center gap-2">
            <Calendar size={16} />
            {item.publication_year ?? "Year unavailable"}
          </span>
          <span className="flex items-center gap-2">
            <UserRound size={16} />
            {item.authors.length
              ? item.authors.join(", ")
              : "Authors unavailable"}
          </span>
          {item.doi && <span>DOI: {item.doi}</span>}
        </div>
        <div className="mt-7 flex flex-wrap gap-2">
          {articleUrl && (
            <a
              href={articleUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-800 px-4 py-2 text-sm font-semibold text-white"
            >
              View source <ExternalLink size={15} />
              <span className="sr-only">opens in a new tab</span>
            </a>
          )}
          {pdfUrl && (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg border border-stone-200 px-4 py-2 text-sm font-semibold dark:border-stone-700"
            >
              <FileText size={15} /> Open PDF
              <span className="sr-only">opens in a new tab</span>
            </a>
          )}
        </div>
      </Card>
      <Card className="p-5 sm:p-8">
        <h2 className="font-serif text-xl font-bold">Abstract</h2>
        <p className="mt-4 whitespace-pre-line leading-7 text-stone-600 dark:text-stone-300">
          {item.abstract || "No abstract is available for this publication."}
        </p>
      </Card>
      {(item.keywords.length > 0 || item.subjects.length > 0) && (
        <Card className="p-5 sm:p-8">
          <h2 className="font-serif text-xl font-bold">Topics</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            {[...new Set([...item.keywords, ...item.subjects])].map((topic) => (
              <span
                key={topic}
                className="rounded-full bg-stone-100 px-3 py-1.5 text-sm dark:bg-stone-800"
              >
                {topic}
              </span>
            ))}
          </div>
        </Card>
      )}
      <SimilarResearch publicationId={item.id} />
      <PublicationIntelligence publicationId={item.id} />
    </div>
  );
}

function PublicationIntelligence({ publicationId }: { publicationId: string }) {
  const summary = useMutation({
    mutationFn: () => api.summarizePublication(publicationId),
  });
  const keywords = useMutation({
    mutationFn: () => api.extractPublicationKeywords(publicationId),
  });
  const citation = useMutation({
    mutationFn: () => api.publicationCitation(publicationId, "apa7"),
  });
  const busy = summary.isPending || keywords.isPending || citation.isPending;
  return (
    <Card className="p-5 sm:p-8">
      <div className="flex items-center gap-2">
        <Sparkles size={20} className="text-amber-500" />
        <h2 className="font-serif text-xl font-bold">Research intelligence</h2>
      </div>
      <p className="mt-2 text-sm text-stone-500">
        Generate grounded assistance from this publication&apos;s metadata and
        abstract.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          disabled={busy}
          onClick={() => summary.mutate()}
          className="rounded-lg bg-emerald-800 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          Generate summary
        </button>
        <button
          disabled={busy}
          onClick={() => keywords.mutate()}
          className="rounded-lg border border-stone-300 px-3 py-2 text-sm font-semibold disabled:opacity-50 dark:border-stone-700"
        >
          Extract keywords
        </button>
        <button
          disabled={busy}
          onClick={() => citation.mutate()}
          className="rounded-lg border border-stone-300 px-3 py-2 text-sm font-semibold disabled:opacity-50 dark:border-stone-700"
        >
          Generate APA citation
        </button>
        <Link
          href={`/ai/assistant?publication=${publicationId}`}
          className="rounded-lg border border-stone-300 px-3 py-2 text-sm font-semibold dark:border-stone-700"
        >
          Ask AI about this paper
        </Link>
      </div>
      {summary.data && (
        <div className="mt-5 rounded-xl bg-stone-100 p-4 dark:bg-stone-800">
          <strong className="text-sm">Abstract-based summary</strong>
          <p className="mt-2 whitespace-pre-line text-sm leading-6">
            {summary.data.summary_text}
          </p>
        </div>
      )}
      {keywords.data && (
        <div className="mt-5 flex flex-wrap gap-2">
          {keywords.data.map((item) => (
            <span
              key={item.id}
              className="rounded-full bg-amber-50 px-3 py-1 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200"
            >
              {item.keyword} · {Math.round(Number(item.confidence_score) * 100)}
              %
            </span>
          ))}
        </div>
      )}
      {citation.data && (
        <div className="mt-5 rounded-xl bg-stone-100 p-4 dark:bg-stone-800">
          <p className="text-sm leading-6">{citation.data.citation_text}</p>
          <button
            onClick={() =>
              void navigator.clipboard.writeText(citation.data.citation_text)
            }
            className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-emerald-800 dark:text-emerald-300"
          >
            <Copy size={13} /> Copy citation
          </button>
        </div>
      )}
      {(summary.isError || keywords.isError || citation.isError) && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          The intelligence request failed. Apply the latest migration and try
          again.
        </p>
      )}
    </Card>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-5 w-40" />
      <Card className="space-y-5 p-8">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-10 w-5/6" />
        <Skeleton className="h-5 w-2/3" />
      </Card>
      <Skeleton className="h-64" />
    </div>
  );
}

function SimilarResearch({ publicationId }: { publicationId: string }) {
  const similar = useQuery({
    queryKey: ["similar-publications", publicationId],
    queryFn: ({ signal }) =>
      api.similarPublications(
        publicationId,
        { limit: 6, minimumScore: 0.35 },
        signal,
      ),
    retry: false,
  });

  if (similar.isPending) {
    return (
      <Card className="p-5 sm:p-8">
        <h2 className="font-serif text-xl font-bold">Similar research</h2>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-32" />
          ))}
        </div>
      </Card>
    );
  }
  if (similar.isError) {
    const unavailable =
      similar.error instanceof ApiError && similar.error.status === 409;
    return (
      <Card className="p-5 sm:p-8">
        <h2 className="font-serif text-xl font-bold">Similar research</h2>
        <p className="mt-3 text-sm text-stone-500">
          {unavailable
            ? "Similarity results will appear after this publication has an embedding."
            : "Similar publications could not be loaded."}
        </p>
      </Card>
    );
  }

  return (
    <Card className="p-5 sm:p-8">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="font-serif text-xl font-bold">Similar research</h2>
          <p className="mt-1 text-xs text-stone-500">
            Model: {similar.data.model}
          </p>
        </div>
        <span className="text-sm text-stone-500">
          {similar.data.count} result{similar.data.count === 1 ? "" : "s"}
        </span>
      </div>
      {similar.data.results.length ? (
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {similar.data.results.map((result) => {
            const score = Number.isFinite(result.similarity_score)
              ? result.similarity_score
              : 0;
            const percentage = Math.max(
              0,
              Math.min(100, Math.round(score * 100)),
            );
            return (
              <Link
                key={result.id}
                href={`/publications/${result.id}`}
                className="rounded-xl border border-stone-200 p-4 transition hover:border-emerald-700 hover:shadow-sm dark:border-stone-700"
              >
                <div className="flex justify-between gap-3 text-xs text-stone-500">
                  <span>{result.publication_year ?? "Undated"}</span>
                  <strong>{percentage}% similar</strong>
                </div>
                <h3 className="mt-2 line-clamp-2 font-serif font-bold">
                  {result.title || "Untitled publication"}
                </h3>
                <p className="mt-2 line-clamp-2 text-sm text-stone-500">
                  {result.abstract_preview || "Abstract unavailable."}
                </p>
                {result.shared_keywords.length > 0 && (
                  <p className="mt-3 text-xs text-emerald-800 dark:text-emerald-400">
                    Shared: {result.shared_keywords.slice(0, 3).join(", ")}
                  </p>
                )}
              </Link>
            );
          })}
        </div>
      ) : (
        <p className="mt-5 text-sm text-stone-500">
          No sufficiently similar embedded publications were found.
        </p>
      )}
    </Card>
  );
}
