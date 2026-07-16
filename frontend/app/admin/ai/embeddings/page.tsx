"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function EmbeddingAdministrationPage() {
  const status = useQuery({
    queryKey: ["embedding-administration"],
    queryFn: ({ signal }) => api.embeddingAdministration(signal),
    refetchInterval: 10_000,
  });
  const generate = useMutation({
    mutationFn: (mode: "missing" | "stale" | "failed") =>
      api.generateEmbeddings(mode),
  });
  const values = status.data;
  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[.2em] text-amber-700">
          AI operations
        </p>
        <h1 className="mt-2 font-serif text-4xl font-bold">
          Publication embeddings
        </h1>
        <p className="mt-2 text-stone-600 dark:text-stone-300">
          Bounded generation controls and live semantic-index coverage.
        </p>
      </header>
      {status.isPending ? (
        <div role="status">Loading embedding status…</div>
      ) : status.isError || !values ? (
        <div
          role="alert"
          className="rounded-xl border border-red-300 p-4 text-red-700"
        >
          Embedding status could not be loaded or access was denied.
        </div>
      ) : (
        <>
          <section
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5"
            aria-label="Embedding coverage"
          >
            {[
              ["Total", values.total_publications],
              ["Embedded", values.embedded_publications],
              ["Missing", values.missing_embeddings],
              ["Stale", values.stale_embeddings],
              ["Failed", values.failed_embeddings],
            ].map(([label, value]) => (
              <article
                key={label}
                className="rounded-2xl border border-stone-200 bg-white p-5 dark:border-stone-800 dark:bg-stone-900"
              >
                <p className="text-sm text-stone-500">{label}</p>
                <p className="mt-2 text-3xl font-bold">{value}</p>
              </article>
            ))}
          </section>
          <p className="text-sm text-stone-500">
            {values.embedding_model} · {values.vector_dimension} dimensions ·
            queue {values.queue}
          </p>
          <div className="flex flex-wrap gap-3">
            {(["missing", "stale", "failed"] as const).map((mode) => (
              <button
                key={mode}
                disabled={generate.isPending}
                onClick={() => generate.mutate(mode)}
                className="rounded-xl bg-emerald-800 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {mode === "missing"
                  ? "Generate missing"
                  : mode === "stale"
                    ? "Regenerate stale"
                    : "Retry failed"}
              </button>
            ))}
          </div>
          {generate.data && (
            <p role="status">Queued job {generate.data.task_id}</p>
          )}
          {generate.isError && (
            <p role="alert" className="text-red-700">
              The generation request failed.
            </p>
          )}
        </>
      )}
    </div>
  );
}
