"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function MetadataQualityPage() {
  const summary = useQuery({
    queryKey: ["quality", "summary"],
    queryFn: ({ signal }) => api.qualitySummary(signal),
  });
  const issues = useQuery({
    queryKey: ["quality", "issues"],
    queryFn: ({ signal }) => api.qualityIssues(signal),
  });
  const loading = summary.isPending || issues.isPending;
  const failed = summary.isError || issues.isError;

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[.2em] text-amber-700">
          Data stewardship
        </p>
        <h1 className="mt-2 font-serif text-4xl font-bold">Metadata quality</h1>
        <p className="mt-2 text-stone-600 dark:text-stone-300">
          Monitor completeness, validity, consistency, uniqueness, timeliness,
          and accessibility.
        </p>
      </header>
      {loading ? (
        <div
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          aria-label="Loading metadata quality"
        >
          {[1, 2, 3, 4].map((item) => (
            <div
              key={item}
              className="h-28 animate-pulse rounded-2xl bg-stone-200 dark:bg-stone-800"
            />
          ))}
        </div>
      ) : failed || !summary.data || !issues.data ? (
        <div
          role="alert"
          className="rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        >
          Quality information could not be loaded.
          <button
            className="ml-3 underline"
            onClick={() => {
              void summary.refetch();
              void issues.refetch();
            }}
          >
            Try again
          </button>
        </div>
      ) : (
        <>
          <section
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
            aria-label="Quality summary"
          >
            <Metric
              label="Average quality"
              value={`${Number(summary.data.average_final_score).toFixed(1)}%`}
            />
            <Metric
              label="Assessed publications"
              value={summary.data.assessed_publications.toLocaleString()}
            />
            <Metric
              label="Open issues"
              value={issues.data.total.toLocaleString()}
            />
            <Metric
              label="Ruleset"
              value={summary.data.ruleset_version}
              compact
            />
          </section>
          <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
            <section className="rounded-2xl border border-stone-200 bg-white p-5 dark:border-stone-800 dark:bg-stone-900">
              <h2 className="font-serif text-xl font-bold">
                Dimension averages
              </h2>
              <div className="mt-5 space-y-4">
                {Object.entries(summary.data.dimension_averages).map(
                  ([name, value]) => {
                    const score = Math.max(0, Math.min(100, Number(value)));
                    return (
                      <div key={name}>
                        <div className="mb-1 flex justify-between text-sm">
                          <span className="capitalize">
                            {name.replaceAll("_", " ")}
                          </span>
                          <span>{score.toFixed(1)}%</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700">
                          <div
                            className="h-full rounded-full bg-emerald-700"
                            style={{ width: `${score}%` }}
                          />
                        </div>
                      </div>
                    );
                  },
                )}
              </div>
            </section>
            <section className="overflow-hidden rounded-2xl border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
              <div className="border-b border-stone-200 p-5 dark:border-stone-800">
                <h2 className="font-serif text-xl font-bold">Recent issues</h2>
                <p className="text-sm text-stone-500">
                  The correction/approval workflow remains an implementation
                  foundation.
                </p>
              </div>
              {issues.data.items.length ? (
                <ul className="divide-y divide-stone-200 dark:divide-stone-800">
                  {issues.data.items.map((issue, index) => (
                    <li
                      key={`${issue.report_id}-${issue.issue_type}-${index}`}
                      className="flex gap-3 p-4"
                    >
                      <AlertTriangle
                        size={18}
                        className="mt-0.5 shrink-0 text-amber-600"
                        aria-hidden="true"
                      />
                      <div className="min-w-0">
                        <p className="font-medium">{issue.message}</p>
                        <p className="mt-1 text-xs text-stone-500">
                          {issue.category} · Grade {issue.grade} ·{" "}
                          {Number(issue.final_score).toFixed(1)}
                        </p>
                        <Link
                          className="mt-2 inline-block text-sm text-emerald-800 underline dark:text-emerald-300"
                          href={`/publications/${issue.publication_id}`}
                        >
                          Review publication
                        </Link>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="p-10 text-center">
                  <CheckCircle2
                    className="mx-auto text-emerald-700"
                    aria-hidden="true"
                  />
                  <p className="mt-3 font-medium">No current issues</p>
                </div>
              )}
            </section>
          </div>
          <p className="text-xs text-stone-500">
            Updated {new Date(summary.data.generated_at).toLocaleString()}.
            Scores support stewardship decisions; they are not institutional
            rankings.
          </p>
        </>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <article className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm dark:border-stone-800 dark:bg-stone-900">
      <ShieldCheck size={19} className="text-emerald-700" aria-hidden="true" />
      <p className="mt-3 text-sm text-stone-500">{label}</p>
      <p
        className={
          compact ? "mt-1 text-sm font-bold" : "mt-1 text-2xl font-bold"
        }
      >
        {value}
      </p>
    </article>
  );
}
