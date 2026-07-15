"use client";

import { Check, Copy, ExternalLink, HelpCircle } from "lucide-react";
import { memo, useEffect, useRef, useState } from "react";
import type { SemanticSearchResult } from "@/lib/types";
import { trackSearchEvent } from "@/lib/analytics";
import { Card } from "@/components/ui";
import { safeHttpUrl } from "@/lib/urls";

export const SemanticSearchResultCard = memo(function SemanticSearchResultCard({
  result,
}: {
  result: SemanticSearchResult;
}) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const copiedTimer = useRef<number | null>(null);
  const normalizedSimilarity = Number.isFinite(result.similarity)
    ? result.similarity
    : 0;
  const percentage = Math.max(
    0,
    Math.min(100, Math.round(normalizedSimilarity * 100)),
  );
  const articleUrl = safeHttpUrl(result.article_url);
  const title = result.title?.trim() || "Untitled publication";

  useEffect(
    () => () => {
      if (copiedTimer.current !== null)
        window.clearTimeout(copiedTimer.current);
    },
    [],
  );

  async function copyLink() {
    if (!articleUrl) return;
    try {
      await navigator.clipboard.writeText(articleUrl);
      setCopyFailed(false);
      setCopied(true);
      trackSearchEvent("semantic_result_link_copied", {
        publicationId: result.id,
      });
      if (copiedTimer.current !== null)
        window.clearTimeout(copiedTimer.current);
      copiedTimer.current = window.setTimeout(() => {
        copiedTimer.current = null;
        setCopied(false);
      }, 1800);
    } catch {
      setCopied(false);
      setCopyFailed(true);
    }
  }

  return (
    <article aria-labelledby={`result-${result.id}`}>
      <Card className="overflow-hidden p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full bg-emerald-50 px-2.5 py-1 font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
              {result.source || "Unknown source"}
            </span>
            <span className="text-stone-500">
              {result.publication_year ?? "Year unavailable"}
            </span>
          </div>
          <div
            className="w-36"
            title="Semantic similarity measures closeness in embedding space; it is not a confidence score."
          >
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="flex items-center gap-1 text-stone-500">
                Similarity <HelpCircle size={12} aria-hidden="true" />
              </span>
              <strong>{percentage}%</strong>
            </div>
            <div
              className="h-1.5 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700"
              role="progressbar"
              aria-label={`Semantic similarity ${percentage}%`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percentage}
            >
              <span
                className="block h-full rounded-full bg-amber-500"
                style={{ width: `${percentage}%` }}
              />
            </div>
          </div>
        </div>
        <h2
          id={`result-${result.id}`}
          className="mt-4 break-words font-serif text-xl font-bold leading-snug text-stone-950 dark:text-white"
        >
          {title}
        </h2>
        <p className="mt-3 min-h-18 text-sm leading-6 text-stone-600 dark:text-stone-300">
          {result.abstract_preview ||
            "No abstract preview is available for this publication."}
        </p>
        <div className="mt-5 flex flex-wrap gap-2 border-t border-stone-100 pt-4 dark:border-stone-800">
          {articleUrl ? (
            <a
              href={articleUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() =>
                trackSearchEvent("semantic_result_opened", {
                  publicationId: result.id,
                })
              }
              className="inline-flex h-9 items-center gap-2 rounded-lg bg-emerald-800 px-3 text-sm font-semibold text-white hover:bg-emerald-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
            >
              View publication <ExternalLink size={15} aria-hidden="true" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          ) : (
            <span className="inline-flex h-9 items-center rounded-lg bg-stone-100 px-3 text-sm text-stone-400 dark:bg-stone-800">
              Link unavailable
            </span>
          )}
          <button
            type="button"
            disabled={!articleUrl}
            onClick={copyLink}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-stone-200 px-3 text-sm font-medium hover:bg-stone-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:cursor-not-allowed disabled:opacity-40 dark:border-stone-700 dark:hover:bg-stone-800"
            aria-label={
              copied ? "Publication link copied" : `Copy link for ${title}`
            }
          >
            {copied ? <Check size={15} /> : <Copy size={15} />}
            {copied ? "Copied" : "Copy link"}
          </button>
          {copyFailed && (
            <span
              role="status"
              className="self-center text-xs text-red-700 dark:text-red-400"
            >
              Could not copy the link.
            </span>
          )}
        </div>
      </Card>
    </article>
  );
});
