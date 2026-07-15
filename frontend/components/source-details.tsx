"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  FileUp,
  Pencil,
  Play,
  RefreshCw,
  Save,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import type { ImportPreview, SourceUpdate } from "@/lib/types";
import { Card, Skeleton } from "@/components/ui";

export function SourceDetails({ id }: { id: string }) {
  const router = useRouter();
  const client = useQueryClient();
  const [file, setFile] = useState<File>();
  const [preview, setPreview] = useState<ImportPreview>();
  const [importJob, setImportJob] = useState<string>();
  const [uploadProgress, setUploadProgress] = useState(0);
  const [editForm, setEditForm] = useState<{
    name: string;
    description: string;
    base_url: string;
    oai_endpoint: string;
    metadata_prefix: string;
    set_spec: string;
    is_public: boolean;
  }>();
  const source = useQuery({
    queryKey: ["source", id],
    queryFn: ({ signal }) => api.source(id, signal),
  });
  const jobs = useQuery({
    queryKey: ["harvest-jobs", id],
    queryFn: ({ signal }) => api.harvestJobs(id, signal),
    refetchInterval: (q) =>
      q.state.data?.some((j) =>
        ["queued", "running", "retrying"].includes(j.status),
      )
        ? 3000
        : false,
  });
  const action = useMutation({
    mutationFn: (mode: "full" | "incremental" | "dry-run") =>
      api.runSourceHarvest(id, mode),
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: ["harvest-jobs", id] });
      location.href = `/harvest/jobs/${job.id}`;
    },
  });
  const test = useMutation({
    mutationFn: () => api.testSource(id),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["source", id] }),
  });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api.setSourceEnabled(id, enabled),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["source", id] }),
  });
  const update = useMutation({
    mutationFn: (payload: SourceUpdate) => api.updateSource(id, payload),
    onSuccess: (updated) => {
      client.setQueryData(["source", id], updated);
      setEditForm(undefined);
      void client.invalidateQueries({ queryKey: ["sources"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteSource(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["sources"] });
      router.push("/repositories");
    },
  });
  function confirmDelete() {
    if (
      window.confirm(
        `Remove "${source.data?.name || "this source"}"? Existing publications and harvest history will be preserved.`,
      )
    ) {
      remove.mutate();
    }
  }
  const upload = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a file");
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext !== "xml" && ext !== "json" && ext !== "csv")
        throw new Error("Use XML, JSON, or CSV");
      setUploadProgress(0);
      return api.uploadImport(id, ext, file, setUploadProgress);
    },
    onSuccess: async (job) => {
      setImportJob(job.id);
      setPreview(await api.previewImport(job.id));
      void client.invalidateQueries({ queryKey: ["harvest-jobs", id] });
    },
  });
  const confirm = useMutation({
    mutationFn: () => api.confirmImport(importJob!),
    onSuccess: (job) => (location.href = `/harvest/jobs/${job.id}`),
  });
  if (source.isPending) return <Skeleton className="h-96" />;
  if (source.isError)
    return <Card className="p-8">We could not load this source.</Card>;
  const item = source.data;
  function startEditing() {
    setEditForm({
      name: item.name,
      description: item.description || "",
      base_url: item.base_url || "",
      oai_endpoint: item.oai_endpoint || "",
      metadata_prefix: item.metadata_prefix,
      set_spec: item.set_spec || "",
      is_public: item.is_public,
    });
    update.reset();
  }
  function saveSource() {
    if (!editForm) return;
    update.mutate({
      name: editForm.name.trim(),
      description: editForm.description.trim() || null,
      base_url: editForm.base_url.trim() || null,
      oai_endpoint: editForm.oai_endpoint.trim() || null,
      metadata_prefix: editForm.metadata_prefix.trim(),
      set_spec: editForm.set_spec.trim() || null,
      is_public: editForm.is_public,
    });
  }
  return (
    <div className="space-y-5">
      <Link
        href="/repositories"
        className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-800"
      >
        <ArrowLeft size={16} />
        Sources
      </Link>
      <Card className="p-5 sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-amber-700">
              {item.source_type.replaceAll("_", " ")}
            </p>
            <h1 className="mt-2 font-serif text-3xl font-bold">{item.name}</h1>
            <p className="mt-2 text-sm text-stone-500">
              {item.oai_endpoint || item.base_url || "Manual import source"}
            </p>
          </div>
          <span className="rounded-full bg-stone-100 px-3 py-1 text-sm font-semibold capitalize dark:bg-stone-800">
            {item.status}
          </span>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <button onClick={() => test.mutate()} className="btn">
            <Activity size={15} />
            Test connection
          </button>
          <button onClick={startEditing} className="btn">
            <Pencil size={15} />
            Edit source
          </button>
          <button onClick={() => action.mutate("incremental")} className="btn">
            <Play size={15} />
            Incremental harvest
          </button>
          <button onClick={() => action.mutate("full")} className="btn">
            Full harvest
          </button>
          <button onClick={() => action.mutate("dry-run")} className="btn">
            Dry run
          </button>
          <button
            onClick={() => toggle.mutate(!item.is_active)}
            className="btn"
          >
            {item.is_active ? "Disable" : "Enable"}
          </button>
          <button
            onClick={confirmDelete}
            disabled={remove.isPending}
            className="btn border-red-300 text-red-700 dark:border-red-900 dark:text-red-400"
          >
            <Trash2 size={15} />
            {remove.isPending ? "Removing..." : "Remove source"}
          </button>
        </div>
      </Card>
      {editForm && (
        <Card className="p-5 sm:p-7">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-serif text-xl font-bold">
              Edit managed source
            </h2>
            <button
              type="button"
              className="btn"
              onClick={() => setEditForm(undefined)}
              aria-label="Close source editor"
            >
              <X size={15} />
            </button>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <SourceField
              label="Source name"
              value={editForm.name}
              required
              onChange={(name) => setEditForm({ ...editForm, name })}
            />
            <SourceField
              label="Base URL"
              value={editForm.base_url}
              type="url"
              onChange={(base_url) => setEditForm({ ...editForm, base_url })}
            />
            <SourceField
              label="OAI-PMH endpoint"
              value={editForm.oai_endpoint}
              type="url"
              onChange={(oai_endpoint) =>
                setEditForm({ ...editForm, oai_endpoint })
              }
            />
            <SourceField
              label="Metadata prefix"
              value={editForm.metadata_prefix}
              required
              onChange={(metadata_prefix) =>
                setEditForm({ ...editForm, metadata_prefix })
              }
            />
            <SourceField
              label="Set specification"
              value={editForm.set_spec}
              onChange={(set_spec) => setEditForm({ ...editForm, set_spec })}
            />
            <SourceField
              label="Description"
              value={editForm.description}
              onChange={(description) =>
                setEditForm({ ...editForm, description })
              }
            />
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={editForm.is_public}
              onChange={(event) =>
                setEditForm({ ...editForm, is_public: event.target.checked })
              }
            />
            Public source
          </label>
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn"
              onClick={saveSource}
              disabled={
                update.isPending ||
                !editForm.name.trim() ||
                !editForm.metadata_prefix.trim()
              }
            >
              <Save size={15} />
              {update.isPending ? "Saving..." : "Save changes"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setEditForm(undefined)}
              disabled={update.isPending}
            >
              Cancel
            </button>
          </div>
          {update.isError && (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {update.error.message}
            </p>
          )}
        </Card>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="font-serif text-xl font-bold">Import metadata file</h2>
          <p className="mt-1 text-sm text-stone-500">
            Upload XML, JSON, or CSV, preview it, then confirm database changes.
          </p>
          <label className="mt-4 block cursor-pointer rounded-xl border border-dashed border-stone-300 p-4 text-sm hover:border-emerald-700 dark:border-stone-700">
            <span className="font-semibold">
              {file ? file.name : "Choose an XML, JSON, or CSV file"}
            </span>
            <span className="mt-1 block text-xs text-stone-500">
              {file
                ? `${(file.size / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} KB selected`
                : "Click here to browse files. Maximum server limit: 100 MB."}
            </span>
            <input
              className="sr-only"
              type="file"
              accept=".xml,.json,.csv,application/json,text/csv,application/xml,text/xml"
              onChange={(event) => {
                setFile(event.target.files?.[0]);
                setPreview(undefined);
                setImportJob(undefined);
                setUploadProgress(0);
                upload.reset();
              }}
            />
          </label>
          <button
            disabled={!file || upload.isPending}
            onClick={() => upload.mutate()}
            className="mt-4 btn"
          >
            <FileUp size={15} />
            {upload.isPending
              ? "Uploading and validating…"
              : "Upload and preview"}
          </button>
          {upload.isPending && (
            <div className="mt-3" aria-live="polite">
              <div className="mb-1 flex justify-between text-xs text-stone-600">
                <span>
                  {uploadProgress < 100
                    ? "Uploading file"
                    : "Validating records"}
                </span>
                <span>{uploadProgress}%</span>
              </div>
              <div
                className="h-2 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700"
                role="progressbar"
                aria-label="File upload progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={uploadProgress}
              >
                <div
                  className={`h-full bg-emerald-700 transition-[width] duration-200 ${uploadProgress === 100 ? "animate-pulse" : ""}`}
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}
          {upload.isError && (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {upload.error.message}
            </p>
          )}
          {preview && (
            <div className="mt-4 rounded-xl bg-stone-100 p-4 text-sm dark:bg-stone-800">
              <p>
                {preview.total_records.toLocaleString()} rows:{" "}
                {preview.valid_records.toLocaleString()} valid,{" "}
                {preview.invalid_records.toLocaleString()} skipped
              </p>
              {preview.invalid_records > 0 && (
                <div className="mt-3 rounded-lg bg-amber-50 p-3 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                  <p className="font-semibold">
                    Invalid rows will not be imported.
                  </p>
                  <ul className="mt-1 list-disc pl-5 text-xs">
                    {preview.validation_errors.slice(0, 5).map((error) => (
                      <li key={`${error.record_index}-${error.message}`}>
                        Row {error.record_index + 1}: {error.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <ul className="mt-2 list-disc pl-5">
                {preview.sample_records.slice(0, 5).map((r, i) => (
                  <li key={`${r.external_id}-${i}`}>{r.title}</li>
                ))}
              </ul>
              <button
                onClick={() => confirm.mutate()}
                disabled={confirm.isPending}
                className="mt-4 rounded-lg bg-emerald-800 px-3 py-2 font-semibold text-white"
              >
                {confirm.isPending ? "Importing…" : "Confirm import"}
              </button>
              {confirm.isError && (
                <p role="alert" className="mt-3 text-red-700">
                  {confirm.error.message}
                </p>
              )}
            </div>
          )}
        </Card>
        <Card className="p-5">
          <div className="flex justify-between">
            <h2 className="font-serif text-xl font-bold">Harvest history</h2>
            <button aria-label="Refresh history" onClick={() => jobs.refetch()}>
              <RefreshCw size={16} />
            </button>
          </div>
          <div className="mt-4 space-y-2">
            {jobs.data?.map((job) => (
              <Link
                key={job.id}
                href={`/harvest/jobs/${job.id}`}
                className="flex justify-between rounded-lg border border-stone-200 p-3 text-sm dark:border-stone-700"
              >
                <span className="capitalize">
                  {job.mode.replaceAll("_", " ")}
                </span>
                <span>
                  {job.status} - {job.fetched_records} fetched
                </span>
              </Link>
            ))}
            {!jobs.data?.length && (
              <p className="text-sm text-stone-500">
                No harvest or import jobs yet.
              </p>
            )}
          </div>
        </Card>
      </div>
      {(action.isError || test.isError || remove.isError) && (
        <p role="alert" className="text-sm text-red-700">
          {(action.error || test.error || remove.error)?.message}
        </p>
      )}
    </div>
  );
}

function SourceField({
  label,
  value,
  onChange,
  type = "text",
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "url";
  required?: boolean;
}) {
  return (
    <label className="text-sm font-semibold">
      {label}
      <input
        type={type}
        value={value}
        required={required}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-lg border border-stone-300 bg-transparent px-3 py-2 font-normal dark:border-stone-700"
      />
    </label>
  );
}
