"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2, Database, ExternalLink, MapPin, Plus } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Card, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { safeHttpUrl } from "@/lib/urls";

export function UniversitiesCatalog() {
  const query = useQuery({
    queryKey: ["universities"],
    queryFn: ({ signal }) => api.universities(signal),
  });
  return (
    <CatalogLayout
      eyebrow="Institutional network"
      title="Universities"
      description="Ethiopian universities represented in the national research catalogue."
    >
      {query.isPending ? (
        <CatalogSkeleton />
      ) : query.isError ? (
        <CatalogError error={query.error} retry={() => query.refetch()} />
      ) : query.data.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {query.data.map((item) => {
            const website = safeHttpUrl(item.website_url);
            return (
              <Card key={item.id} className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <span className="grid size-11 place-items-center rounded-xl bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                    <Building2 />
                  </span>
                  <span
                    className={
                      item.is_active
                        ? "text-xs font-semibold text-emerald-700"
                        : "text-xs text-stone-400"
                    }
                  >
                    {item.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
                <h2 className="mt-4 font-serif text-xl font-bold">
                  {item.name}
                </h2>
                <p className="mt-1 text-sm text-stone-500">{item.code}</p>
                {item.city && (
                  <p className="mt-4 flex items-center gap-2 text-sm text-stone-500">
                    <MapPin size={15} />
                    {item.city}, {item.country}
                  </p>
                )}
                {website && (
                  <a
                    href={website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-emerald-800 hover:underline dark:text-emerald-400"
                  >
                    Visit website <ExternalLink size={14} />
                    <span className="sr-only">opens in a new tab</span>
                  </a>
                )}
              </Card>
            );
          })}
        </div>
      ) : (
        <CatalogEmpty
          icon={Building2}
          label="No universities are registered yet."
        />
      )}
    </CatalogLayout>
  );
}

export function RepositoriesCatalog() {
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: ({ signal }) => api.sources(signal),
    refetchInterval: 15_000,
  });
  return (
    <CatalogLayout
      eyebrow="Connected sources"
      title="Repositories"
      description="Live, editable research sources connected to ResearchHub."
      action={
        <Link
          href="/repositories/new"
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-800 px-4 py-2 text-sm font-semibold text-white"
        >
          <Plus size={16} /> Add source
        </Link>
      }
    >
      {sources.isPending ? (
        <CatalogSkeleton />
      ) : sources.isError ? (
        <CatalogError error={sources.error} retry={() => sources.refetch()} />
      ) : sources.data.length ? (
        <section aria-labelledby="managed-sources-heading">
          <h2
            id="managed-sources-heading"
            className="mb-3 font-serif text-xl font-bold"
          >
            Managed sources
          </h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {sources.data.map((source) => (
              <Link
                key={source.id}
                href={`/repositories/${source.id}`}
                className="block"
              >
                <Card className="h-full p-5 transition hover:border-emerald-700 hover:shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <span className="grid size-11 place-items-center rounded-xl bg-emerald-50 text-emerald-800 dark:bg-emerald-950">
                      <Database />
                    </span>
                    <span className="rounded-full bg-stone-100 px-2 py-1 text-xs font-semibold capitalize dark:bg-stone-800">
                      {source.status}
                    </span>
                  </div>
                  <h3 className="mt-4 font-serif text-xl font-bold">
                    {source.name}
                  </h3>
                  <p className="mt-1 text-xs uppercase tracking-wider text-stone-500">
                    {source.source_type.replaceAll("_", " ")}
                  </p>
                  <p className="mt-4 truncate text-xs text-stone-500">
                    {source.oai_endpoint ||
                      source.base_url ||
                      "File import source"}
                  </p>
                  <p className="mt-2 text-xs text-stone-500">
                    {source.total_records_harvested.toLocaleString()} harvested
                    records
                  </p>
                </Card>
              </Link>
            ))}
          </div>
        </section>
      ) : (
        <Card className="p-5 text-sm text-stone-500">
          No managed sources have been connected yet. Use{" "}
          <strong>Add source</strong> to begin.
        </Card>
      )}
    </CatalogLayout>
  );
}

function CatalogLayout({
  eyebrow,
  title,
  description,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[.18em] text-amber-700 dark:text-amber-400">
            {eyebrow}
          </p>
          <h1 className="mt-2 font-serif text-3xl font-bold sm:text-4xl">
            {title}
          </h1>
          <p className="mt-2 text-stone-500">{description}</p>
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function CatalogSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }, (_, index) => (
        <Skeleton key={index} className="h-56" />
      ))}
    </div>
  );
}

function CatalogError({ error, retry }: { error: Error; retry: () => void }) {
  const message =
    error instanceof ApiError && error.kind === "network"
      ? "The ResearchHub API is unreachable."
      : "The managed sources could not be loaded.";
  return (
    <Card className="p-8 text-center">
      <p className="font-semibold">{message}</p>
      <button
        onClick={retry}
        className="mt-4 rounded-lg bg-emerald-800 px-4 py-2 text-sm font-semibold text-white"
      >
        Try again
      </button>
    </Card>
  );
}

function CatalogEmpty({
  icon: Icon,
  label,
}: {
  icon: typeof Building2;
  label: string;
}) {
  return (
    <Card className="grid min-h-64 place-items-center text-center">
      <div>
        <Icon className="mx-auto mb-3 text-stone-400" />
        <p className="text-stone-500">{label}</p>
      </div>
    </Card>
  );
}
