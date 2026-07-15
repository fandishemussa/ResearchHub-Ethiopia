"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, Search } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { Card, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";

export default function DocumentsPage() {
  const [search, setSearch] = useState("");
  const deferred = useDeferredValue(search);
  const params = new URLSearchParams({ limit: "50" });
  if (deferred) params.set("search", deferred);
  const query = useQuery({
    queryKey: ["documents", deferred],
    queryFn: ({ signal }) => api.researchDocuments(params, signal),
  });
  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-[.18em] text-amber-700">
          Full-text research
        </p>
        <h1 className="mt-2 font-serif text-4xl font-bold">
          Indexed documents
        </h1>
        <p className="mt-2 text-stone-500">
          Browse extracted and embedded PDFs without exposing server file paths.
        </p>
      </header>
      <label className="relative block max-w-xl">
        <span className="sr-only">Search indexed documents</span>
        <Search className="absolute left-3 top-3 text-stone-400" size={18} />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search document titles"
          className="input pl-10"
        />
      </label>
      {query.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-48" />
          ))}
        </div>
      ) : query.isError ? (
        <Card className="p-8 text-center">
          Indexed documents could not be loaded.
        </Card>
      ) : query.data.items.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {query.data.items.map((item) => (
            <Link key={item.id} href={`/documents/${item.id}`}>
              <Card className="h-full p-5 transition hover:border-emerald-600">
                <div className="flex justify-between">
                  <span className="grid size-10 place-items-center rounded-xl bg-emerald-50 text-emerald-800 dark:bg-emerald-950">
                    <FileText />
                  </span>
                  <span className="text-xs capitalize text-stone-500">
                    {item.extraction_status}
                  </span>
                </div>
                <h2 className="mt-4 line-clamp-2 font-serif text-lg font-bold">
                  {item.title || "Untitled indexed document"}
                </h2>
                <p className="mt-2 text-xs uppercase tracking-wider text-stone-500">
                  {item.source}
                </p>
                <p className="mt-4 text-xs text-stone-500">
                  {item.page_count ?? "?"} pages ·{" "}
                  {item.chunk_count.toLocaleString()} chunks ·{" "}
                  {item.embedded_chunk_count.toLocaleString()} embedded
                </p>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <Card className="p-10 text-center text-stone-500">
          No indexed documents match this search.
        </Card>
      )}
    </div>
  );
}
