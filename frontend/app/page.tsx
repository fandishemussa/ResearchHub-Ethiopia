"use client";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BookOpen,
  Building2,
  Database,
  FileText,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { Card, Skeleton } from "@/components/ui";

export default function DashboardPage() {
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: ({ signal }) => api.dashboard(signal),
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 5000),
    refetchInterval: (query) =>
      query.state.status === "error" ? 5_000 : 15_000,
  });
  const trends = useQuery({
    queryKey: ["publication-trends"],
    queryFn: ({ signal }) => api.trends(signal),
  });
  const keywords = useQuery({
    queryKey: ["keyword-trends"],
    queryFn: ({ signal }) => api.keywords(signal),
  });
  const sources = dashboard.data?.source_status ?? [];
  const stats = [
    {
      label: "Total publications",
      value: dashboard.data?.counts.total_publications,
      icon: FileText,
    },
    {
      label: "Active publications",
      value: dashboard.data
        ? dashboard.data.counts.total_publications -
          dashboard.data.counts.deleted_publications
        : undefined,
      icon: BookOpen,
    },
    {
      label: "Managed sources",
      value: sources.length || undefined,
      icon: Database,
    },
    {
      label: "Healthy sources",
      value: sources.filter((item) => item.is_active).length || undefined,
      icon: Activity,
    },
  ];
  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[.18em] text-amber-700 dark:text-amber-400">
          Platform overview
        </p>
        <h1 className="mt-2 font-serif text-3xl font-bold sm:text-4xl">
          Research at a glance
        </h1>
        <p className="mt-2 text-stone-500">
          A live view of Ethiopia&apos;s connected research landscape.
        </p>
      </div>
      {dashboard.isError && (
        <Card
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 border-red-200 bg-red-50 p-5 text-red-800 dark:bg-red-950/20"
        >
          <span>
            Research data is temporarily unavailable. The dashboard will retry
            automatically.
          </span>
          <button
            type="button"
            onClick={() => dashboard.refetch()}
            disabled={dashboard.isFetching}
            className="rounded-lg border border-red-300 px-3 py-2 text-sm font-semibold disabled:opacity-50"
          >
            {dashboard.isFetching ? "Retrying…" : "Try again"}
          </button>
        </Card>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map(({ label, value, icon: Icon }) => (
          <Card key={label} className="p-5">
            <div className="mb-5 flex items-center justify-between">
              <span className="text-sm text-stone-500">{label}</span>
              <span className="rounded-lg bg-emerald-50 p-2 text-emerald-800 dark:bg-emerald-950">
                <Icon size={18} />
              </span>
            </div>
            {value === undefined ? (
              <Skeleton className="h-9 w-24" />
            ) : (
              <strong className="text-3xl">{value.toLocaleString()}</strong>
            )}
          </Card>
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[1.7fr_1fr]">
        <Card className="p-5">
          <div className="mb-5">
            <h2 className="font-serif text-xl font-bold">
              Publications over time
            </h2>
            <p className="text-sm text-stone-500">Annual research output</p>
          </div>
          <div className="h-72">
            {trends.isLoading ? (
              <Skeleton className="h-full" />
            ) : trends.data?.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trends.data}>
                  <defs>
                    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" stopColor="#047857" stopOpacity={0.35} />
                      <stop offset="1" stopColor="#047857" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    vertical={false}
                    strokeDasharray="3 3"
                    opacity={0.25}
                  />
                  <XAxis dataKey="year" axisLine={false} tickLine={false} />
                  <YAxis axisLine={false} tickLine={false} />
                  <Tooltip />
                  <Area
                    dataKey="count"
                    type="monotone"
                    stroke="#047857"
                    strokeWidth={3}
                    fill="url(#fill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <Empty label="Trends appear after the data import." />
            )}
          </div>
        </Card>
        <Card className="p-5">
          <h2 className="font-serif text-xl font-bold">Top research topics</h2>
          <p className="mb-5 text-sm text-stone-500">Most frequent keywords</p>
          <div className="space-y-4">
            {keywords.isLoading ? (
              Array.from({ length: 6 }, (_, i) => (
                <Skeleton className="h-7" key={i} />
              ))
            ) : keywords.data?.length ? (
              keywords.data.map((item, index) => (
                <div className="flex items-center gap-3" key={item.keyword}>
                  <span className="w-5 text-xs text-stone-400">
                    {index + 1}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">
                    {item.keyword}
                  </span>
                  <b className="text-sm text-emerald-800 dark:text-emerald-400">
                    {item.count}
                  </b>
                </div>
              ))
            ) : (
              <Empty label="Keywords appear after import." />
            )}
          </div>
        </Card>
      </div>
      <Card className="overflow-hidden">
        <div className="border-b border-stone-200 p-5 dark:border-stone-800">
          <h2 className="font-serif text-xl font-bold">
            Managed source health
          </h2>
        </div>
        {sources.length ? (
          sources.map((item) => (
            <div
              key={item.name}
              className="flex items-center gap-4 border-b border-stone-100 p-4 last:border-0 dark:border-stone-800"
            >
              <span className="rounded-xl bg-stone-100 p-2.5 dark:bg-stone-800">
                <Building2 size={19} />
              </span>
              <div className="min-w-0 flex-1">
                <b className="block truncate text-sm">{item.name}</b>
                <span className="text-xs text-stone-500">{item.platform}</span>
              </div>
              <span
                className={
                  item.is_active
                    ? "text-xs font-semibold text-emerald-700"
                    : "text-xs text-stone-400"
                }
              >
                {item.is_active ? "Active" : "Inactive"}
              </span>
              <span className="w-20 text-right text-sm">
                {item.publication_count.toLocaleString()}
              </span>
            </div>
          ))
        ) : (
          <div className="p-8">
            <Empty label="No managed sources connected yet." />
          </div>
        )}
      </Card>
    </div>
  );
}
function Empty({ label }: { label: string }) {
  return (
    <div className="grid h-full place-items-center text-center text-sm text-stone-400">
      <div>
        <Database className="mx-auto mb-2" />
        <p>{label}</p>
      </div>
    </div>
  );
}
