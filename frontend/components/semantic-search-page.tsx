"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BookOpen,
  Clock3,
  Filter,
  LoaderCircle,
  RotateCcw,
  Search,
  ServerOff,
  Sparkles,
  X,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  type Dispatch,
  type FormEvent,
  type SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { ApiError, searchSemanticPublications } from "@/lib/api";
import { trackSearchEvent } from "@/lib/analytics";
import { Button, Card, Skeleton } from "@/components/ui";
import { SemanticSearchResultCard } from "@/components/semantic-result-card";

const suggestions = [
  "machine learning for crop disease detection",
  "maternal health challenges in Ethiopia",
  "groundwater modelling in Addis Ababa",
  "drought-resistant sorghum varieties",
  "educational challenges of students with disabilities",
];
const HISTORY_KEY = "researchhub:semantic-search-history";

export function SemanticSearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const query = searchParams.get("q")?.trim() ?? "";
  const source = searchParams.get("source") ?? "";
  const limit = boundedNumber(searchParams.get("limit"), 10, 1, 50);
  const minimum = optionalBoundedNumber(
    searchParams.get("minSimilarity"),
    0,
    1,
  );
  const [draft, setDraft] = useState(query);
  const [draftQuerySource, setDraftQuerySource] = useState(query);
  const [history, setHistory] = useState<string[]>([]);
  const debounceTimer = useRef<number | null>(null);
  const searchParamsValue = searchParams.toString();

  // Adjust during render so browser back/forward state is reflected before commit,
  // without a hydration-sensitive synchronization effect.
  if (draftQuerySource !== query) {
    setDraftQuerySource(query);
    setDraft(query);
  }
  useEffect(() => {
    // Defer the client-only read until after hydration.
    const frame = window.requestAnimationFrame(() => setHistory(readHistory()));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const cancelDebounce = useCallback(() => {
    if (debounceTimer.current !== null) {
      window.clearTimeout(debounceTimer.current);
      debounceTimer.current = null;
    }
  }, []);

  const updateUrl = useCallback(
    (values: Record<string, string | number | undefined>, push = false) => {
      const next = new URLSearchParams(searchParamsValue);
      for (const [key, value] of Object.entries(values)) {
        if (
          value === undefined ||
          value === "" ||
          (key === "limit" && value === 10)
        )
          next.delete(key);
        else next.set(key, String(value));
      }
      const url = `/search/semantic${next.size ? `?${next.toString()}` : ""}`;
      const currentUrl = `/search/semantic${searchParamsValue ? `?${searchParamsValue}` : ""}`;
      if (url === currentUrl) return;
      if (push) router.push(url);
      else router.replace(url);
    },
    [router, searchParamsValue],
  );

  useEffect(() => {
    if (draft.trim() === query) return;
    cancelDebounce();
    debounceTimer.current = window.setTimeout(() => {
      debounceTimer.current = null;
      updateUrl({ q: draft.trim() });
    }, 500);
    return cancelDebounce;
  }, [cancelDebounce, draft, query, updateUrl]);

  const search = useQuery({
    queryKey: ["semantic-search", query, source, limit, minimum],
    queryFn: ({ signal }) =>
      searchSemanticPublications({
        query,
        limit,
        source: source || undefined,
        minSimilarity: minimum,
        signal,
      }),
    enabled: Boolean(query),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    retry: (count, error) =>
      error instanceof ApiError && error.kind === "network" && count < 1,
  });

  useEffect(() => {
    if (!search.data || !query || search.isPlaceholderData) return;
    persistSearchHistory(query, setHistory);
    if (search.data.count === 0)
      trackSearchEvent("semantic_no_results", { queryLength: query.length });
  }, [query, search.data, search.dataUpdatedAt, search.isPlaceholderData]);
  useEffect(() => {
    if (search.error)
      trackSearchEvent("semantic_search_error", {
        kind: search.error instanceof ApiError ? search.error.kind : "unknown",
      });
  }, [search.error]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const value = draft.trim();
    if (!value) return;
    cancelDebounce();
    if (value === query) void search.refetch();
    else updateUrl({ q: value }, true);
    persistSearchHistory(value, setHistory);
    trackSearchEvent("semantic_search_submitted", {
      queryLength: value.length,
    });
  }
  function chooseQuery(value: string) {
    cancelDebounce();
    setDraft(value);
    updateUrl({ q: value }, true);
  }
  function clearHistory() {
    setHistory([]);
    localStorage.removeItem(HISTORY_KEY);
  }
  function reset() {
    cancelDebounce();
    setDraft("");
    updateUrl(
      {
        q: undefined,
        source: undefined,
        limit: undefined,
        minSimilarity: undefined,
      },
      true,
    );
  }
  function filterChanged(values: Record<string, string | number | undefined>) {
    updateUrl(values);
    trackSearchEvent("semantic_filter_changed", {
      fields: Object.keys(values),
    });
  }

  const filterPanel = (
    <FilterPanel
      source={source}
      limit={limit}
      minimum={minimum}
      onChange={filterChanged}
      onClear={() =>
        filterChanged({
          source: undefined,
          limit: undefined,
          minSimilarity: undefined,
        })
      }
    />
  );
  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[.18em] text-amber-700 dark:text-amber-400">
          <Sparkles size={16} /> Semantic discovery
        </p>
        <h1 className="mt-2 font-serif text-3xl font-bold sm:text-4xl">
          Search research by meaning
        </h1>
        <p className="mt-2 max-w-2xl text-stone-500">
          Describe an idea or research question in natural language. Results are
          ranked by conceptual similarity, not just matching words.
        </p>
      </div>
      <Card className="p-4 sm:p-5">
        <form onSubmit={submit}>
          <label
            htmlFor="semantic-query"
            className="mb-2 block text-sm font-semibold"
          >
            Research question or topic
          </label>
          <p id="semantic-query-help" className="mb-3 text-xs text-stone-500">
            For example: drought-resistant sorghum varieties in Ethiopia
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search
                className="absolute left-3 top-3.5 text-stone-400"
                size={19}
                aria-hidden="true"
              />
              <input
                id="semantic-query"
                aria-describedby="semantic-query-help"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                className="h-12 w-full rounded-xl border border-stone-200 bg-transparent pl-10 pr-10 outline-none transition focus-visible:ring-2 focus-visible:ring-emerald-700 dark:border-stone-700"
                placeholder="Search by meaning, for example: drought-resistant sorghum varieties in Ethiopia"
                maxLength={500}
              />
              {draft && (
                <button
                  type="button"
                  onClick={() => setDraft("")}
                  className="absolute right-3 top-3.5 text-stone-400 hover:text-stone-700"
                  aria-label="Clear search input"
                >
                  <X size={18} />
                </button>
              )}
            </div>
            <Button
              className="h-12 px-6"
              disabled={
                !draft.trim() || (search.isFetching && draft.trim() === query)
              }
              type="submit"
            >
              {search.isFetching && draft.trim() === query ? (
                <LoaderCircle className="animate-spin" size={18} />
              ) : (
                <Search size={18} />
              )}{" "}
              {search.isFetching && draft.trim() === query
                ? "Searching"
                : "Search"}
            </Button>
            <Button
              type="button"
              onClick={reset}
              className="h-12 bg-white text-stone-700 ring-1 ring-stone-200 hover:bg-stone-50 dark:bg-stone-900 dark:text-stone-200 dark:ring-stone-700"
            >
              <RotateCcw size={16} /> Reset
            </Button>
          </div>
        </form>
      </Card>
      <details className="rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900 lg:hidden">
        <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold">
          <Filter size={18} /> Search filters
        </summary>
        <div className="mt-4">{filterPanel}</div>
      </details>
      <ActiveFilters
        source={source}
        limit={limit}
        minimum={minimum}
        onRemove={filterChanged}
      />
      <div className="grid items-start gap-6 lg:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="sticky top-20 hidden lg:block">{filterPanel}</aside>
        <section
          aria-live="polite"
          aria-busy={search.isFetching}
          aria-label="Semantic search results"
          className="min-w-0 space-y-4"
        >
          {!query ? (
            <WelcomeState
              history={history}
              choose={chooseQuery}
              clearHistory={clearHistory}
            />
          ) : search.isPending ? (
            <SearchSkeleton />
          ) : search.isError ? (
            <ErrorState error={search.error} retry={() => search.refetch()} />
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="font-serif text-xl font-bold">
                    <span className="sr-only">Semantic search returned </span>
                    {search.data?.count ?? 0} result
                    {search.data?.count === 1 ? "" : "s"}
                  </h2>
                  <p className="text-xs text-stone-500">
                    {source ? `Source: ${source} · ` : ""}
                    {minimum !== undefined
                      ? `Minimum similarity: ${Math.round(minimum * 100)}%`
                      : "No similarity threshold"}
                  </p>
                </div>
                {search.isFetching && search.data && (
                  <span className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
                    <LoaderCircle className="animate-spin" size={15} />{" "}
                    {search.isPlaceholderData
                      ? "Showing previous results while updating"
                      : "Updating results"}
                  </span>
                )}
              </div>
              {search.data?.results.length ? (
                search.data.results.map((result) => (
                  <SemanticSearchResultCard result={result} key={result.id} />
                ))
              ) : (
                <NoResults query={query} />
              )}
              {search.data && (
                <details className="rounded-xl border border-stone-200 px-4 py-3 text-xs text-stone-500 dark:border-stone-800">
                  <summary className="cursor-pointer font-medium">
                    Technical details
                  </summary>
                  <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                    <div>
                      <dt className="font-semibold">Embedding model</dt>
                      <dd className="break-all">{search.data.model}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold">Ranking</dt>
                      <dd>Cosine similarity in embedding space</dd>
                    </div>
                  </dl>
                </details>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function FilterPanel({
  source,
  limit,
  minimum,
  onChange,
  onClear,
}: {
  source: string;
  limit: number;
  minimum: number | undefined;
  onChange: (values: Record<string, string | number | undefined>) => void;
  onClear: () => void;
}) {
  return (
    <Card className="space-y-5 p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Filters</h2>
        <button
          type="button"
          onClick={onClear}
          className="text-xs font-semibold text-emerald-800 hover:underline dark:text-emerald-400"
        >
          Clear all
        </button>
      </div>
      <label className="block text-sm font-medium">
        Source
        <select
          value={source}
          onChange={(event) =>
            onChange({ source: event.target.value || undefined })
          }
          className="mt-2 h-10 w-full rounded-lg border border-stone-200 bg-white px-3 dark:border-stone-700 dark:bg-stone-900"
        >
          <option value="">All sources</option>
          <option value="aau-etd">AAU ETD</option>
        </select>
      </label>
      <label className="block text-sm font-medium">
        Result limit
        <select
          value={limit}
          onChange={(event) => onChange({ limit: Number(event.target.value) })}
          className="mt-2 h-10 w-full rounded-lg border border-stone-200 bg-white px-3 dark:border-stone-700 dark:bg-stone-900"
        >
          {[10, 20, 30, 50].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      <label className="block text-sm font-medium">
        Minimum similarity{" "}
        <span className="float-right text-stone-500">
          {minimum === undefined ? "Any" : `${Math.round(minimum * 100)}%`}
        </span>
        <input
          type="range"
          min="0"
          max="0.9"
          step="0.05"
          value={minimum ?? 0}
          onChange={(event) =>
            onChange({ minSimilarity: Number(event.target.value) || undefined })
          }
          className="mt-3 w-full accent-emerald-800"
          aria-label="Minimum semantic similarity"
        />
      </label>
      <div className="border-t border-stone-100 pt-4 text-xs text-stone-400 dark:border-stone-800">
        <p className="font-semibold">Coming later</p>
        <p className="mt-1">
          Year, language, institution, publication type, and subject filters.
        </p>
      </div>
    </Card>
  );
}
function ActiveFilters({
  source,
  limit,
  minimum,
  onRemove,
}: {
  source: string;
  limit: number;
  minimum: number | undefined;
  onRemove: (values: Record<string, string | number | undefined>) => void;
}) {
  if (!source && limit === 10 && minimum === undefined) return null;
  return (
    <div className="flex flex-wrap gap-2" aria-label="Active filters">
      {source && (
        <Chip
          label={`Source: ${source}`}
          remove={() => onRemove({ source: undefined })}
        />
      )}{" "}
      {limit !== 10 && (
        <Chip
          label={`Limit: ${limit}`}
          remove={() => onRemove({ limit: undefined })}
        />
      )}{" "}
      {minimum !== undefined && (
        <Chip
          label={`Similarity: ${Math.round(minimum * 100)}%+`}
          remove={() => onRemove({ minSimilarity: undefined })}
        />
      )}
    </div>
  );
}
function Chip({ label, remove }: { label: string; remove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
      {label}
      <button type="button" onClick={remove} aria-label={`Remove ${label}`}>
        <X size={13} />
      </button>
    </span>
  );
}
function WelcomeState({
  history,
  choose,
  clearHistory,
}: {
  history: string[];
  choose: (value: string) => void;
  clearHistory: () => void;
}) {
  return (
    <div className="space-y-5">
      <Card className="p-6">
        <Sparkles className="mb-3 text-amber-600" />
        <h2 className="font-serif text-xl font-bold">Try a suggested search</h2>
        <div className="mt-4 flex flex-wrap gap-2">
          {suggestions.map((item) => (
            <button
              type="button"
              onClick={() => choose(item)}
              key={item}
              className="rounded-full border border-stone-200 px-3 py-2 text-left text-sm hover:border-emerald-700 hover:text-emerald-800 dark:border-stone-700 dark:hover:text-emerald-300"
            >
              {item}
            </button>
          ))}
        </div>
      </Card>
      {history.length > 0 && (
        <Card className="p-5">
          <div className="flex justify-between">
            <h2 className="flex items-center gap-2 font-semibold">
              <Clock3 size={17} /> Recent searches
            </h2>
            <button
              type="button"
              onClick={clearHistory}
              className="text-xs font-semibold text-stone-500 hover:text-red-700"
            >
              Clear history
            </button>
          </div>
          <div className="mt-3 divide-y divide-stone-100 dark:divide-stone-800">
            {history.map((item) => (
              <button
                type="button"
                onClick={() => choose(item)}
                key={item}
                className="block w-full py-2 text-left text-sm hover:text-emerald-800 dark:hover:text-emerald-300"
              >
                {item}
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
function SearchSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading semantic search results">
      {Array.from({ length: 4 }, (_, index) => (
        <Card className="p-6" key={index}>
          <Skeleton className="h-4 w-32" />
          <Skeleton className="mt-5 h-7 w-4/5" />
          <Skeleton className="mt-4 h-4 w-full" />
          <Skeleton className="mt-2 h-4 w-3/4" />
          <Skeleton className="mt-6 h-9 w-36" />
        </Card>
      ))}
    </div>
  );
}
function NoResults({ query }: { query: string }) {
  return (
    <Card className="grid min-h-72 place-items-center p-8 text-center">
      <div>
        <BookOpen className="mx-auto mb-3 text-stone-400" />
        <h2 className="font-serif text-xl font-bold">
          No matching publications
        </h2>
        <p className="mt-2 max-w-md text-sm text-stone-500">
          No embedded publications matched “{query}”. Lower the similarity
          threshold, broaden the wording, or verify that embeddings have been
          generated.
        </p>
      </div>
    </Card>
  );
}
function ErrorState({ error, retry }: { error: Error; retry: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  const content = getErrorContent(error, apiError);
  const Icon = content.icon;
  return (
    <Card className="grid min-h-72 place-items-center p-8 text-center">
      <div>
        <Icon className="mx-auto mb-3 text-red-600" />
        <h2 className="font-serif text-xl font-bold">{content.title}</h2>
        <p className="mt-2 max-w-md text-sm text-stone-500">{content.body}</p>
        <Button className="mt-5" onClick={retry}>
          Try again
        </Button>
        {process.env.NODE_ENV === "development" && apiError?.details && (
          <details className="mt-4 max-w-lg text-left text-xs text-stone-500">
            <summary className="cursor-pointer">Technical details</summary>
            <p className="mt-2">{apiError.details}</p>
          </details>
        )}
      </div>
    </Card>
  );
}

function getErrorContent(error: Error, apiError: ApiError | null) {
  const message = error.message.toLowerCase();
  if (message.includes("embedding") || message.includes("vector")) {
    return {
      title: "Embeddings are not available",
      body: "Generate publication embeddings before using semantic search.",
      icon: BookOpen,
    };
  }
  if (apiError?.kind === "network") {
    return {
      title: "ResearchHub is unavailable",
      body: "Check that the API is running and reachable, then try again.",
      icon: ServerOff,
    };
  }
  if (apiError?.kind === "validation") {
    return {
      title: "Check your search",
      body: apiError.message,
      icon: AlertTriangle,
    };
  }
  if (apiError?.kind === "not-found") {
    return {
      title: "Semantic search is not enabled",
      body: "The API endpoint could not be found. Confirm the backend is up to date.",
      icon: ServerOff,
    };
  }
  if (apiError?.kind === "aborted") {
    return {
      title: "Search cancelled",
      body: "The previous search was cancelled before it completed.",
      icon: AlertTriangle,
    };
  }
  return {
    title: "Search could not be completed",
    body: "The server encountered a problem. Please retry in a moment.",
    icon: AlertTriangle,
  };
}
function boundedNumber(
  raw: string | null,
  fallback: number,
  min: number,
  max: number,
) {
  const value = Number(raw);
  return Number.isInteger(value) && value >= min && value <= max
    ? value
    : fallback;
}
function optionalBoundedNumber(raw: string | null, min: number, max: number) {
  if (raw === null || raw === "") return undefined;
  const value = Number(raw);
  return Number.isFinite(value) && value >= min && value <= max
    ? value
    : undefined;
}

function readHistory(): string[] {
  try {
    const stored: unknown = JSON.parse(
      localStorage.getItem(HISTORY_KEY) ?? "[]",
    );
    return Array.isArray(stored)
      ? stored
          .filter((item): item is string => typeof item === "string")
          .slice(0, 8)
      : [];
  } catch {
    return [];
  }
}

function persistSearchHistory(
  value: string,
  update: Dispatch<SetStateAction<string[]>>,
): void {
  update((current) => {
    const next = [value, ...current.filter((item) => item !== value)].slice(
      0,
      8,
    );
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
    return next;
  });
}
