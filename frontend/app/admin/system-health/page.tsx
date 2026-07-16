"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, RefreshCw, Server } from "lucide-react";
import { api } from "@/lib/api";

export default function SystemHealthPage() {
  const health = useQuery({
    queryKey: ["system-health"],
    queryFn: ({ signal }) => api.systemHealth(signal),
    refetchInterval: 15_000,
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[.2em] text-amber-700">
            Operations
          </p>
          <h1 className="mt-2 font-serif text-4xl font-bold">System health</h1>
          <p className="mt-2 text-stone-600 dark:text-stone-300">
            Live API dependency status. Refreshes every 15 seconds.
          </p>
        </div>
        <button
          className="flex items-center gap-2 rounded-xl border border-stone-300 px-4 py-2 text-sm dark:border-stone-700"
          onClick={() => void health.refetch()}
          disabled={health.isFetching}
        >
          <RefreshCw
            size={16}
            className={health.isFetching ? "animate-spin" : ""}
            aria-hidden="true"
          />
          Refresh
        </button>
      </header>
      {health.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="h-32 animate-pulse rounded-2xl bg-stone-200 dark:bg-stone-800" />
          <div className="h-32 animate-pulse rounded-2xl bg-stone-200 dark:bg-stone-800" />
        </div>
      ) : health.isError || !health.data ? (
        <div
          role="alert"
          className="rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        >
          <AlertCircle className="mb-2" aria-hidden="true" />
          The API health endpoint is unreachable. Check the API process, proxy
          routing, and network configuration.
        </div>
      ) : (
        <>
          <div
            className={
              health.data.status === "ok"
                ? "rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100"
                : "rounded-2xl border border-amber-200 bg-amber-50 p-5 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100"
            }
          >
            <div className="flex items-center gap-3">
              {health.data.status === "ok" ? (
                <CheckCircle2 aria-hidden="true" />
              ) : (
                <AlertCircle aria-hidden="true" />
              )}
              <div>
                <p className="font-bold">
                  {health.data.status === "ok"
                    ? "All reported dependencies are available"
                    : "One or more dependencies are degraded"}
                </p>
                <p className="text-xs opacity-75">
                  Instance {health.data.instance_id}
                </p>
              </div>
            </div>
          </div>
          <section
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
            aria-label="Dependency status"
          >
            {Object.entries(health.data.checks).map(([name, status]) => {
              const available = status === "ok";
              return (
                <article
                  key={name}
                  className="rounded-2xl border border-stone-200 bg-white p-5 dark:border-stone-800 dark:bg-stone-900"
                >
                  <div className="flex items-center justify-between">
                    <Server className="text-emerald-700" aria-hidden="true" />
                    <span
                      className={
                        available
                          ? "rounded-full bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-800"
                          : "rounded-full bg-red-100 px-2 py-1 text-xs font-semibold text-red-800"
                      }
                    >
                      {status}
                    </span>
                  </div>
                  <h2 className="mt-4 font-serif text-xl font-bold capitalize">
                    {name.replaceAll("_", " ")}
                  </h2>
                </article>
              );
            })}
          </section>
          <p className="text-xs text-stone-500">
            This page reports API dependencies only. Worker, queue, storage,
            model, backup, and alert delivery require additional operations
            validation.
          </p>
        </>
      )}
    </div>
  );
}
