"use client";

import { useQuery } from "@tanstack/react-query";
import { Search, UserRound } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";

export default function ResearchersPage() {
  const [query, setQuery] = useState("");
  const researchers = useQuery({
    queryKey: ["researchers"],
    queryFn: ({ signal }) => api.researchers(signal),
  });
  const filtered = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return researchers.data ?? [];
    return (researchers.data ?? []).filter((item) =>
      [item.full_name, item.affiliation, item.orcid]
        .filter(Boolean)
        .some((field) => field!.toLowerCase().includes(value)),
    );
  }, [query, researchers.data]);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[.2em] text-amber-700">
          Research expertise
        </p>
        <h1 className="mt-2 font-serif text-4xl font-bold">Researchers</h1>
        <p className="mt-2 text-stone-600 dark:text-stone-300">
          Discover normalized author identities and institutional affiliations.
        </p>
      </header>
      <label className="flex max-w-xl items-center gap-2 rounded-xl border border-stone-300 bg-white px-3 dark:border-stone-700 dark:bg-stone-900">
        <Search size={18} aria-hidden="true" className="text-stone-500" />
        <span className="sr-only">Search researchers</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name, affiliation, or ORCID"
          className="w-full bg-transparent py-3 outline-none"
        />
      </label>
      {researchers.isPending ? (
        <div
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          aria-label="Loading researchers"
        >
          {[1, 2, 3, 4, 5, 6].map((item) => (
            <div
              key={item}
              className="h-36 animate-pulse rounded-2xl bg-stone-200 dark:bg-stone-800"
            />
          ))}
        </div>
      ) : researchers.isError ? (
        <div
          role="alert"
          className="rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        >
          The researcher directory could not be loaded.
          <button
            className="ml-3 underline"
            onClick={() => void researchers.refetch()}
          >
            Try again
          </button>
        </div>
      ) : filtered.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((researcher) => (
            <article
              key={researcher.id}
              className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm dark:border-stone-800 dark:bg-stone-900"
            >
              <span className="grid size-10 place-items-center rounded-xl bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
                <UserRound aria-hidden="true" />
              </span>
              <h2 className="mt-4 font-serif text-xl font-bold">
                {researcher.full_name}
              </h2>
              <p className="mt-1 text-sm text-stone-600 dark:text-stone-300">
                {researcher.affiliation || "Affiliation not recorded"}
              </p>
              {researcher.orcid ? (
                <p className="mt-3 text-xs font-medium text-emerald-800 dark:text-emerald-300">
                  ORCID {researcher.orcid}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-stone-300 p-10 text-center dark:border-stone-700">
          <UserRound className="mx-auto text-stone-400" aria-hidden="true" />
          <p className="mt-3 font-medium">No matching researchers</p>
          <p className="mt-1 text-sm text-stone-500">
            Try a broader name or affiliation.
          </p>
        </div>
      )}
      <p className="text-xs text-stone-500">
        This directory reflects harvested author metadata. Verified profiles,
        publication claims, CV export, and external identity synchronization are
        not yet enabled.
      </p>
    </div>
  );
}
