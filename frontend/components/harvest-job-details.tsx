"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RotateCcw, XCircle } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, Skeleton } from "@/components/ui";
const active = ["pending", "queued", "running", "retrying"];
export function HarvestJobDetails({ id }: { id: string }) {
  const client = useQueryClient();
  const job = useQuery({
    queryKey: ["harvest-job", id],
    queryFn: ({ signal }) => api.harvestJob(id, signal),
    refetchInterval: (q) =>
      active.includes(q.state.data?.status || "") ? 2500 : false,
  });
  const events = useQuery({
    queryKey: ["harvest-events", id],
    queryFn: ({ signal }) => api.harvestEvents(id, signal),
    refetchInterval:
      job.data && active.includes(job.data.status) ? 3000 : false,
  });
  const failures = useQuery({
    queryKey: ["harvest-failures", id],
    queryFn: ({ signal }) => api.harvestFailures(id, signal),
  });
  const refresh = () =>
    void client.invalidateQueries({ queryKey: ["harvest-job", id] });
  const cancel = useMutation({
    mutationFn: () => api.cancelHarvest(id),
    onSuccess: refresh,
  });
  const retry = useMutation({
    mutationFn: () => api.retryHarvest(id),
    onSuccess: (next) => (location.href = `/harvest/jobs/${next.id}`),
  });
  if (job.isPending) return <Skeleton className="h-96" />;
  if (job.isError)
    return <Card className="p-8">Harvest job could not be loaded.</Card>;
  const item = job.data;
  const counters = [
    ["Fetched", item.fetched_records],
    ["Created", item.created_records],
    ["Updated", item.updated_records],
    ["Unchanged", item.unchanged_records],
    ["Deleted", item.deleted_records],
    ["Duplicates", item.duplicate_records],
    ["Failed", item.failed_records],
  ] as const;
  return (
    <div className="space-y-5">
      <Link
        href={`/repositories/${item.connector_id}`}
        className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-800"
      >
        <ArrowLeft size={16} />
        Source
      </Link>
      <Card className="p-5 sm:p-7">
        <div className="flex flex-wrap justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-amber-700">
              {item.job_type}
            </p>
            <h1 className="mt-2 font-serif text-3xl font-bold">
              {item.mode.replaceAll("_", " ")} job
            </h1>
            <p className="mt-2 font-mono text-xs text-stone-500">{item.id}</p>
          </div>
          <span className="capitalize">{item.status}</span>
        </div>
        <div className="mt-5 h-2 overflow-hidden rounded bg-stone-200">
          <div
            className="h-full bg-emerald-700"
            style={{
              width: `${item.total_records ? Math.min(100, (item.fetched_records / item.total_records) * 100) : active.includes(item.status) ? 15 : 100}%`,
            }}
          />
        </div>
        <div className="mt-5 flex gap-2">
          {active.includes(item.status) && (
            <button className="btn" onClick={() => cancel.mutate()}>
              <XCircle size={15} />
              Cancel
            </button>
          )}
          {!active.includes(item.status) && item.status !== "completed" && (
            <button className="btn" onClick={() => retry.mutate()}>
              <RotateCcw size={15} />
              Retry
            </button>
          )}
        </div>
      </Card>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {counters.map(([label, value]) => (
          <Card key={label} className="p-4">
            <span className="text-xs text-stone-500">{label}</span>
            <strong className="mt-1 block text-2xl">
              {value.toLocaleString()}
            </strong>
          </Card>
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="font-serif text-xl font-bold">Events</h2>
          <div className="mt-4 space-y-3">
            {events.data?.map((e) => (
              <div
                key={e.id}
                className="border-l-2 border-emerald-700 pl-3 text-sm"
              >
                <b>{e.event_type.replaceAll("_", " ")}</b>
                <p className="text-stone-500">{e.message}</p>
              </div>
            ))}
          </div>
        </Card>
        <Card className="p-5">
          <h2 className="font-serif text-xl font-bold">Failures</h2>
          <div className="mt-4 space-y-3">
            {failures.data?.map((f) => (
              <div
                key={f.id}
                className="rounded-lg bg-red-50 p-3 text-sm text-red-900"
              >
                <b>{f.external_id || `Record ${f.record_index}`}</b>
                <p>{f.error_message}</p>
              </div>
            ))}
            {!failures.data?.length && (
              <p className="text-sm text-stone-500">
                No record-level failures.
              </p>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
