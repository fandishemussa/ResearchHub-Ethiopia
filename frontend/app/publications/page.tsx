"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpen, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api } from "@/lib/api";
import { Button, Card, Skeleton } from "@/components/ui";

const filtersSchema = z.object({
  query: z.string().max(250),
  year: z.string().regex(/^\d{4}$|^$/),
  language: z.string().max(10),
});
type Filters = z.infer<typeof filtersSchema>;

export default function PublicationsPage() {
  const [filters, setFilters] = useState<Filters>({
    query: "",
    year: "",
    language: "",
  });
  const [offset, setOffset] = useState(0);
  const form = useForm<Filters>({
    resolver: zodResolver(filtersSchema),
    defaultValues: filters,
  });
  const params = new URLSearchParams({ limit: "12", offset: String(offset) });
  if (filters.query) params.set("q", filters.query);
  if (filters.year) params.set("year", filters.year);
  if (filters.language) params.set("language", filters.language);
  const publications = useQuery({
    queryKey: ["publications", params.toString()],
    queryFn: ({ signal }) => api.publications(params, signal),
  });
  const submit = form.handleSubmit((values) => {
    setFilters(values);
    setOffset(0);
  });
  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[.18em] text-amber-700 dark:text-amber-400">
          Research catalogue
        </p>
        <h1 className="mt-2 font-serif text-3xl font-bold sm:text-4xl">
          Publications
        </h1>
        <p className="mt-2 text-stone-500">
          Search and explore research from Ethiopian institutions.
        </p>
      </div>
      <Card className="p-4">
        <form
          onSubmit={submit}
          className="grid gap-3 md:grid-cols-[1fr_140px_150px_auto]"
        >
          <label className="relative">
            <Search
              className="absolute left-3 top-3 text-stone-400"
              size={18}
            />
            <input
              {...form.register("query")}
              className="h-11 w-full rounded-lg border border-stone-200 bg-transparent pl-10 pr-3 outline-none focus:ring-2 focus:ring-emerald-700 dark:border-stone-700"
              placeholder="Title, author, topic…"
            />
          </label>
          <input
            {...form.register("year")}
            className="h-11 rounded-lg border border-stone-200 bg-transparent px-3 dark:border-stone-700"
            placeholder="Year"
            inputMode="numeric"
          />
          <select
            {...form.register("language")}
            className="h-11 rounded-lg border border-stone-200 bg-white px-3 dark:border-stone-700 dark:bg-stone-900"
          >
            <option value="">All languages</option>
            <option value="en">English</option>
            <option value="am">Amharic</option>
            <option value="om">Afaan Oromo</option>
          </select>
          <Button className="h-11">Search</Button>
        </form>
        {form.formState.errors.year && (
          <p className="mt-2 text-xs text-red-600">
            Enter a valid four-digit year.
          </p>
        )}
      </Card>
      {publications.isError ? (
        <Card className="border-red-200 bg-red-50 p-5 text-red-800 dark:bg-red-950/20">
          Could not load publications. Check the API connection.
        </Card>
      ) : publications.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton className="h-64" key={i} />
          ))}
        </div>
      ) : publications.data?.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {publications.data.map((item) => (
            <Link href={`/publications/${item.id}`} key={item.id}>
              <Card className="group flex h-full min-h-64 flex-col p-5 transition hover:-translate-y-0.5 hover:shadow-md">
                <div className="mb-4 flex justify-between text-xs uppercase tracking-wider text-stone-400">
                  <span>{item.source_type.replaceAll("-", " ")}</span>
                  <span>{item.publication_year ?? "Undated"}</span>
                </div>
                <h2 className="line-clamp-3 font-serif text-lg font-bold leading-snug group-hover:text-emerald-800 dark:group-hover:text-emerald-400">
                  {item.title}
                </h2>
                <p className="mt-3 line-clamp-3 text-sm leading-6 text-stone-500">
                  {item.abstract || "Abstract not available for this record."}
                </p>
                <div className="mt-auto flex items-end justify-between pt-5 text-sm">
                  <span className="line-clamp-1 max-w-[80%] text-stone-500">
                    {item.authors?.join(", ") || item.publisher || item.source}
                  </span>
                  <ArrowRight size={17} />
                </div>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <Card className="grid min-h-72 place-items-center text-center">
          <div>
            <BookOpen className="mx-auto mb-3 text-stone-400" />
            <h2 className="font-serif text-xl font-bold">
              No publications found
            </h2>
            <p className="mt-1 text-sm text-stone-500">
              Try a broader query or remove a filter.
            </p>
          </div>
        </Card>
      )}
      <div className="flex items-center justify-center gap-4">
        <Button
          className="bg-white text-stone-800 ring-1 ring-stone-200 hover:bg-stone-50 dark:bg-stone-900 dark:text-white"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 12))}
        >
          Previous
        </Button>
        <span className="text-sm text-stone-500">Page {offset / 12 + 1}</span>
        <Button
          disabled={(publications.data?.length ?? 0) < 12}
          onClick={() => setOffset(offset + 12)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
